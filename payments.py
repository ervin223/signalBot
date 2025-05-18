# payments.py

import os
import hmac
import hashlib
import logging

import httpx
from aiohttp import web
from aiogram import Bot

from db import get_conn

# ─── Configuration ────────────────────────────────────────────────────────────
# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

API_KEY      = os.getenv("NOWPAYMENTS_API_KEY")
IPN_SECRET   = os.getenv("NOWPAYMENTS_IPN_SECRET")
IPN_CALLBACK = os.getenv("NOWPAYMENTS_IPN_URL")   # должен включать путь /nowpayments/ipn
BASE_URL     = "https://api.nowpayments.io/v1"

# Инициализация бота для отправки уведомлений
bot = Bot(token=os.getenv("TELEGRAM_TOKEN"))

# ─── Создание счёта (invoice) в NOWPayments ───────────────────────────────────
async def create_invoice(amount: float, currency: str = "USD", order_id: str = None) -> dict:
    """
    Создаёт счёт в NOWPayments и возвращает ответ API.
    order_id обычно равен строковому Telegram user_id.
    """
    payload = {
        "price_amount":      amount,
        "price_currency":    currency,
        "order_id":          order_id,
        "order_description": "Subscription",
        "ipn_callback_url":  IPN_CALLBACK
    }
    headers = {
        "x-api-key":    API_KEY,
        "Content-Type": "application/json"
    }

    logging.info(f"Creating NOWPayments invoice for order_id={order_id}, amount={amount} {currency}")
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{BASE_URL}/invoice", json=payload, headers=headers)
        resp.raise_for_status()
        invoice = resp.json()
        logging.info(f"Invoice created: {invoice}")
        return invoice

# ─── Обработчик webhook’ов IPN от NOWPayments ─────────────────────────────────
async def handle_ipn(request: web.Request) -> web.Response:
    """
    Вебхук для обработки IPN-уведомлений от NOWPayments.
    При статусе payment_status == "finished" активирует подписку в БД
    и отправляет сообщение в Telegram.
    """
    raw_body = await request.read()
    try:
        data = await request.json()
    except Exception:
        logging.exception("Failed to parse JSON from IPN")
        return web.Response(status=400, text="Bad JSON")

    sig_hdr = request.headers.get("x-nowpayments-signature", None)
    logging.info("=== NOWPayments IPN received ===")
    logging.info("Headers: %s", dict(request.headers))
    logging.info("Raw body: %s", raw_body)
    logging.info("Parsed JSON: %s", data)
    logging.info("Signature header: %s", sig_hdr)

    # === Опциональная проверка подписи HMAC-SHA512 ===
    # if not sig_hdr:
    #     logging.warning("Missing signature header – rejecting")
    #     return web.Response(status=400, text="No signature")
    #
    # expected = hmac.new(IPN_SECRET.encode(), raw_body, hashlib.sha512).hexdigest()
    # if not hmac.compare_digest(expected, sig_hdr):
    #     logging.warning("Bad IPN signature – rejecting")
    #     return web.Response(status=400, text="Invalid signature")
    # ================================================

    # Активируем подписку при успешной оплате
    if data.get("payment_status") == "finished":
        try:
            user_id = int(data.get("order_id", 0))
            logging.info(f"Activating subscription for user_id={user_id}")

            conn = get_conn()
            cur  = conn.cursor()
            cur.execute(
                """
                UPDATE users
                   SET is_subscribed = 1,
                       subscription_until = DATE_ADD(NOW(), INTERVAL 30 DAY)
                 WHERE user_id = %s
                """,
                (user_id,)
            )
            conn.commit()
            rows = cur.rowcount
            cur.close()
            conn.close()
            logging.info(f"Database updated, rows affected: {rows}")

            # Отправляем уведомление в Telegram
            await bot.send_message(
                user_id,
                "🎉 Оплата прошла успешно! Ваша подписка активирована на 30 дней."
            )
            logging.info(f"Sent confirmation message to {user_id}")

        except Exception:
            logging.exception("Error while activating subscription")

    # Возвращаем OK, чтобы NOWPayments не повторял попытки
    return web.Response(text="OK")
