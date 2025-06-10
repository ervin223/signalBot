import os
import logging
from aiogram import Bot
from db import get_conn
from locale_utils import load_messages

async def weekly_motivation_reminder(bot: Bot):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT user_id, language FROM users")
    users = cur.fetchall(); cur.close(); conn.close()

    for uid, lang in users:
        if not lang:
            lang = "en"
        msgs = load_messages(lang)
        try:
            await bot.send_message(
                uid,
                "📣 Не уверены в графике? 🧐 Подключите профессиональные сигналы и торгуйте уверенно! 💼🔥"
            )
        except Exception as e:
            logging.warning(f"Не удалось отправить weekly reminder {uid}: {e}")
