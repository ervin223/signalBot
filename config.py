import os
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

API_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not API_TOKEN:
    logging.error("Missing TELEGRAM_TOKEN in .env")
    exit(1)

DB_CFG = {
    "host":     os.getenv("DB_HOST"),
    "port":     int(os.getenv("DB_PORT", "3306")),
    "user":     os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
}

# Logging configuration
logging.basicConfig(level=logging.INFO)