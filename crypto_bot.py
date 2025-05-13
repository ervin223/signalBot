import logging
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.utils import executor
import mysql.connector
import json
from dotenv import load_dotenv
import os

# Загружаем переменные из .env файла
load_dotenv()

# Токен бота и данные для подключения к базе данных из .env файла
API_TOKEN = os.getenv("TELEGRAM_TOKEN")
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Создание экземпляра бота и диспетчера
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# Подключение к базе данных MySQL
def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )

# Функция для загрузки сообщений в зависимости от выбранного языка
def load_messages(language="en"):
    with open(f'locales/{language}.json', 'r', encoding='utf-8') as file:
        return json.load(file)

# Словарь для хранения текущего языка пользователя
user_languages = {}

# Начало работы с ботом
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    # Проверяем, выбрал ли пользователь язык
    user_id = message.from_user.id
    if user_id not in user_languages:
        await message.reply("Please choose your language: /en for English or /ru for Russian.")
        return

    language = user_languages[user_id]
    messages = load_messages(language)
    await message.reply(messages['start_message'])

# Обработчик выбора языка
@dp.message_handler(commands=['en', 'ru'])
async def choose_language(message: types.Message):
    user_id = message.from_user.id
    language = message.text[1:]  # Извлекаем язык из команды
    if language not in ['en', 'ru']:
        return

    user_languages[user_id] = language
    messages = load_messages(language)
    await message.reply(messages['choose_language'])

# Регистрация пользователя
@dp.message_handler()
async def register(message: types.Message):
    user_id = message.from_user.id

    if user_id not in user_languages:
        await message.reply("You didn't choose a language. Please choose your language first.")
        return

    language = user_languages[user_id]
    messages = load_messages(language)

    # Если пользователь еще не выбрал язык, он будет перенаправлен к выбору
    if ',' not in message.text:
        await message.reply(messages['register_prompt'])
        return

    user_input = message.text.split(',')
    if len(user_input) == 2:
        username = user_input[0].strip()
        email = user_input[1].strip()

        # Сохраняем данные в базу данных
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("INSERT INTO users (username, email) VALUES (%s, %s)", (username, email))
        connection.commit()
        cursor.close()
        connection.close()

        await message.reply(messages['registration_success'].format(username=username, email=email))
    else:
        await message.reply(messages['register_prompt'])

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
