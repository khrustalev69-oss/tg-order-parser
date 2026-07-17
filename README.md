# Telegram-парсер заказов

Парсер читает новые сообщения в заданных Telegram-чатах, отбирает заказы по
ключевым словам и пересылает их в указанный аккаунт или чат.

## Переменные Railway

- `SESSION_STRING` — сессия Telegram-аккаунта, от имени которого работает парсер.
- `FORWARD_TO` — числовой Telegram ID получателя или username без `@`.
- `SOCKS_PROXY` — необязательный SOCKS4/5-прокси, например `socks5://host:1080`.

Номер телефона и сессионный ключ нельзя публиковать в GitHub.

## Получение SESSION_STRING

Локально выполни:

```bash
cd "/Users/denishrustalev/Documents/New project/tg-order-parser"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PHONE=+79990000000 python auth_server.py
```

Вместо `+79990000000` укажи номер второго Telegram-аккаунта. Затем открой
`http://localhost:8080`, запроси код, введи код и при необходимости пароль 2FA.
Полученный `SESSION_STRING` добавь в Railway Variables.

## Запуск парсера локально

```bash
source .venv/bin/activate
SESSION_STRING='полученная_строка' FORWARD_TO='telegram_id' python userbot.py
```

На Railway команда запуска уже настроена: `python userbot.py`.
