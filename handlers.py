from aiogram import types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from db import get_conn, save_language
from locale_utils import load_messages
from keyboards import language_kb, reset_kb, main_menu_kb


class Form(StatesGroup):
    lang = State()
    username = State()
    email = State()


def register_handlers(dp):
    @dp.message(Command("start"))
    async def cmd_start(msg: types.Message, state: FSMContext):
        await state.clear()
        await msg.answer(
            "Please choose your language / Пожалуйста, выберите язык",
            reply_markup=language_kb()
        )
        await state.set_state(Form.lang)

    @dp.callback_query(Form.lang, F.data.startswith("lang:"))
    async def on_lang(cb: types.CallbackQuery, state: FSMContext):
        lang = cb.data.split(":", 1)[1]
        uid = cb.from_user.id

        save_language(uid, lang)
        await state.update_data(lang=lang)

        msgs = load_messages(lang)
        await cb.message.edit_text(text=msgs["start_message"], reply_markup=reset_kb())
        await cb.message.answer(text=msgs["ask_username"], reply_markup=reset_kb())
        await state.set_state(Form.username)
        await cb.answer()

    @dp.message(Form.username, F.text)
    async def process_username(msg: types.Message, state: FSMContext):
        await state.update_data(username=msg.text.strip())
        data = await state.get_data()
        msgs = load_messages(data["lang"])

        await msg.answer(text=msgs["ask_email"], reply_markup=reset_kb())
        await state.set_state(Form.email)

    @dp.message(Form.email, F.text)
    async def process_email(msg: types.Message, state: FSMContext):
        data = await state.get_data()
        uid = msg.from_user.id
        lang = data["lang"]
        username = data["username"]
        email = msg.text.strip()

        conn = get_conn()
        cur = conn.cursor()
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

    @dp.callback_query(F.data == "action:reset")
    async def on_reset(cb: types.CallbackQuery, state: FSMContext):
        uid = cb.from_user.id
        conn = get_conn()
        cur = conn.cursor()
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

    @dp.message(F.text == load_messages("en")["signals_button"])
    @dp.message(F.text == load_messages("ru")["signals_button"])
    async def show_signals(msg: types.Message):
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT language FROM users WHERE user_id=%s", (msg.from_user.id,))
        lang = cur.fetchone()[0]
        cur.close()
        conn.close()

        msgs = load_messages(lang)
        await msg.answer(text=msgs["signals_text"])

    @dp.message(F.text == load_messages("en")["commands_button"])
    @dp.message(F.text == load_messages("ru")["commands_button"])
    async def show_commands(msg: types.Message):
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT language FROM users WHERE user_id=%s", (msg.from_user.id,))
        lang = cur.fetchone()[0]
        cur.close()
        conn.close()

        msgs = load_messages(lang)
        await msg.answer(text=msgs["commands_list"])