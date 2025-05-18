# main.py

import os
from dotenv import load_dotenv

# ─── Load .env as early as possible ─────────────────────────────────────────
load_dotenv(override=True)

import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

# Включаем логгирование для aiohttp и вашего кода
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from handlers import register_handlers
from payments import handle_ipn

API_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not API_TOKEN:
    logger.error("TELEGRAM_TOKEN is missing in .env")
    exit(1)

# ─── Init bot & dispatcher ───────────────────────────────────────────────────
bot = Bot(token=API_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())
register_handlers(dp)

# ─── Telegram polling ────────────────────────────────────────────────────────
async def run_bot():
    logger.info("Starting Telegram polling…")
    await dp.start_polling(bot)

# ─── NOWPayments IPN webhook ─────────────────────────────────────────────────
async def run_webhook():
    app = web.Application()
    app.router.add_post('/nowpayments/ipn', handle_ipn)
    runner = web.AppRunner(app)
    app.router.add_get('/health', lambda request: web.Response(text="OK"))
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8000)
    await site.start()
    logger.info("NOWPayments IPN server running on port 8000")

# ─── Главная корутина ────────────────────────────────────────────────────────
async def main():
    await asyncio.gather(
        run_bot(),
        run_webhook()
    )

if __name__ == "__main__":
    asyncio.run(main())
