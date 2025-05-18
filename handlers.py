# handlers.py

import datetime
from datetime import datetime as dt
from aiogram import types, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from db import get_conn, save_language
from locale_utils import load_messages
from payments import create_invoice

# ─── FSM states ───────────────────────────────────────────────────────────────
class Form(StatesGroup):
    lang     = State()
    username = State()
    email    = State()

# ─── Keyboards ────────────────────────────────────────────────────────────────
def language_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="English", callback_data="lang:en"),
            InlineKeyboardButton(text="Русский", callback_data="lang:ru"),
        ]]
    )

def reset_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔄 Reset", callback_data="action:reset")]]
    )

def main_menu_kb(lang: str) -> ReplyKeyboardMarkup:
    msgs = load_messages(lang)
    return ReplyKeyboardMarkup(
        keyboard=[[ 
            KeyboardButton(text=msgs["signals_button"]),
            KeyboardButton(text=msgs["commands_button"])
        ]],
        resize_keyboard=True
    )

def buy_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💳 Оплатить подписку", callback_data="action:buy")]]
    )

# ─── Утилита для языка пользователя ───────────────────────────────────────────
async def get_user_lang(user_id: int) -> str:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT language FROM users WHERE user_id=%s", (user_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return row[0] if row else "en"

# ─── Handlers ─────────────────────────────────────────────────────────────────
async def cmd_start(msg: types.Message, state: FSMContext):
    await state.clear()
    await msg.answer(
        "Please choose your language / Пожалуйста, выберите язык",
        reply_markup=language_kb()
    )
    await state.set_state(Form.lang)

async def on_lang(cb: types.CallbackQuery, state: FSMContext):
    lang = cb.data.split(":",1)[1]
    uid  = cb.from_user.id

    # Сохраняем язык в БД (синхронно)
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

    conn = get_conn(); cur = conn.cursor()
    cur.execute(
        "UPDATE users SET username=%s, email=%s WHERE user_id=%s",
        (username, email, uid)
    )
    conn.commit(); cur.close(); conn.close()

    msgs = load_messages(lang)
    await msg.answer(
        text=msgs["registration_success"].format(username=username, email=email),
        reply_markup=main_menu_kb(lang)
    )
    await state.clear()

async def on_reset(cb: types.CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    conn = get_conn(); cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE user_id=%s", (uid,))
    conn.commit(); cur.close(); conn.close()

    await state.clear()
    await cb.message.edit_text(
        text="Please choose your language / Пожалуйста, выберите язык",
        reply_markup=language_kb()
    )
    await state.set_state(Form.lang)
    await cb.answer()

async def show_signals(msg: types.Message):
    uid = msg.from_user.id
    conn = get_conn(); cur = conn.cursor()
    cur.execute(
        "SELECT language, is_subscribed, subscription_until FROM users WHERE user_id=%s",
        (uid,)
    )
    row = cur.fetchone()
    cur.close(); conn.close()

    lang, is_sub, until = row if row else ("en", 0, None)
    msgs = load_messages(lang)

    if not is_sub or (until and until < dt.utcnow()):
        return await msg.answer(msgs["pay_prompt"], reply_markup=buy_kb())

    await msg.answer(text=msgs["signals_text"])

async def on_buy(cb: types.CallbackQuery):
    user_id = cb.from_user.id
    invoice = await create_invoice(amount=2.0, currency="USD", order_id=str(user_id))
    pay_url = invoice["invoice_url"]

    lang = await get_user_lang(user_id)
    msgs = load_messages(lang)
    await cb.message.answer(msgs["invoice_message"].format(url=pay_url))
    await cb.answer()

async def show_commands(msg: types.Message):
    uid = msg.from_user.id
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT language FROM users WHERE user_id=%s", (uid,))
    row = cur.fetchone()
    cur.close(); conn.close()

    lang = row[0] if row else "en"
    msgs = load_messages(lang)
    await msg.answer(text=msgs["commands_list"])

async def cmd_activate(msg: types.Message):
    parts = msg.text.split(maxsplit=1)
    if len(parts) < 2:
        return await msg.reply("Укажите TX-хеш: /activate <tx-hash>")
    uid = msg.from_user.id

    conn = get_conn(); cur = conn.cursor()
    cur.execute(
        "UPDATE users SET is_subscribed=1, subscription_until=DATE_ADD(NOW(), INTERVAL 30 DAY) WHERE user_id=%s",
        (uid,)
    )
    conn.commit(); cur.close(); conn.close()

    lang = await get_user_lang(uid)
    msgs = load_messages(lang)
    await msg.answer(msgs["subscribe_success"])

# ─── Регистрация всех хэндлеров ─────────────────────────────────────────────
def register_handlers(dp: Dispatcher):
    dp.message.register(cmd_start, Command("start"))
    dp.callback_query.register(on_lang, Form.lang, lambda c: c.data.startswith("lang:"))
    dp.message.register(process_username, Form.username, lambda m: True)
    dp.message.register(process_email, Form.email, lambda m: True)
    dp.callback_query.register(on_reset, lambda c: c.data == "action:reset")
    dp.message.register(show_signals, F.text == load_messages("en")["signals_button"])
    dp.message.register(show_signals, F.text == load_messages("ru")["signals_button"])
    dp.callback_query.register(on_buy, lambda c: c.data == "action:buy")
    dp.message.register(show_commands, F.text == load_messages("en")["commands_button"])
    dp.message.register(show_commands, F.text == load_messages("ru")["commands_button"])
    dp.message.register(cmd_activate, Command("activate"))
