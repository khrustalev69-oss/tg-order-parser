import os
import re
import time
import logging
import hashlib
import requests
from bs4 import BeautifulSoup
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

BOT_TOKEN  = os.environ.get("BOT_TOKEN", "")
FORWARD_TO = os.environ.get("FORWARD_TO", "@ygscors")
INTERVAL   = int(os.environ.get("INTERVAL", "120"))

GROUPS = [
    "Kinopeople",
    "jetlagchat",
    "cam_mtg",
    "mediaordersgeneratione",
    "theClapperChat",
]

KEYWORDS = [
    "монтаж",
    "съемка",
    "съёмка",
    "sde",
    "режиссер",
    "режиссёр",
    "оператор",
    "продюсер",
    "продакшн",
    "видеосъемка",
    "видеосъёмка",
    "режиссер монтажа",
    "режиссёр монтажа",
]

HASHTAGS = [
    "монтаж",
    "съемка",
    "съёмка",
    "режиссер",
    "оператор",
    "продюсер",
    "продакшн",
    "видеосъемка",
    "sde",
]

kw_re = re.compile("|".join(re.escape(k) for k in KEYWORDS), re.IGNORECASE)
ht_re = re.compile(r"#(" + "|".join(re.escape(h) for h in HASHTAGS) + r")\b", re.IGNORECASE)

seen_ids = set()
CHAT_ID_CACHE = {}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}


def get_chat_id():
    if "target" in CHAT_ID_CACHE:
        return CHAT_ID_CACHE["target"]
    # Use numeric ID directly if possible
    try:
        cid = int(FORWARD_TO)
        CHAT_ID_CACHE["target"] = cid
        log.info("Using direct chat_id: %s", cid)
        return cid
    except (ValueError, TypeError):
        pass
    # Fallback: resolve via sendMessage to self
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": FORWARD_TO, "text": "🤖 Parser bot started!"}, timeout=10
        )
        data = r.json()
        if data.get("ok"):
            cid = data["result"]["chat"]["id"]
            CHAT_ID_CACHE["target"] = cid
            log.info("Target chat_id resolved: %s", cid)
            return cid
        else:
            log.error("sendMessage failed: %s", data)
    except Exception as e:
        log.error("Error resolving chat_id: %s", e)
    return None


def send_notification(chat_id, group, text, link, triggers):
    short_text = text[:300] + ("..." if len(text) > 300 else "")
    msg = (
        f"🎬 <b>Найден заказ!</b>\n"
        f"📌 Группа: <b>{group}</b>\n"
        f"🏷 Триггеры: <code>{', '.join(triggers)}</code>\n"
        f"🕐 {datetime.now().strftime('%d.%m %H:%M')}\n\n"
        f"{short_text}\n\n"
        f'<a href="{link}">Открыть сообщение →</a>'
    )
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": msg,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            }, timeout=10
        )
        if r.json().get("ok"):
            log.info("✅ Sent notification for %s", group)
        else:
            log.error("Send error: %s", r.text)
    except Exception as e:
        log.error("sendMessage error: %s", e)


def scrape_group(group_name, chat_id):
    url = f"https://t.me/s/{group_name}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            log.warning("%s: HTTP %s", group_name, r.status_code)
            return

        soup = BeautifulSoup(r.text, "html.parser")
        messages = soup.select(".tgme_widget_message")

        if not messages:
            log.info("%s: no messages found (private or empty)", group_name)
            return

        new_count = 0
        for msg in messages:
            msg_id = msg.get("data-post", "")
            if not msg_id:
                continue

            uid = hashlib.md5(msg_id.encode()).hexdigest()
            if uid in seen_ids:
                continue
            seen_ids.add(uid)

            text_el = msg.select_one(".tgme_widget_message_text")
            if not text_el:
                continue
            text = text_el.get_text(separator=" ", strip=True)

            kw = kw_re.findall(text)
            ht = ht_re.findall(text)
            if not kw and not ht:
                continue

            triggers = list(set(kw + ["#" + h for h in ht]))
            link = f"https://t.me/{msg_id}"

            log.info("🎯 Match in %s | triggers: %s | text: %.80s",
                     group_name, triggers, text)

            send_notification(chat_id, group_name, text, link, triggers)
            new_count += 1

        log.info("%s: checked, %d new matches", group_name, new_count)

    except Exception as e:
        log.error("%s: scrape error: %s", group_name, e)


def main():
    log.info("🚀 Scraper started")
    log.info("Keywords: %s", KEYWORDS)
    log.info("Groups: %s", GROUPS)
    log.info("Interval: %ds", INTERVAL)

    chat_id = None
    while not chat_id:
        chat_id = get_chat_id()
        if not chat_id:
            log.warning("Cannot get chat_id, retrying in 30s...")
            time.sleep(30)

    log.info("✅ Ready! Monitoring %d groups", len(GROUPS))

    while True:
        for group in GROUPS:
            scrape_group(group, chat_id)
            time.sleep(3)
        log.info("⏳ Sleeping %ds...", INTERVAL)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
