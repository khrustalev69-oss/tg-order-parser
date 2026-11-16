import os
import json
import asyncio
import logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError
from order_filter import classify_order

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("TG-Parser")

API_ID = 2496
API_HASH = "8da85b0d5bfe62527e5b244c209159c3"
SESSION_STRING = os.getenv(
    "SESSION_STRING",
    "1ApWapzMBu0ozeC189NHxq_1JkejTQi0Z2nQezs445iLWdc1mJsKjN1zy4K4s44sUwGCLO4ETNRDTcHKlY15GOB_Ue8IPxwWGkhGjcsu4bOTBBSyraYS1YGPYW_uAekAzMK6527-0nbBcXiAWIraGJDvU_HZLfKMCIu6LR4Tt30nMEH64xS8ZsM36iIcwm4XbrPLY4exLfIiAGU4tJUUWsLZgSPtvjSsfD8VRKz3ANRSUlsogHEf4-HErYrdASSqTYBwaoU2TwUueeWtHFZ0WasUX13Hx6JI364kcQU1W07P2bazuqlDQJtA-YKgqESfnItrctABawAJotIGGKKoyxkY7LLrPuEI="
)

# Получатели заказов (Денис и Алексей)
TARGETS = ["@ygscors", "@afedorovpro"]

# Каналы для мониторинга
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

SEEN_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seen_ids.json")

def load_seen_ids() -> set:
    if os.path.exists(SEEN_CACHE_FILE):
        try:
            with open(SEEN_CACHE_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception as e:
            logger.warning(f"Не удалось загрузить seen_ids: {e}")
    return set()

def save_seen_ids(seen_ids: set):
    try:
        ids_to_save = list(seen_ids)[-3000:]
        with open(SEEN_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(ids_to_save, f)
    except Exception as e:
        logger.warning(f"Не удалось сохранить seen_ids: {e}")

seen_ids = load_seen_ids()

def format_order_message(category: str, chat_title: str, post_link: str, text: str, trigger_word: str, max_len: int = 3500) -> str:
    header = (
        f"{category}\n"
        f"📍 <b>Источник:</b> {chat_title}\n"
        f"🎯 <b>Запрос:</b> <code>#{trigger_word}</code>\n"
    )
    if post_link:
        header += f"🔗 <a href=\"{post_link}\">Открыть сообщение в Telegram</a>\n"
    header += "────────────────────\n\n"
    
    available_text_len = max_len - len(header) - 50
    if len(text) > available_text_len:
        text = text[:available_text_len] + "\n\n<i>... [текст обрезан, полный текст по ссылке]</i>"
        
    return header + text

async def broadcast_order(client, message, category: str, chat_title: str, post_link: str, trigger_word: str):
    for target in TARGETS:
        try:
            if message.media and not getattr(message.media, "webpage", None):
                caption_text = format_order_message(category, chat_title, post_link, message.raw_text or "", trigger_word, max_len=1000)
                await client.send_message(
                    target,
                    caption_text,
                    file=message.media,
                    parse_mode="html",
                    link_preview=False
                )
            else:
                formatted_text = format_order_message(category, chat_title, post_link, message.raw_text or "", trigger_word, max_len=3500)
                await client.send_message(
                    target,
                    formatted_text,
                    parse_mode="html",
                    link_preview=False
                )
            logger.info(f"✅ Отправлен заказ в {target} [{category} / {chat_title}]")
            await asyncio.sleep(1.5)
        except FloodWaitError as e:
            logger.warning(f"FloodWait: спим {e.seconds} сек...")
            await asyncio.sleep(e.seconds + 2)
        except Exception as e:
            logger.error(f"❌ Ошибка отправки в {target}: {e}")

async def process_incoming_message(client, message):
    try:
        msg_id_key = f"{message.chat_id}_{message.id}"
        if msg_id_key in seen_ids:
            return
        seen_ids.add(msg_id_key)

        text = message.raw_text or ""
        is_order, category, trigger = classify_order(text)
        if not is_order:
            return

        chat = await message.get_chat()
        chat_title = getattr(chat, "title", None) or getattr(chat, "username", "Канал")
        username = getattr(chat, "username", None)
        post_link = f"https://t.me/{username}/{message.id}" if username else ""

        logger.info(f"🎯 НАЙДЕН РЕАЛЬНЫЙ ЗАКАЗ: [{category}] '{trigger}' в '{chat_title}'")
        await broadcast_order(client, message, category, chat_title, post_link, trigger)
        save_seen_ids(seen_ids)
        
    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения: {e}", exc_info=True)

async def seed_initial_messages(client):
    logger.info("Инициализация базы просмотренных сообщений...")
    for ch in SOURCE_CHANNELS:
        try:
            ent = await client.get_entity(ch)
            async for m in client.iter_messages(ent, limit=15):
                seen_ids.add(f"{m.chat_id}_{m.id}")
        except Exception as e:
            logger.debug(f"Ошибка сидинга {ch}: {e}")
    save_seen_ids(seen_ids)
    logger.info("✅ База обновлена. Бот мониторит новые заказы.")

async def polling_worker(client):
    await asyncio.sleep(10)
    logger.info("🔄 Фоновый периодический сканер запущен...")
    while True:
        try:
            for ch in SOURCE_CHANNELS:
                try:
                    ent = await client.get_entity(ch)
                    messages = await client.get_messages(ent, limit=5)
                    for m in reversed(messages):
                        await process_incoming_message(client, m)
                except Exception as e:
                    logger.debug(f"Временная ошибка опроса {ch}: {e}")
                await asyncio.sleep(2)
        except Exception as e:
            logger.warning(f"Ошибка в цикле сканера (сон 30с): {e}")
            await asyncio.sleep(30)
            continue
            
        await asyncio.sleep(45)

async def run_client_lifecycle():
    """
    Запускает TelegramClient с бесконечным авто-переподключением при обрывах связи / сне Мака.
    """
    while True:
        client = None
        try:
            logger.info("Инициализация Telegram-клиента (авто-реконнект включен)...")
            client = TelegramClient(
                StringSession(SESSION_STRING),
                API_ID,
                API_HASH,
                auto_reconnect=True,
                connection_retries=None,  # бесконечные повторные попытки при обрыве Wi-Fi
                retry_delay=5
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                logger.error("❌ Сессия не авторизована! Проверьте SESSION_STRING.")
                return

            me = await client.get_me()
            logger.info(f"🤖 Юзербот на связи: {me.first_name} (@{me.username}, ID: {me.id})")
            
            # Проверяем получателей
            active_targets = []
            for t in TARGETS:
                try:
                    ent = await client.get_entity(t)
                    active_targets.append(t)
                    logger.info(f"Получатель подтвержден: {t} (ID: {ent.id})")
                except Exception as e:
                    logger.error(f"Не удалось найти получателя {t}: {e}")

            # Инициализация кэша
            await seed_initial_messages(client)

            # Регистрация слушателя событий реального времени
            @client.on(events.NewMessage(chats=SOURCE_CHANNELS + ["@ygscors"]))
            async def real_time_handler(event):
                await process_incoming_message(client, event.message)

            # Фоновый поллер
            poll_task = asyncio.create_task(polling_worker(client))
            
            logger.info("✨ Парсер полностью активен и слушает входящие заказы!")
            
            # Ждем пока клиент на связи
            await client.run_until_disconnected()
            
        except (ConnectionError, OSError, asyncio.TimeoutError) as e:
            logger.warning(f"⚠️ Потеря интернет-соединения или сон Мака ({e}). Ожидание сети...")
            await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"⚠️ Ошибка в жизненном цикле клиента: {e}. Перезапуск через 10 сек...", exc_info=True)
            await asyncio.sleep(10)
        finally:
            if client:
                try:
                    await client.disconnect()
                except Exception:
                    pass

def main():
    asyncio.run(run_client_lifecycle())

if __name__ == "__main__":
    main()
