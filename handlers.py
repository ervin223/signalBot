# handlers.py

import os
import datetime
import logging
import httpx
from aiogram import types, F, Dispatcher
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)

from db import get_conn, save_language
from locale_utils import load_messages
from payments import create_email_subscription, fetch_subscription_invoices, SUBSCRIPTION_PLANS


# ─── FSM ──────────────────────────────────────────────────────────────────────
class Form(StatesGroup):
    lang     = State()
    username = State()
    email    = State()

# ─── Keyboards ─────────────────────────────────────────────────────────────────
def language_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="English", callback_data="lang:en"),
        InlineKeyboardButton(text="Русский", callback_data="lang:ru"),
    ]])

def reset_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Reset", callback_data="action:reset")]
    ])

def main_menu_kb(lang: str) -> ReplyKeyboardMarkup:
    msgs = load_messages(lang)
    return ReplyKeyboardMarkup(
        keyboard=[[ 
            KeyboardButton(text=msgs["signals_button"]),
            KeyboardButton(text=msgs["commands_button"])
        ]],
        resize_keyboard=True
    )

def buy_kb(lang: str) -> InlineKeyboardMarkup:
    from payments import SUBSCRIPTION_PLANS  # если нужно импортировать

    buttons = []
    for key, plan in SUBSCRIPTION_PLANS.items():
        label = plan[f"label_{lang}"]
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"buy:{key}")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ─── Утилита ────────────────────────────────────────────────────────────────────
async def get_user_lang(user_id: int) -> str:
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("SELECT language FROM users WHERE user_id=%s", (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else "en"

# ─── Хэндлеры ──────────────────────────────────────────────────────────────────
async def cmd_start(msg: types.Message, state: FSMContext):
    await state.clear()
    await msg.answer(
        text="Please choose your language / Пожалуйста, выберите язык",
        reply_markup=language_kb()
    )
    await state.set_state(Form.lang)

async def on_lang(cb: types.CallbackQuery, state: FSMContext):
    lang = cb.data.split(":", 1)[1]
    uid  = cb.from_user.id
    save_language(uid, lang)
    await state.update_data(lang=lang)

    msgs = load_messages(lang)
    await cb.message.edit_text(text=msgs["start_message"], reply_markup=reset_kb())
    await cb.message.answer(text=msgs["ask_username"], reply_markup=reset_kb())
    await state.set_state(Form.username)
    await cb.answer()

async def process_username(msg: types.Message, state: FSMContext):
    await state.update_data(username=msg.text.strip())
    data = await state.get_data()
    msgs = load_messages(data["lang"])
    await msg.answer(text=msgs["ask_email"], reply_markup=reset_kb())
    await state.set_state(Form.email)

async def process_email(msg: types.Message, state: FSMContext):
    data     = await state.get_data()
    uid      = msg.from_user.id
    lang     = data["lang"]
    username = data["username"]
    email    = msg.text.strip()

    conn = get_conn()
    cur  = conn.cursor()
    cur.execute(
        "UPDATE users SET username=%s, email=%s WHERE user_id=%s",
        (username, email, uid)
    )
    conn.commit()
    cur.close()
    conn.close()

    msgs = load_messages(lang)
    await msg.answer(
        text=msgs["registration_success"].format(username=username, email=email),
        reply_markup=main_menu_kb(lang)
    )
    await state.clear()

async def on_reset(cb: types.CallbackQuery, state: FSMContext):
    uid  = cb.from_user.id
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("DELETE FROM users WHERE user_id=%s", (uid,))
    conn.commit()
    cur.close()
    conn.close()

    await state.clear()
    await cb.message.edit_text(
        text="Please choose your language / Пожалуйста, выберите язык",
        reply_markup=language_kb()
    )
    await state.set_state(Form.lang)
    await cb.answer()

async def show_signals(msg: types.Message):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    msgs = load_messages(lang)

    conn = get_conn(); cur = conn.cursor()
    cur.execute("""
        SELECT status, expire_at
          FROM subscriptions
         WHERE user_id=%s AND status='ACTIVE' AND expire_at > NOW()
      ORDER BY created_at DESC
         LIMIT 1
    """, (uid,))
    row = cur.fetchone()
    cur.close(); conn.close()

    if not row:
        await msg.answer(text=msgs["pay_prompt"], reply_markup=buy_kb(lang))
    else:
        await msg.answer(text=msgs["signals_text"])


async def on_buy(cb: types.CallbackQuery):
    from payments import SUBSCRIPTION_PLANS

    uid = cb.from_user.id
    plan_key = cb.data.split(":", 1)[1]
    await cb.answer("⏳ Формирую подписку…")

    plan = SUBSCRIPTION_PLANS.get(plan_key)
    if not plan:
        await cb.message.answer("❌ Неверный план подписки.")
        return

    plan_id = plan["id"]

    # Получаем email пользователя
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT email FROM users WHERE user_id=%s", (uid,))
    row = cur.fetchone()
    cur.close(); conn.close()

    if not row:
        await cb.message.answer("❌ Email не найден. Сначала зарегистрируйтесь командой /start.")
        return

    email = row[0]

    # Создаём подписку
    try:
        sub = await create_email_subscription(email, plan_id)
    except httpx.HTTPStatusError as e:
        logging.error("NOWPayments /subscriptions error %s: %s", e.response.status_code, e.response.text)
        await cb.message.answer("❌ Не удалось оформить подписку: " + e.response.json().get("message", ""))
        return

    sub_id = sub.get("id")
    if not sub_id:
        await cb.message.answer("❌ Не удалось получить ID подписки.")
        return

    logging.info(f"🔖 Subscription ID: {sub_id}")

    # Сохраняем в БД
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO subscriptions(subscription_id, user_id, plan_id, email, status, expire_at, created_at, updated_at)
        VALUES (%s, %s, %s, %s, 'WAITING_PAY', DATE_ADD(NOW(), INTERVAL 30 DAY), NOW(), NOW())
        ON DUPLICATE KEY UPDATE
            status = 'WAITING_PAY',
            expire_at = DATE_ADD(NOW(), INTERVAL 30 DAY),
            updated_at = NOW()
    """, (sub_id, uid, plan_id, email))
    conn.commit(); cur.close(); conn.close()

    # Получаем ссылку на оплату
    invs = await fetch_subscription_invoices(sub_id)
    if invs:
        url = invs[0].get("invoice_url")
        await cb.message.answer(f"🔗 Оплатите подписку по ссылке:\n{url}")
    else:
        await cb.message.answer("✅ Подписка создана, но счёт пока не готов. Попробуйте позже.")
async def on_buy(cb: types.CallbackQuery):
    from payments import SUBSCRIPTION_PLANS

    uid = cb.from_user.id
    plan_key = cb.data.split(":", 1)[1]
    await cb.answer("⏳ Формирую подписку…")

    plan = SUBSCRIPTION_PLANS.get(plan_key)
    if not plan:
        await cb.message.answer("❌ Неверный план подписки.")
        return

    plan_id = plan["id"]

    # Получаем email пользователя
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT email FROM users WHERE user_id=%s", (uid,))
    row = cur.fetchone()
    cur.close(); conn.close()

    if not row:
        await cb.message.answer("❌ Email не найден. Сначала зарегистрируйтесь командой /start.")
        return

    email = row[0]

    # Создаём подписку
    try:
        sub = await create_email_subscription(email, plan_id)
    except httpx.HTTPStatusError as e:
        logging.error("NOWPayments /subscriptions error %s: %s", e.response.status_code, e.response.text)
        await cb.message.answer("❌ Не удалось оформить подписку: " + e.response.json().get("message", ""))
        return

    sub_id = sub.get("id")
    if not sub_id:
        await cb.message.answer("❌ Не удалось получить ID подписки.")
        return

    logging.info(f"🔖 Subscription ID: {sub_id}")

    # Сохраняем в БД
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO subscriptions(subscription_id, user_id, plan_id, email, status, expire_at, created_at, updated_at)
        VALUES (%s, %s, %s, %s, 'WAITING_PAY', DATE_ADD(NOW(), INTERVAL 30 DAY), NOW(), NOW())
        ON DUPLICATE KEY UPDATE
            status = 'WAITING_PAY',
            expire_at = DATE_ADD(NOW(), INTERVAL 30 DAY),
            updated_at = NOW()
    """, (sub_id, uid, plan_id, email))
    conn.commit(); cur.close(); conn.close()

    # Получаем ссылку на оплату
    invs = await fetch_subscription_invoices(sub_id)
    if invs:
        url = invs[0].get("invoice_url")
        await cb.message.answer(f"🔗 Оплатите подписку по ссылке:\n{url}")
    else:
        await cb.message.answer("✅ Подписка создана, но счёт пока не готов. Попробуйте позже.")





async def show_commands(msg: types.Message):
    lang = await get_user_lang(msg.from_user.id)
    await msg.answer(text=load_messages(lang)["commands_list"])

# ─── Регистрация хэндлеров ─────────────────────────────────────────────────────
def register_handlers(dp: Dispatcher):
    dp.message.register(cmd_start,        Command("start"))
    dp.callback_query.register(on_lang,   Form.lang, lambda c: c.data.startswith("lang:"))
    dp.message.register(process_username, Form.username)
    dp.message.register(process_email,    Form.email)
    dp.callback_query.register(on_reset,  lambda c: c.data == "action:reset")
    dp.message.register(show_signals,     F.text == load_messages("en")["signals_button"])
    dp.message.register(show_signals,     F.text == load_messages("ru")["signals_button"])
    dp.callback_query.register(on_buy, lambda c: c.data.startswith("buy:"))
    dp.message.register(show_commands,    F.text == load_messages("en")["commands_button"])
    dp.message.register(show_commands,    F.text == load_messages("ru")["commands_button"])
