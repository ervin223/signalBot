import os
import logging
from aiogram import Bot
from db import get_conn
from locale_utils import load_messages
from payments import SUBSCRIPTION_PLANS
from keyboards import buy_kb



async def remind_unpaid_users(bot: Bot):  
    conn = get_conn()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT u.user_id, u.language FROM users u
        LEFT JOIN (
            SELECT user_id, MAX(expire_at) AS max_exp
            FROM subscriptions
            WHERE status = 'ACTIVE' AND expire_at > NOW()
            GROUP BY user_id
        ) s ON u.user_id = s.user_id
        WHERE s.max_exp IS NULL
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()

    for user_id, lang in rows:
        if not lang:
            lang = "en"
        msgs = load_messages(lang)
        try:
            await bot.send_message(
                user_id,
                text=msgs["pay_prompt_not"],
                reply_markup=buy_kb(lang)
            )
            print(f"✅ Отправлено {user_id}")
        except Exception as e:
            logging.warning(f"❌ Не удалось отправить {user_id}: {e}")
