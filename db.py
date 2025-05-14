import mysql.connector
from config import DB_CFG


def get_conn():
    return mysql.connector.connect(**DB_CFG)


def save_language(user_id: int, lang: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (user_id, language) VALUES (%s, %s) "
        "ON DUPLICATE KEY UPDATE language = %s",
        (user_id, lang, lang)
    )
    conn.commit()
    cur.close()
    conn.close()
