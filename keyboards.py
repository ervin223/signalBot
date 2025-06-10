from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from locale_utils import load_messages
from payments import SUBSCRIPTION_PLANS


def language_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="English", callback_data="lang:en"),
        InlineKeyboardButton(text="Русский", callback_data="lang:ru"),
    ]])


def reset_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Reset", callback_data="action:reset")]
    ])

def buy_kb(lang: str) -> InlineKeyboardMarkup:
    buttons = []
    for key, plan in SUBSCRIPTION_PLANS.items():
        label = plan[f"label_{lang}"]
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"buy:{key}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def main_menu_kb(lang: str) -> ReplyKeyboardMarkup:
    msgs = load_messages(lang)
    return ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(text=msgs["signals_button"]),
            KeyboardButton(text=msgs["commands_button"]),
        ]],
        resize_keyboard=True
    )