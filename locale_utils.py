import json


def load_messages(lang: str) -> dict:
    with open(f"locales/{lang}.json", encoding="utf-8") as f:
        return json.load(f)