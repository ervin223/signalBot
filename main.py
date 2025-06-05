import asyncio
import logging

from aiohttp import web
from aiogram import Bot
from aiogram import Dispatcher

from payments import create_app      # aiohttp-приложение с IPN-роутом
from handlers import register_handlers

logging.basicConfig(level=logging.INFO)
bot = Bot(token=__import__("os").getenv("TELEGRAM_TOKEN"))
dp  = Dispatcher()
register_handlers(dp, bot)

async def start_bot():
    logging.info("🟢 Telegram polling started")
    await dp.start_polling(bot)


async def start_ipn():
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8000)
    await site.start()
    logging.info("🟢 IPN server listening on port 8000")

async def main():
    await asyncio.gather(start_ipn(), start_bot())

if __name__ == "__main__":
    asyncio.run(main())
