"""Monitor public Telegram groups without a Telegram user API session.

The scraper reads Telegram's public message widget pages, filters hiring posts,
and sends matching text and a source link through a regular BotFather bot.
"""

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

import httpx
from telegram.ext import Application


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


@dataclass(frozen=True)
class Source:
    username: str
    title: str
    initial_message_id: int


# These IDs were captured immediately before enabling the scraper. On its first
# launch it starts after them, so an old chat archive is not sent to the user.
SOURCES = (
    Source("kinopeople", "Работники Кино Pro", 381360),
    Source("jetlagchat", "JETLAG CHAT", 215141),
    Source("cam_mtg", "Операторы и монтажеры", 8418),
    Source("mediaordersgeneratione", "MOG - Медиа Заказы", 3199),
    Source("theclapperchat", "The Clapper", 95883),
)

INTENT_WORDS = (
    "ищу", "ищем", "нужен", "нужна", "нужны", "нужно", "требуется",
    "требуются", "в поиске", "ищется", "вакансия", "заказ", "бюджет",
    "оплата", "ставка", "нанимаем", "приглашаем",
)
NICHE_WORDS = (
    "монтаж", "монтажер", "монтажёр", "съемка", "съёмка", "оператор",
    "режиссер", "режиссёр", "продюсер", "продакшн", "видеограф",
    "видеосъемка", "видеосъёмка", "видео", "ролик", "рилс", "reels",
    "motion", "моушн", "vfx", "sde", "клип", "интервью", "репортаж",
    "стрим", "прямой эфир", "сценарист",
)
EXCLUDED_MARKERS = (
    "#портфолио", "#резюме", "#portfolio", "#обомне", "#обо_мне",
    "#помогу", "#ищуработу", "предлагаю услуги", "оказываю услуги",
    "беру заказы", "мои услуги",
)
EXCLUDED_STARTS = (
    "меня зовут", "привет, я ", "привет! я ", "всем привет! я ",
    "всем привет, я ", "я оператор", "я режиссер", "я режиссёр",
    "я монтажер", "я монтажёр", "я продюсер", "я видеограф",
    "ищу работу", "ищу проекты", "открыт к проектам", "открыта к проектам",
    "хочешь монтаж", "нужен монтаж, но",
)


def compile_terms(words: tuple[str, ...]) -> re.Pattern[str]:
    alternatives = "|".join(re.escape(word) for word in sorted(words, key=len, reverse=True))
    return re.compile(r"(?<!\w)(?:" + alternatives + r")(?!\w)", re.IGNORECASE)


INTENT_RE = compile_terms(INTENT_WORDS)
NICHE_RE = compile_terms(NICHE_WORDS)

HIRING_TARGET_PATTERN = (
    r"(?:видеограф\w*|монтаж(?:ер|ёр)?\w*|оператор\w*|режисс(?:ер|ёр)\w*|"
    r"продюсер\w*|сценарист\w*|продакшн\w*|видеосъ[её]мк\w*|"
    r"съ[её]мк\w*|видео\w*|ролик\w*|рилс\w*|reels\w*|motion\w*|"
    r"моушн\w*|vfx\w*|sde\w*|клип\w*|интервью\w*|репортаж\w*|"
    r"стрим\w*|прям(?:ой|ого|ому|ым)\s+эфир\w*)"
)

HIRING_RE = re.compile(
    r"(?<!\w)(?:ищу|ищем|нужен|нужна|нужны|нужно|требуется|требуются|"
    r"нанимаем|приглашаем|в\s+поиске)(?!\w)[^\n.!?]{0,80}"
    r"(?<!\w)" + HIRING_TARGET_PATTERN + r"(?!\w)"
    r"|(?<!\w)" + HIRING_TARGET_PATTERN + r"(?!\w)"
    r"[^\n.!?]{0,40}(?<!\w)(?:нужен|нужна|нужны|требуется|требуются)(?!\w)"
    r"|(?<!\w)(?:вакансия|заказ)(?!\w)[^\n.!?]{0,80}"
    r"(?<!\w)" + HIRING_TARGET_PATTERN + r"(?!\w)",
    re.IGNORECASE,
)

SELF_PROMO_RE = re.compile(
    r"(?<!\w)(?:смонтирую|монтирую)(?!\w)"
    r"|(?<!\w)(?:ищу|ищем)\s+(?:новых\s+)?(?:клиентов|заказы|работу|проекты)(?!\w)"
    r"|(?<!\w)в\s+поиске[^\n.!?]{0,35}(?:проектов|заказов|клиентов)(?!\w)"
    r"|(?<!\w)(?:мои|моё|мое)\s+(?:работы|кейсы|портфолио)(?!\w)"
    r"|(?<!\w)примеры\s+(?:моих\s+)?работ(?!\w)"
    r"|(?<!\w)я\s+(?:занимаюсь|начинающий|начинающая|монтажер|монтажёр|видеограф)(?!\w)"
    r"|(?<!\w)работаю\s+в\s+(?:capcut|premiere|after\s+effects|davinci|blender)(?!\w)"
    r"|(?<!\w)(?:обращайтесь|буду\s+рад(?:а)?\s+сотрудничеству)(?!\w)"
    r"|(?<!\w)если\s+(?:(?:вам|кому-то)\s+)?нуж(?:ен|на|ны|но)(?!\w)"
    r"|(?<!\w)ищете[^\n.!?]{0,50}\?",
    re.IGNORECASE,
)


class TelegramWidgetParser(HTMLParser):
    """Extract message text and distinguish a message from a not-found page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.exists = False
        self._capture_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())

        if "tgme_widget_message" in classes and "err_message" not in classes:
            self.exists = True

        if "tgme_widget_message_text" in classes:
            self._capture_depth = 1
            return

        if self._capture_depth:
            if tag == "br":
                self._parts.append("\n")
                return
            if tag not in {"img", "input", "meta", "link", "hr"}:
                self._capture_depth += 1
            if tag in {"p", "div"}:
                self._parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._capture_depth and tag == "br":
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._capture_depth:
            self._capture_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._capture_depth:
            self._parts.append(data)

    @property
    def text(self) -> str:
        value = "".join(self._parts).replace("\xa0", " ")
        value = re.sub(r"[ \t]+\n", "\n", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
        return value.strip()


def parse_message_page(html: str) -> tuple[bool, str]:
    parser = TelegramWidgetParser()
    parser.feed(html)
    return parser.exists, parser.text


def classify_order(text: str) -> tuple[bool, list[str]]:
    normalized = re.sub(r"\s+", " ", text).strip().lower()
    if not normalized:
        return False, []
    if any(marker in normalized for marker in EXCLUDED_MARKERS):
        return False, []
    if any(normalized.startswith(prefix) for prefix in EXCLUDED_STARTS):
        return False, []
    if SELF_PROMO_RE.search(normalized):
        return False, []

    intent = sorted(set(match.lower() for match in INTENT_RE.findall(normalized)))
    niche = sorted(set(match.lower() for match in NICHE_RE.findall(normalized)))
    return bool(HIRING_RE.search(normalized)), intent + niche


def initial_state() -> dict[str, int]:
    return {source.username: source.initial_message_id for source in SOURCES}


def load_state(path: Path) -> dict[str, int]:
    state = initial_state()
    if not path.exists():
        return state
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        for username in state:
            if isinstance(saved.get(username), int):
                state[username] = max(state[username], saved[username])
    except (OSError, ValueError, TypeError) as error:
        log.warning("State file is invalid, using safe initial IDs: %s", error)
    return state


def save_state(path: Path, state: dict[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def resolve_target(raw_target: str) -> int | str:
    value = raw_target.strip().strip('"').strip("'")
    return int(value) if re.fullmatch(r"-?\d+", value) else value


async def fetch_message(
    client: httpx.AsyncClient,
    source: Source,
    message_id: int,
) -> tuple[bool, str]:
    url = f"https://t.me/{source.username}/{message_id}?embed=1&mode=tme"
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = await client.get(url)
            response.raise_for_status()
            return parse_message_page(response.text)
        except Exception as error:
            last_error = error
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)

    log.warning(
        "Cannot fetch %s/%s after retries: %s",
        source.username,
        message_id,
        type(last_error).__name__,
    )
    raise RuntimeError("Telegram message fetch failed") from last_error


async def send_order(bot, target: int | str, source: Source, message_id: int, text: str, triggers: list[str]) -> None:
    link = f"https://t.me/{source.username}/{message_id}"
    trigger_text = ", ".join(triggers[:8])
    body = text[:3400]
    message = (
        "🎬 Новый заказ\n"
        f"📌 {source.title}\n"
        f"🏷 {trigger_text}\n"
        f"🔗 {link}\n\n"
        f"{body}"
    )
    await bot.send_message(chat_id=target, text=message, disable_web_page_preview=True)


async def scan_source(
    client: httpx.AsyncClient,
    bot,
    target: int | str,
    source: Source,
    state: dict[str, int],
    state_path: Path,
    gap_limit: int,
) -> None:
    candidate = state[source.username] + 1
    consecutive_missing = 0

    while consecutive_missing < gap_limit:
        try:
            exists, text = await fetch_message(client, source, candidate)
        except Exception:
            return

        if not exists:
            consecutive_missing += 1
            candidate += 1
            continue

        consecutive_missing = 0
        is_order, triggers = classify_order(text)
        if is_order:
            try:
                await send_order(bot, target, source, candidate, text, triggers)
            except Exception as error:
                log.warning("Cannot send order from %s/%s: %s", source.username, candidate, error)
                return
            log.info("Order sent from %s/%s", source.username, candidate)
        else:
            log.info("Skipped %s/%s: not a hiring post", source.username, candidate)

        state[source.username] = candidate
        save_state(state_path, state)
        candidate += 1


async def run() -> None:
    bot_token = os.environ["BOT_TOKEN"].strip()
    target = resolve_target(os.environ.get("FORWARD_TO", "1900772820"))
    proxy = os.environ.get("SOCKS_PROXY", "").strip() or None
    state_path = Path(os.environ.get("WEB_STATE_FILE", "/var/lib/tg-order-parser/web-state.json"))
    poll_interval = max(10, int(os.environ.get("POLL_INTERVAL", "45")))
    gap_limit = max(3, int(os.environ.get("MESSAGE_GAP_LIMIT", "12")))

    state = load_state(state_path)
    save_state(state_path, state)

    builder = Application.builder().token(bot_token)
    if proxy:
        builder = builder.proxy(proxy)
    application = builder.build()

    timeout = httpx.Timeout(25.0, connect=25.0)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; TelegramLeadMonitor/1.0)"}
    async with httpx.AsyncClient(proxy=proxy, timeout=timeout, headers=headers, follow_redirects=True) as client:
        await application.initialize()
        try:
            try:
                await application.bot.send_message(
                    chat_id=target,
                    text=(
                        "✅ Веб-парсер запущен без my.telegram.org.\n"
                        "Он проверяет 5 публичных групп и присылает только новые заказы."
                    ),
                )
            except Exception as error:
                log.warning("Cannot send startup message yet: %s", error)
            log.info("Public web scraper started: %s", ", ".join(state))

            while True:
                await asyncio.gather(*(
                    scan_source(client, application.bot, target, source, state, state_path, gap_limit)
                    for source in SOURCES
                ))
                await asyncio.sleep(poll_interval)
        finally:
            await application.shutdown()


if __name__ == "__main__":
    asyncio.run(run())
