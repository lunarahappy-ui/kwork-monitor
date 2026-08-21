#!/usr/bin/env python3
"""
Мониторинг новых заказов на Kwork.ru по ключевым словам/категориям.
"""

import json
import os
import sys
from pathlib import Path

import requests

DEFAULT_CATEGORIES = ["41"]
CATEGORIES = os.getenv("KWORK_CATEGORIES", ",".join(DEFAULT_CATEGORIES)).split(",")

KEYWORDS = [
    "телеграм", "телеграмм", "telegram", "тг бот", "чат-бот", "чатбот",
    "лендинг", "landing",
    "сайт", "website", "веб-сайт", "вебсайт",
]

PAGES_PER_CATEGORY = 2
STATE_FILE = Path(__file__).parent / "seen_ids.json"
KWORK_PROJECTS_URL = "https://kwork.ru/projects"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://kwork.ru",
    "Referer": "https://kwork.ru/projects",
}

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def load_seen_ids() -> set:
    if STATE_FILE.exists():
        try:
            return set(json.loads(STATE_FILE.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            return set()
    return set()


def save_seen_ids(ids: set) -> None:
    STATE_FILE.write_text(json.dumps(sorted(ids)), encoding="utf-8")


def fetch_page(category_id: str, page: int) -> list:
    response = requests.post(
        KWORK_PROJECTS_URL,
        data={"c": category_id, "page": page},
        headers=HEADERS,
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data", payload)
    return data.get("wants", [])


def matches_keywords(order: dict) -> bool:
    text = f"{order.get('name', '')} {order.get('description', '')}".lower()
    return any(keyword.lower() in text for keyword in KEYWORDS)


def format_message(order: dict) -> str:
    title = order.get("name", "Без названия")
    url = f"https://kwork.ru/projects/{order.get('id')}/view"
    price = order.get("priceLimit") or order.get("possiblePriceLimit") or "не указан"
    description = (order.get("description") or "").strip()
    if len(description) > 300:
        description = description[:300].rstrip() + "…"
    return f"🆕 {title}\nБюджет: {price} ₽\n{description}\n{url}"


def send_telegram(text: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[!] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID не заданы — печатаю в консоль:\n")
        print(text)
        print("-" * 40)
        return
    resp = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "disable_web_page_preview": "false"},
        timeout=15,
    )
    if not resp.ok:
        print(f"[!] Ошибка отправки в Telegram: {resp.status_code} {resp.text}", file=sys.stderr)


def main() -> None:
    seen_ids = load_seen_ids()
    first_run = len(seen_ids) == 0
    new_seen = set(seen_ids)
    found_new = []

    for category_id in CATEGORIES:
        category_id = category_id.strip()
        if not category_id:
            continue
        try:
            for page in range(1, PAGES_PER_CATEGORY + 1):
                wants = fetch_page(category_id, page)
                if not wants:
                    break
                for order in wants:
                    order_id = order.get("id")
                    if order_id is None:
                        continue
                    new_seen.add(order_id)
                    if order_id in seen_ids:
                        continue
                    if matches_keywords(order):
                        found_new.append(order)
        except requests.RequestException as exc:
            print(f"[!] Ошибка запроса для категории {category_id}: {exc}", file=sys.stderr)

    save_seen_ids(new_seen)

    if first_run:
        print(f"Первый запуск: сохранено {len(new_seen)} уже существующих заказов, ждём новых.")
        return

    if not found_new:
        print("Новых подходящих заказов не найдено.")
        return

    print(f"Найдено новых подходящих заказов: {len(found_new)}")
    for order in found_new:
        send_telegram(format_message(order))


if __name__ == "__main__":
    main()
