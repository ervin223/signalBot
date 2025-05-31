import os
import time
import logging
import httpx
import uuid
from aiohttp import web
from aiogram import Bot
from db import get_conn

# ─── Конфиг ────────────────────────────────────────────────────────────────────
API_KEY        = os.getenv("NOWPAYMENTS_API_KEY")
ADMIN_EMAIL    = os.getenv("NOWPAYMENTS_ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("NOWPAYMENTS_ADMIN_PASSWORD")
IPN_SECRET     = os.getenv("NOWPAYMENTS_IPN_SECRET")
IPN_ROUTE      = "/nowpayments/ipn"
BOT_TOKEN      = os.getenv("TELEGRAM_TOKEN")
BASE_URL       = "https://api.nowpayments.io/v1"
PLAN_ID        = os.getenv("NOWPAYMENTS_PLAN_ID")

SUBSCRIPTION_PLANS = {
    "monthly":     {"id": os.getenv("PLAN_ID_MONTHLY"), "label_ru": "📆 Месяц ($20)",      "label_en": "📆 1 Month ($20)"},
    "quarterly":   {"id": os.getenv("PLAN_ID_QUARTERLY"), "label_ru": "📅 3 месяца ($50)", "label_en": "📅 3 Months ($50)"},
    "yearly":      {"id": os.getenv("PLAN_ID_YEARLY"), "label_ru": "📈 Год ($120)",        "label_en": "📈 1 Year ($120)"},
    "lifetime":    {"id": os.getenv("PLAN_ID_LIFETIME"), "label_ru": "♾️ Навсегда ($300)", "label_en": "♾️ Lifetime ($300)"}
}


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
bot = Bot(token=BOT_TOKEN)

# ─── JWT-кэш ──────────────────────────────────────────────────────────────────
_jwt_cache = {"token": None, "expires": 0}

async def _get_jwt() -> str:
    now = time.time()
    if _jwt_cache["token"] and now < _jwt_cache["expires"] - 30:
        return _jwt_cache["token"]

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/auth",
            headers={
                "x-api-key": API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "email":    ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            },
            timeout=10.0
        )
        resp.raise_for_status()
        token = resp.json().get("token")
        _jwt_cache["token"]   = token
        _jwt_cache["expires"] = now + 5*60
        logging.info("🔑 Acquired JWT")
        return token

async def create_email_subscription(email: str, plan_id: str) -> dict:
    jwt = await _get_jwt()
    payload = {
        "subscription_plan_id": plan_id,
        "email": email
    }
    headers = {
        "Authorization": f"Bearer {jwt}",
        "x-api-key": API_KEY,
        "Content-Type": "application/json"
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{BASE_URL}/subscriptions", json=payload, headers=headers)
        resp.raise_for_status()
        result = resp.json()["result"][0]
        return result  # содержит id

    
async def fetch_subscription_invoices(subscription_id: str) -> list[dict]:
    jwt = await _get_jwt()
    headers = {
        "Authorization": f"Bearer {jwt}",
        "x-api-key":     API_KEY
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{BASE_URL}/subscriptions/{subscription_id}/invoices",
            headers=headers,
            timeout=10.0
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
        return data.get("result", [])

# ─── Обработчик webhook IPN ──────────────────────────────────────────────────
async def handle_ipn(request: web.Request) -> web.Response:
    raw = await request.read()
    try:
        data = await request.json()
    except Exception:
        logging.exception("❌ Failed to parse IPN JSON")
        return web.Response(status=400, text="Bad JSON")

    logging.info("📩 === IPN RECEIVED ===")
    logging.info("📩 Headers: %s", dict(request.headers))
    logging.info("📩 Body: %s", data)

    # Получаем статус и ID подписки
    status = data.get("payment_status") or data.get("status")
    sub_id = data.get("subscription_id") or data.get("id")

    if not sub_id:
        logging.warning("❌ Нет subscription_id в IPN")
        return web.Response(status=400, text="No subscription_id")

    if status in ("finished", "PAID"):
        conn = get_conn(); cur = conn.cursor()

        # Проверка: есть ли такая подписка
        cur.execute("SELECT user_id FROM subscriptions WHERE subscription_id = %s", (sub_id,))
        row = cur.fetchone()

        if not row:
            logging.warning(f"❌ Unknown subscription: {sub_id}")
            cur.close(); conn.close()
            return web.Response(text="Unknown subscription")

        user_id = row[0]

        # Обновление подписки
        cur.execute("""
            UPDATE subscriptions
               SET status     = 'ACTIVE',
                   expire_at  = DATE_ADD(NOW(), INTERVAL 30 DAY),
                   updated_at = NOW()
             WHERE subscription_id = %s
        """, (sub_id,))
        conn.commit()
        cur.close(); conn.close()

        # Отправка сообщения
        await bot.send_message(user_id, "✅ Ваша подписка успешно активирована!")

    return web.Response(text="OK")




# ─── Создание aiohttp-приложения для IPN ──────────────────────────────────────
def create_app() -> web.Application:
    app = web.Application()
    app.router.add_post(IPN_ROUTE, handle_ipn)
    logging.info("🟢 IPN app ready on %s", IPN_ROUTE)
    return app
