# 🤖 GPT Bot — Multi-model AI Telegram Bot

Telegram-бот с доступом к множеству AI-моделей через единый интерфейс. Доступ к моделям открывается в зависимости от срока подписки на VPN-бот — чем дольше подписка, тем мощнее модели доступны.

## Возможности

- **15+ AI-моделей** — GPT-5, Grok 4, DeepSeek R1, Qwen, Gemini, Mistral и другие
- **Тирная система доступа** — модели открываются по сроку VPN-подписки (0 / 1 / 3 / 6 / 12 мес)
- **Режимы общения** — переключение между пресетами: переводчик, программист, копирайтер, аналитик, учитель
- **История диалога** — контекст сохраняется в SQLite
- **Интеграция с VPN-ботом** — проверка подписки через общую БД

## Стек

- Python 3.11+
- [aiogram 3](https://docs.aiogram.dev/)
- [aitunnel.ru](https://aitunnel.ru) — API-прокси к AI-моделям
- SQLite + aiosqlite
- httpx

## Установка

```bash
git clone https://github.com/kurumi-mProject/gpt-bot.git
cd gpt-bot
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
python bot.py
```

## Переменные окружения (.env)

| Переменная | Описание |
|---|---|
| `GPT_BOT_TOKEN` | Токен от @BotFather |
| `ADMIN_ID` | Telegram ID администратора |
| `AITUNNEL_KEY` | API ключ aitunnel.ru |

## Доступные модели по уровням

| Уровень | Модели |
|---|---|
| 🆓 Пробный | GPT-5 Nano, GLM-4.7 Flash, Gemini 3.1 Flash Lite |
| 📅 1+ мес | GPT-4.1 Nano, Qwen 3.5 Flash, MiniMax M2.5 |
| 📅 3+ мес | GPT-5 Mini, Qwen3 235B, DeepSeek V3.2, Mistral Medium |
| 📅 6+ мес | Qwen 3.5 35B, DeepSeek R1, Grok 4.1 Fast |
| 📅 12 мес | Grok 4 Fast |

## Режимы

| Режим | Описание |
|---|---|
| 💬 Обычный | Стандартный диалог |
| 🌍 Переводчик | RU ↔ EN перевод |
| 💻 Программист | Ответы с примерами кода |
| ✍️ Копирайтер | Продающие тексты и посты |
| 📊 Аналитик | Структурированный анализ |
| 📚 Учитель | Простые объяснения сложных тем |

## Структура проекта

```
gpt-bot/
├── bot.py          # Точка входа
├── config.py       # Модели, режимы, конфигурация
├── handlers.py     # Обработчики команд и сообщений
├── ai.py           # Клиент к aitunnel API
├── database.py     # SQLite: история диалогов
└── requirements.txt
```
