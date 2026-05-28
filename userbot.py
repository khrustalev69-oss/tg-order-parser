"""
Telegram Userbot — парсер заказов
Работает от имени второго аккаунта (Denis), пересылает на первый.
"""
import os
import re
import logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

# Telegram Web credentials (official app)
API_ID   = 2496
API_HASH = "8da85b0d5bfe62527e5b244c209159c3"

SESSION  = os.environ.get("SESSION_STRING", "")
FORWARD_TO = int(os.environ.get("FORWARD_TO", "1900772820").strip('"').strip("'"))

WATCH_CHATS = [
    "Kinopeople",
    "jetlagchat",
    "cam_mtg",
    "mediaordersgeneratione",
    "theClapperChat",
]

KEYWORDS = [
    "монтаж", "съемка", "съёмка", "sde",
    "режиссер", "режиссёр", "оператор",
    "продюсер", "продакшн", "видеосъемка",
    "видеосъёмка", "режиссер монтажа", "режиссёр монтажа",
    "рекламный ролик", "клип", "интервью", "репортаж",
    "документалка", "корпоратив", "стриминг",
    "прямой эфир", "livestream",
]

HASHTAGS = [
    "монтаж", "съемка", "съёмка", "режиссер",
    "оператор", "продюсер", "продакшн", "sde",
]

kw_re = re.compile("|".join(re.escape(k) for k in KEYWORDS), re.IGNORECASE)
ht_re = re.compile(r"#(" + "|".join(re.escape(h) for h in HASHTAGS) + r")\b", re.IGNORECASE)

client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)


@client.on(events.NewMessage(chats=WATCH_CHATS))
async def handler(event):
    text = event.message.text or event.message.message or ""
    kw = kw_re.findall(text)
    ht = ht_re.findall(text)
    if not kw and not ht:
        return

    triggers = list(set(kw + ["#" + h for h in ht]))
    chat = await event.get_chat()
    chat_name = getattr(chat, "title", None) or getattr(chat, "username", str(chat.id))
    log.info("✅ Match in %s | triggers: %s", chat_name, triggers)

    header = (
        f"🎬 <b>Новый заказ!</b>\n"
        f"📌 <b>{chat_name}</b>\n"
        f"🏷 <code>{', '.join(triggers)}</code>"
    )
    await client.send_message(FORWARD_TO, header, parse_mode="html")
    await client.forward_messages(FORWARD_TO, event.message)


async def main():
    await client.start()
    me = await client.get_me()
    log.info("🚀 Userbot запущен как %s (@%s)", me.first_name, me.username)
    log.info("👀 Слежу за: %s", WATCH_CHATS)
    await client.run_until_disconnected()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
