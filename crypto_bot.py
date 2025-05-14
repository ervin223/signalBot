import os, json, logging, asyncio, mysql.connector
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage

# ─── 1. Load .env ─────────────────────────────────────────────────────────
load_dotenv(override=True)
API_TOKEN = os.getenv("TELEGRAM_TOKEN")
DB_CFG = {
    "host":     os.getenv("DB_HOST"),
    "port":     int(os.getenv("DB_PORT",   "3306")),
    "user":     os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
}
if not API_TOKEN:
    logging.error("Missing TELEGRAM_TOKEN in .env")
    exit(1)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())

# ─── 2. FSM states ─────────────────────────────────────────────────────────
class Form(StatesGroup):
    lang     = State()
    username = State()
    email    = State()

# ─── 3. DB helper ──────────────────────────────────────────────────────────
def get_conn():
    return mysql.connector.connect(**DB_CFG)

# ─── 4. Load locale ─────────────────────────────────────────────────────────
def load_messages(lang: str) -> dict:
    return json.load(open(f"locales/{lang}.json", encoding="utf-8"))

# ─── 5. Keyboards ───────────────────────────────────────────────────────────
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
        keyboard=[
            [
                KeyboardButton(text=msgs["signals_button"]),
                KeyboardButton(text=msgs["commands_button"])
            ]
        ],
        resize_keyboard=True
    )

# ─── 6. Handlers ────────────────────────────────────────────────────────────

@dp.message(Command("start"))
async def cmd_start(msg: types.Message, state: FSMContext):
    await state.clear()
    # просто двуязычный призыв
    await msg.answer(
        "Please choose your language / Пожалуйста, выберите язык",
        reply_markup=language_kb()
    )
    await state.set_state(Form.lang)

async def _save_language(uid: int, lang: str):
    conn = get_conn(); cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (user_id, language) VALUES (%s,%s) "
        "ON DUPLICATE KEY UPDATE language=%s",
        (uid, lang, lang)
    )
    conn.commit()
    cur.close()
    conn.close()

@dp.callback_query(Form.lang, F.data.startswith("lang:"))
async def on_lang(cb: types.CallbackQuery, state: FSMContext):
    lang = cb.data.split(":",1)[1]
    uid  = cb.from_user.id

    await _save_language(uid, lang)
    await state.update_data(lang=lang)

    msgs = load_messages(lang)
    # показываем стартовое сообщение из локали
    await cb.message.edit_text(text=msgs["start_message"], reply_markup=reset_kb())

    # сразу спрашиваем никнейм
    await cb.message.answer(text=msgs["ask_username"], reply_markup=reset_kb())
    await state.set_state(Form.username)
    await cb.answer()

@dp.message(Form.username, F.text)
async def process_username(msg: types.Message, state: FSMContext):
    await state.update_data(username=msg.text.strip())
    data = await state.get_data()
    msgs = load_messages(data["lang"])

    # теперь спрашиваем почту
    await msg.answer(text=msgs["ask_email"], reply_markup=reset_kb())
    await state.set_state(Form.email)

@dp.message(Form.email, F.text)
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
    conn.commit()
    cur.close()
    conn.close()

    msgs = load_messages(lang)
    # регистрация прошла — отправляем подтверждение + главное меню
    await msg.answer(
        text=msgs["registration_success"].format(username=username, email=email),
        reply_markup=main_menu_kb(lang)
    )
    await state.clear()

@dp.callback_query(F.data=="action:reset")
async def on_reset(cb: types.CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    conn = get_conn(); cur = conn.cursor()
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

# ─── Main menu ───────────────────────────────────────────────────────────────

@dp.message(F.text == load_messages("en")["signals_button"])
@dp.message(F.text == load_messages("ru")["signals_button"])
async def show_signals(msg: types.Message):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT language FROM users WHERE user_id=%s", (msg.from_user.id,))
    lang = cur.fetchone()[0]
    cur.close(); conn.close()

    msgs = load_messages(lang)
    await msg.answer(text=msgs["signals_text"])

@dp.message(F.text == load_messages("en")["commands_button"])
@dp.message(F.text == load_messages("ru")["commands_button"])
async def show_commands(msg: types.Message):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT language FROM users WHERE user_id=%s", (msg.from_user.id,))
    lang = cur.fetchone()[0]
    cur.close(); conn.close()

    msgs = load_messages(lang)
    await msg.answer(text=msgs["commands_list"])

# ─── Run ─────────────────────────────────────────────────────────────────────
async def main():
    await dp.start_polling(bot)

if __name__=="__main__":
    asyncio.run(main())
