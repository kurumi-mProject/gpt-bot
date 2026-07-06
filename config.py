import os
from dotenv import load_dotenv

load_dotenv("/root/vpn_bot/.env")

BOT_TOKEN = os.getenv("GPT_BOT_TOKEN", "8356573889:AAGDt5ln93E4AFVh1pa6ws0pzBRuIM3Xd6c")
ADMIN_ID = int(os.getenv("ADMIN_ID", "6715030024"))
AITUNNEL_KEY = os.getenv("AITUNNEL_KEY", "")
AITUNNEL_URL = "https://api.aitunnel.ru/v1"
VPN_DB = "/root/vpn_bot/vpn.db"

# Модели по уровням подписки (месяцев -> список моделей)
# Каждый уровень включает все модели предыдущего
MODELS = {
    "gpt-5-nano":                    {"name": "GPT-5 Nano",              "desc": "Быстрая и лёгкая модель от OpenAI",                    "tier": 0},
    "glm-4.7-flash":                 {"name": "GLM-4.7 Flash",           "desc": "Молниеносная модель от Zhipu AI",                      "tier": 0},
    "gemini-3.1-flash-lite-preview": {"name": "Gemini 3.1 Flash Lite",   "desc": "Лёгкая версия Gemini от Google",                       "tier": 0},
    "gpt-4.1-nano":                  {"name": "GPT-4.1 Nano",            "desc": "Компактная версия GPT-4.1",                            "tier": 1},
    "qwen3.5-flash-02-23":           {"name": "Qwen 3.5 Flash",          "desc": "Быстрая модель от Alibaba Cloud",                      "tier": 1},
    "minimax-m2.5":                  {"name": "MiniMax M2.5",            "desc": "Эффективная модель от MiniMax",                        "tier": 1},
    "gpt-5-mini":                    {"name": "GPT-5 Mini",              "desc": "Компактная версия GPT-5",                              "tier": 3},
    "qwen3-235b-a22b-2507":          {"name": "Qwen3 235B",              "desc": "Мощная модель 235B параметров от Alibaba",             "tier": 3},
    "deepseek-v3.2-special":         {"name": "DeepSeek V3.2 Special",   "desc": "Специальная версия DeepSeek V3.2",                     "tier": 3},
    "mistral-medium-3.1":            {"name": "Mistral Medium 3.1",      "desc": "Сбалансированная модель от Mistral AI",                "tier": 3},
    "qwen3.5-35b-a3b":               {"name": "Qwen 3.5 35B",            "desc": "Продвинутая модель 35B от Alibaba",                    "tier": 6},
    "deepseek-r1-0528":              {"name": "DeepSeek R1",             "desc": "Мощная reasoning-модель от DeepSeek",                  "tier": 6},
    "grok-4.1-fast":                 {"name": "Grok 4.1 Fast",           "desc": "Быстрая версия Grok 4.1 от xAI",                      "tier": 6},
    "deepseek-v3.2-exp":             {"name": "DeepSeek V3.2 Exp",       "desc": "Экспериментальная версия DeepSeek V3.2",               "tier": 6},
    "grok-4-fast":                   {"name": "Grok 4 Fast",             "desc": "Топовая модель от xAI — быстрая версия",              "tier": 12},
}

# tier = минимальное кол-во месяцев подписки для доступа (0 = пробный тоже)
TIER_LABELS = {0: "Пробный+", 1: "1+ мес", 3: "3+ мес", 6: "6+ мес", 12: "12 мес"}

# Готовые режимы с системными промптами
MODES = {
    "default":    {"name": "💬 Обычный",     "prompt": None},
    "translator": {"name": "🌍 Переводчик",  "prompt": "Ты профессиональный переводчик. Переводи на русский если текст на другом языке, и на английский если на русском. Отвечай только переводом."},
    "coder":      {"name": "💻 Программист", "prompt": "Ты опытный программист. Отвечай кратко, с примерами кода в markdown блоках."},
    "copywriter": {"name": "✍️ Копирайтер",  "prompt": "Ты профессиональный копирайтер. Пишешь продающие тексты, посты, заголовки. Стиль — живой, цепляющий."},
    "analyst":    {"name": "📊 Аналитик",    "prompt": "Ты бизнес-аналитик. Анализируй данные, делай выводы, структурируй ответы по пунктам."},
    "teacher":    {"name": "📚 Учитель",     "prompt": "Ты терпеливый учитель. Объясняй сложные вещи простыми словами, приводи примеры."},
}
