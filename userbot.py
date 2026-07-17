"""
Telegram Userbot — парсер заказов
Работает от имени второго аккаунта (Denis), пересылает на первый.
"""
import os
import re
import logging
from urllib.parse import urlparse
from telethon import TelegramClient, events
from telethon.sessions import StringSession

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

API_ID = int(os.environ.get("TELEGRAM_API_ID", "2496"))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "8da85b0d5bfe62527e5b244c209159c3").strip()

SESSION  = os.environ.get("SESSION_STRING", "")
FORWARD_TO_RAW = os.environ.get("FORWARD_TO", "1900772820").strip().strip('"').strip("'")
SOCKS_PROXY = os.environ.get("SOCKS_PROXY", "").strip()

WATCH_CHATS = {
    "kinopeople",
    "jetlagchat",
    "cam_mtg",
    "mediaordersgeneratione",
    "theclapperchat",
}

# Топики которые нужно ИГНОРИРОВАТЬ
EXCLUDED_TOPICS = [
    "портфолио",
    "резюме",
    "portfolio",
]

# Хэштеги/слова в тексте → пропускаем (это чужое резюме/портфолио, не заказ)
EXCLUDED_HASHTAGS = [
    "#портфолио",
    "#резюме",
    "#portfolio",
    "#обомне",
    "#обо_мне",
]

# Если сообщение начинается с этих слов — это самопрезентация, не заказ
EXCLUDED_STARTS = [
    "меня зовут",
    "привет, я ",
    "привет! я ",
    "я оператор",
    "я режиссер",
    "я режиссёр",
    "я монтажер",
    "я монтажёр",
    "я продюсер",
    "предлагаю услуги",
    "ищу работу",
    "ищу проекты",
    "открыт к проектам",
    "открыта к проектам",
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

if not SESSION:
    raise RuntimeError("SESSION_STRING is required")


def resolve_proxy():
    if not SOCKS_PROXY:
        return None

    parsed = urlparse(SOCKS_PROXY)
    if parsed.scheme not in {"socks5", "socks4"} or not parsed.hostname or not parsed.port:
        raise RuntimeError("SOCKS_PROXY must look like socks5://host:port")

    return (
        parsed.scheme,
        parsed.hostname,
        parsed.port,
        True,
        parsed.username,
        parsed.password,
    )


client = TelegramClient(StringSession(SESSION), API_ID, API_HASH, proxy=resolve_proxy())


def resolve_forward_target():
    if re.fullmatch(r"-?\d+", FORWARD_TO_RAW):
        return int(FORWARD_TO_RAW)
    return FORWARD_TO_RAW.lstrip("@")


@client.on(events.NewMessage())
async def handler(event):
    chat = await event.get_chat()
    username = (getattr(chat, "username", None) or "").lower()
    if username not in WATCH_CHATS:
        return

    # Проверяем — не из запрещённого топика ли сообщение
    if event.message.reply_to and hasattr(event.message.reply_to, 'reply_to_top_id'):
        top_id = event.message.reply_to.reply_to_top_id
        if top_id:
            try:
                topic_msg = await client.get_messages(event.chat_id, ids=top_id)
                if topic_msg and hasattr(topic_msg, 'action') and hasattr(topic_msg.action, 'title'):
                    title = topic_msg.action.title.lower()
                    for excl in EXCLUDED_TOPICS:
                        if excl in title:
                            log.debug("Skipping topic: %s", topic_msg.action.title)
                            return
            except Exception:
                pass

    text = event.message.text or event.message.message or ""

    # Пропускаем если в тексте есть стоп-хэштеги (это портфолио/резюме)
    text_lower = text.lower()
    for tag in EXCLUDED_HASHTAGS:
        if tag in text_lower:
            log.debug("Skipping: excluded hashtag %s", tag)
            return

    # Пропускаем самопрезентации
    for start in EXCLUDED_STARTS:
        if text_lower.startswith(start):
            log.debug("Skipping: self-presentation")
            return

    kw = kw_re.findall(text)
    ht = ht_re.findall(text)
    if not kw and not ht:
        return

    triggers = list(set(kw + ["#" + h for h in ht]))
    chat_name = getattr(chat, "title", None) or getattr(chat, "username", str(chat.id))
    log.info("✅ Match in %s | triggers: %s", chat_name, triggers)

    header = (
        f"🎬 <b>Новый заказ!</b>\n"
        f"📌 <b>{chat_name}</b>\n"
        f"🏷 <code>{', '.join(triggers)}</code>"
    )
    forward_target = resolve_forward_target()
    await client.send_message(forward_target, header, parse_mode="html")
    await client.forward_messages(forward_target, event.message)


async def main():
    await client.start()
    me = await client.get_me()
    log.info("🚀 Userbot запущен как %s (@%s)", me.first_name, me.username)
    log.info("👀 Слежу за: %s", WATCH_CHATS)
    # Отправляем тестовое сообщение при старте
    try:
        await client.send_message(resolve_forward_target(),
            "✅ <b>Userbot запущен!</b>\n"
            f"👤 Аккаунт: {me.first_name} (@{me.username})\n"
            "👀 Мониторю группы:\n" +
            "\n".join(f"• {g}" for g in WATCH_CHATS) +
            "\n\n🔑 Ключевых слов: " + str(len(KEYWORDS)),
            parse_mode="html"
        )
        log.info("✅ Test message sent!")
    except Exception as e:
        log.error("Test message error: %s", e)
    await client.run_until_disconnected()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
