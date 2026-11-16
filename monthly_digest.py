import os
import json
import asyncio
from datetime import datetime, timezone
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = 2496
API_HASH = "8da85b0d5bfe62527e5b244c209159c3"
SESSION_STRING = os.getenv(
    "SESSION_STRING",
    "1ApWapzMBu0ozeC189NHxq_1JkejTQi0Z2nQezs445iLWdc1mJsKjN1zy4K4s44sUwGCLO4ETNRDTcHKlY15GOB_Ue8IPxwWGkhGjcsu4bOTBBSyraYS1YGPYW_uAekAzMK6527-0nbBcXiAWIraGJDvU_HZLfKMCIu6LR4Tt30nMEH64xS8ZsM36iIcwm4XbrPLY4exLfIiAGU4tJUUWsLZgSPtvjSsfD8VRKz3ANRSUlsogHEf4-HErYrdASSqTYBwaoU2TwUueeWtHFZ0WasUX13Hx6JI364kcQU1W07P2bazuqlDQJtA-YKgqESfnItrctABawAJotIGGKKoyxkY7LLrPuEI="
)

SOURCE_CHANNELS = [
    "@platform_film",
    "@vktvru",
    "@cinema_works",
    "@theclapperchat",
    "@kinopeople",
    "@jetlagchat",
    "@cam_mtg",
    "@mediaordersgeneratione"
]

KEYWORDS = [
    "монтаж", "монтажер", "монтажёр", "режиссер", "режиссёр", "продакшн", "production",
    "съемка", "съёмка", "оператор", "продюсер", "клип", "подкаст", "интервью",
    "документ", "док.", "ролик", "реклама", "корпоратив", "davinci", "premiere",
    "постпродакшн", "видео", "сценарист", "заказ", "ищем", "требуется"
]

STOP_WORDS = [
    "казино", "1win", "крипт", "слив курса", "ставка", "заработок от", "пассивный доход"
]

START_DATE = datetime(2026, 11, 1, tzinfo=timezone.utc)

def is_order(text: str):
    if not text:
        return False, []
    text_lower = text.lower()
    if any(sw in text_lower for sw in STOP_WORDS):
        return False, []
    matched = [kw for kw in KEYWORDS if kw in text_lower]
    return len(matched) > 0, matched

async def collect():
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await client.connect()
    
    all_orders = []
    print(f"🔍 Начинаем сбор заказов с {START_DATE.strftime('%Y-%m-%d')} по каналам...")
    
    for ch in SOURCE_CHANNELS:
        try:
            ent = await client.get_entity(ch)
            title = getattr(ent, "title", ch)
            username = getattr(ent, "username", None)
            print(f"⏳ Сканируем: {title} ({ch})...")
            
            count_channel = 0
            # Итерируемся по сообщениям до начала месяца
            async for msg in client.iter_messages(ent, limit=400):
                if msg.date < START_DATE:
                    break
                text = msg.raw_text or ""
                ok, matched = is_order(text)
                if ok:
                    link = f"https://t.me/{username}/{msg.id}" if username else ""
                    all_orders.append({
                        "channel": title,
                        "username": username,
                        "date": msg.date.strftime("%Y-%m-%d %H:%M"),
                        "link": link,
                        "keywords": matched,
                        "text": text
                    })
                    count_channel += 1
                    
            print(f"  -> Найдено заказов в {title}: {count_channel}")
            await asyncio.sleep(1)
        except Exception as e:
            print(f"❌ Ошибка при сканировании {ch}: {e}")
            
    print(f"\n🎉 Всего собрано релевантных заказов за этот месяц: {len(all_orders)}")
    
    # Сохраняем в JSON
    output_json = "/tmp/monthly_orders.json"
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(all_orders, f, ensure_ascii=False, indent=2)
    print(f"💾 Данные сохранены в {output_json}")
    
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(collect())
