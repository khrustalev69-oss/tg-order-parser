import os
import re
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)

BOT_TOKEN  = os.environ["BOT_TOKEN"]
FORWARD_TO = os.environ.get("FORWARD_TO", "@ygscors")

KEYWORDS = [
    "заказ", "нужен", "нужна", "нужно", "ищу", "куплю",
    "требуется", "закажу", "хочу заказать", "сниму", "ищем",
    "срочно", "оплата", "бюджет", "hire", "нанимаю",
]
HASHTAGS = [
    "заказ", "заявка", "съёмка", "проект", "вакансия",
    "работа", "ищу", "нужен", "нужна",
]

kw_re = re.compile("|".join(re.escape(k) for k in KEYWORDS), re.IGNORECASE)
ht_re = re.compile(r"#(" + "|".join(re.escape(h) for h in HASHTAGS) + r")\b", re.IGNORECASE)

WATCH_USERNAMES = {
    "kinopeople", "jetlagchat", "cam_mtg",
    "mediaordersgeneratione", "theclapperChat",
}


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.channel_post
    if not msg:
        return

    chat = msg.chat
    uname = (chat.username or "").lower()
    if uname not in WATCH_USERNAMES:
        return

    text = msg.text or msg.caption or ""
    kw = kw_re.findall(text)
    ht = ht_re.findall(text)
    if not kw and not ht:
        return

    triggers = list(set(kw + ["#" + h for h in ht]))
    chat_name = chat.title or chat.username or str(chat.id)

    try:
        header = (
            f"🔔 <b>Новый заказ!</b>\n"
            f"📌 <b>{chat_name}</b>\n"
            f"🏷 <code>{', '.join(triggers)}</code>"
        )
        target = await context.bot.get_chat(FORWARD_TO)
        await context.bot.send_message(target.id, header, parse_mode="HTML")
        await context.bot.forward_message(target.id, msg.chat_id, msg.message_id)
        logger.info("Forwarded from %s | triggers: %s", chat_name, triggers)
    except Exception as e:
        logger.error("Forward error: %s", e)


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, handle))
    logger.info("Bot started, watching: %s", WATCH_USERNAMES)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
