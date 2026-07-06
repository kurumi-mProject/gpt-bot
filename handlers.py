from aiogram import Router, F, Bot
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                            InlineKeyboardButton, InlineQueryResultArticle,
                            InputTextMessageContent, InlineQuery)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime
import io, hashlib

from database import (get_user, get_session, set_model, set_system_prompt,
                      get_history, add_message, clear_history, get_msg_count,
                      get_last_user_message)
from ai import chat_completion, transcribe_audio
from config import MODELS, TIER_LABELS, ADMIN_ID, MODES

router = Router()

# ─── FSM ──────────────────────────────────────────────────────────────────────
class PromptState(StatesGroup):
    waiting = State()

# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_user_tier(user_row) -> int:
    if not user_row or not user_row["active"]:
        return -1
    try:
        delta = (datetime.strptime(user_row["paid_until"], "%Y-%m-%d") - datetime.now()).days
        if delta < 0:
            return -1
    except Exception:
        return -1
    limit = user_row["traffic_limit_gb"] or 50
    if limit >= 200: return 12
    if limit >= 150: return 6
    if limit >= 100: return 3
    if limit >= 50:  return 1
    return 0

def allowed_models(tier: int) -> list:
    return [mid for mid, m in MODELS.items() if m["tier"] <= tier]

def models_keyboard(tier: int, current: str) -> InlineKeyboardMarkup:
    rows = []
    last_tier = -1
    for mid, m in MODELS.items():
        if m["tier"] != last_tier:
            last_tier = m["tier"]
        if m["tier"] > tier:
            rows.append([InlineKeyboardButton(
                text=f"🔒 {m['name']} ({TIER_LABELS.get(m['tier'],'')})",
                callback_data="locked_model"
            )])
            continue
        mark = "✅ " if mid == current else "   "
        rows.append([InlineKeyboardButton(
            text=f"{mark}{m['name']} — {m['desc'][:35]}",
            callback_data=f"model:{mid}"
        )])
    rows.append([InlineKeyboardButton(text="✕ Закрыть", callback_data="close")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def main_menu_kb(model_name: str = "") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🤖 Модель: {model_name}", callback_data="choose_model")],
        [InlineKeyboardButton(text="🗑 Новый чат", callback_data="clear_hist"),
         InlineKeyboardButton(text="📊 Статус", callback_data="my_status")],
        [InlineKeyboardButton(text="⚙️ Системный промпт", callback_data="set_prompt"),
         InlineKeyboardButton(text="📤 Экспорт", callback_data="export_hist")],
        [InlineKeyboardButton(text="🎭 Режим", callback_data="choose_mode"),
         InlineKeyboardButton(text="🌐 Войти на сайт", callback_data="web_login")],
    ])

def answer_kb(model_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Повторить", callback_data="regenerate"),
         InlineKeyboardButton(text="➕ Продолжи", callback_data="continue_answer")],
        [InlineKeyboardButton(text="🤖 Модель", callback_data="choose_model"),
         InlineKeyboardButton(text="🗑 Новый чат", callback_data="clear_hist")],
    ])

def no_access_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Получить подписку", url="https://t.me/KomoVpn_bot")]
    ])

async def get_current_model(user_id: int) -> str:
    session = await get_session(user_id)
    return session["model"] if session else "gpt-5-nano"

async def do_chat(user_id: int, user_text: str, bot: Bot, reply_to: Message, image_b64: str = None) -> Message:
    """Основная логика запроса к AI. Возвращает сообщение с ответом."""
    session = await get_session(user_id)
    model_id = session["model"] if session else "gpt-5-nano"
    user = await get_user(user_id)
    tier = get_user_tier(user)

    if model_id not in MODELS or MODELS[model_id]["tier"] > tier:
        model_id = "gpt-5-nano"
        await set_model(user_id, model_id)

    thinking = await reply_to.answer("✨ _Думаю..._")

    history = await get_history(user_id, model_id, limit=12)
    messages = []
    if session and session["system_prompt"]:
        messages.append({"role": "system", "content": session["system_prompt"]})
    messages += [{"role": r["role"], "content": r["content"]} for r in history]

    # Поддержка изображений
    if image_b64:
        user_content = [
            {"type": "text", "text": user_text},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
        ]
    else:
        user_content = user_text

    messages.append({"role": "user", "content": user_content})
    await add_message(user_id, model_id, "user", user_text)

    try:
        answer = await chat_completion(model_id, messages)
        await add_message(user_id, model_id, "assistant", answer)
        model_name = MODELS[model_id]["name"]
        display = answer if len(answer) <= 4000 else answer[:3990] + "\n\n_...обрезано_"
        await thinking.edit_text(
            f"{display}\n\n_— {model_name}_",
            reply_markup=answer_kb(model_id)
        )
        return thinking
    except Exception as e:
        await thinking.edit_text(
            f"❌ *Ошибка:* `{e}`\n\nПопробуй ещё раз или смени модель.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Повторить", callback_data="regenerate"),
                 InlineKeyboardButton(text="🤖 Сменить модель", callback_data="choose_model")]
            ])
        )
        return thinking

# ─── /start ───────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(msg: Message):
    user = await get_user(msg.from_user.id)
    tier = get_user_tier(user)
    if tier < 0:
        await msg.answer(
            "👋 Привет! Я *KomoGPT* — AI-ассистент.\n\n"
            "⚠️ Нужна активная подписка *KomoVPN*.\n"
            "Одна подписка — VPN + ChatGPT.\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "✅ *Что умею:*\n"
            "• 15+ AI моделей (GPT-5, Grok 4, DeepSeek R1...)\n"
            "• Голосовые сообщения 🎤\n"
            "• Анализ изображений 🖼\n"
            "• Режимы: переводчик, программист, аналитик\n"
            "• Inline-режим в любом чате\n"
            "• Экспорт истории в .md",
            reply_markup=no_access_kb()
        )
        return
    model_id = await get_current_model(msg.from_user.id)
    model_name = MODELS.get(model_id, {}).get("name", model_id)
    count = await get_msg_count(msg.from_user.id)
    avail = len(allowed_models(tier))
    tier_name = {0:"Пробный",1:"1 мес",3:"3 мес",6:"6 мес",12:"12 мес"}.get(tier,"—")
    await msg.answer(
        f"👋 Привет, *{msg.from_user.first_name}*!\n\n"
        f"🤖 Модель: *{model_name}*\n"
        f"🔓 Доступно моделей: *{avail}* из {len(MODELS)}\n"
        f"💎 Тариф: *{tier_name}*\n"
        f"💬 Сообщений отправлено: *{count}*\n\n"
        f"Просто напиши сообщение — отвечу мгновенно.\n"
        f"Голосовые и изображения тоже понимаю 🎤🖼",
        reply_markup=main_menu_kb(model_name)
    )

# ─── /help ────────────────────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "📖 *Команды KomoGPT*\n\n"
        "/start — главное меню\n"
        "/model — выбрать AI модель\n"
        "/new — новый чат (очистить историю)\n"
        "/prompt — задать системный промпт\n"
        "/myprompt — показать текущий промпт\n"
        "/clearprompt — сбросить промпт\n"
        "/export — экспорт истории в файл\n"
        "/stats — статистика использования\n"
        "/status — статус подписки\n"
        "/help — эта справка\n\n"
        "🎤 *Голосовые сообщения* — автоматически распознаются\n"
        "🔄 *Повторить* — кнопка под ответом\n"
        "⚙️ *Системный промпт* — задай роль боту\n\n"
        "💡 Inline-режим: `@бот вопрос` в любом чате"
    )

# ─── /new ─────────────────────────────────────────────────────────────────────

@router.message(Command("new"))
async def cmd_new(msg: Message):
    session = await get_session(msg.from_user.id)
    model = session["model"] if session else None
    await clear_history(msg.from_user.id, model)
    model_name = MODELS.get(model, {}).get("name", model or "—")
    await msg.answer(
        f"🆕 Новый чат начат!\n_История модели {model_name} очищена._",
        reply_markup=main_menu_kb(model_name)
    )

# ─── /model ───────────────────────────────────────────────────────────────────

@router.message(Command("model"))
async def cmd_model(msg: Message):
    user = await get_user(msg.from_user.id)
    tier = get_user_tier(user)
    if tier < 0:
        await msg.answer("⚠️ Нет активной подписки.", reply_markup=no_access_kb())
        return
    current = await get_current_model(msg.from_user.id)
    await msg.answer(
        "🤖 *Выбери модель:*\n_Заблокированные доступны на более высоком тарифе_",
        reply_markup=models_keyboard(tier, current)
    )

@router.callback_query(F.data == "choose_model")
async def cb_choose_model(cb: CallbackQuery):
    user = await get_user(cb.from_user.id)
    tier = get_user_tier(user)
    if tier < 0:
        await cb.answer("Нет подписки", show_alert=True)
        return
    current = await get_current_model(cb.from_user.id)
    await cb.message.edit_text(
        "🤖 *Выбери модель:*\n_Заблокированные доступны на более высоком тарифе_",
        reply_markup=models_keyboard(tier, current)
    )
    await cb.answer()

@router.callback_query(F.data == "locked_model")
async def cb_locked(cb: CallbackQuery):
    await cb.answer("🔒 Эта модель доступна на более высоком тарифе. Продли подписку в @KomoVpn_bot", show_alert=True)

@router.callback_query(F.data.startswith("model:"))
async def cb_set_model(cb: CallbackQuery):
    model_id = cb.data.split(":", 1)[1]
    user = await get_user(cb.from_user.id)
    tier = get_user_tier(user)
    if model_id not in MODELS or MODELS[model_id]["tier"] > tier:
        await cb.answer("❌ Недоступно на вашем тарифе", show_alert=True)
        return
    await set_model(cb.from_user.id, model_id)
    m = MODELS[model_id]
    await cb.message.edit_text(
        f"✅ *{m['name']}*\n\n_{m['desc']}_\n\nПросто напиши сообщение 👇",
        reply_markup=main_menu_kb(m["name"])
    )
    await cb.answer(f"Модель: {m['name']}")

# ─── /prompt ──────────────────────────────────────────────────────────────────

@router.message(Command("prompt"))
async def cmd_prompt(msg: Message, state: FSMContext):
    user = await get_user(msg.from_user.id)
    if get_user_tier(user) < 0:
        await msg.answer("⚠️ Нет подписки.", reply_markup=no_access_kb())
        return
    await state.set_state(PromptState.waiting)
    await msg.answer(
        "⚙️ *Системный промпт*\n\n"
        "Напиши роль или инструкцию для бота.\n"
        "_Например: «Ты опытный Python-разработчик. Отвечай кратко и с примерами кода.»_\n\n"
        "Или /clearprompt чтобы сбросить.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_prompt")]
        ])
    )

@router.callback_query(F.data == "set_prompt")
async def cb_set_prompt(cb: CallbackQuery, state: FSMContext):
    user = await get_user(cb.from_user.id)
    if get_user_tier(user) < 0:
        await cb.answer("Нет подписки", show_alert=True)
        return
    await state.set_state(PromptState.waiting)
    await cb.message.edit_text(
        "⚙️ *Системный промпт*\n\nНапиши роль для бота:\n"
        "_«Ты опытный Python-разработчик»_\n_«Отвечай только на русском»_\n_«Ты помощник по математике»_",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_prompt")]
        ])
    )
    await cb.answer()

@router.message(PromptState.waiting)
async def receive_prompt(msg: Message, state: FSMContext):
    await state.clear()
    await set_system_prompt(msg.from_user.id, msg.text)
    model_id = await get_current_model(msg.from_user.id)
    model_name = MODELS.get(model_id, {}).get("name", model_id)
    await msg.answer(
        f"✅ *Системный промпт установлен!*\n\n`{msg.text[:200]}`\n\nТеперь бот будет следовать этой роли.",
        reply_markup=main_menu_kb(model_name)
    )

@router.callback_query(F.data == "cancel_prompt")
async def cb_cancel_prompt(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    model_id = await get_current_model(cb.from_user.id)
    model_name = MODELS.get(model_id, {}).get("name", model_id)
    await cb.message.edit_text("❌ Отменено.", reply_markup=main_menu_kb(model_name))
    await cb.answer()

@router.message(Command("myprompt"))
async def cmd_myprompt(msg: Message):
    session = await get_session(msg.from_user.id)
    prompt = session["system_prompt"] if session else None
    if prompt:
        await msg.answer(f"⚙️ *Текущий промпт:*\n\n`{prompt}`")
    else:
        await msg.answer("⚙️ Системный промпт не задан.\nИспользуй /prompt чтобы задать.")

@router.message(Command("clearprompt"))
async def cmd_clearprompt(msg: Message):
    await set_system_prompt(msg.from_user.id, None)
    await msg.answer("✅ Системный промпт сброшен.")

# ─── /stats ───────────────────────────────────────────────────────────────────

@router.message(Command("stats"))
async def cmd_stats(msg: Message):
    user = await get_user(msg.from_user.id)
    tier = get_user_tier(user)
    count = await get_msg_count(msg.from_user.id)
    model_id = await get_current_model(msg.from_user.id)
    model_name = MODELS.get(model_id, {}).get("name", model_id)
    avail = len(allowed_models(tier)) if tier >= 0 else 0
    tier_name = {-1:"Нет подписки",0:"Пробный",1:"1 мес",3:"3 мес",6:"6 мес",12:"12 мес"}.get(tier,"—")
    await msg.answer(
        f"📊 *Статистика*\n\n"
        f"💬 Сообщений отправлено: *{count}*\n"
        f"🤖 Текущая модель: *{model_name}*\n"
        f"🔓 Доступно моделей: *{avail}* из {len(MODELS)}\n"
        f"💎 Тариф: *{tier_name}*\n"
        f"📅 Подписка до: *{user['paid_until'] if user else '—'}*"
    )

# ─── /status ──────────────────────────────────────────────────────────────────

@router.message(Command("status"))
async def cmd_status(msg: Message):
    user = await get_user(msg.from_user.id)
    tier = get_user_tier(user)
    model_id = await get_current_model(msg.from_user.id)
    model_name = MODELS.get(model_id, {}).get("name", model_id)
    if tier < 0:
        await msg.answer("❌ Нет активной подписки.", reply_markup=no_access_kb())
        return
    avail = len(allowed_models(tier))
    session = await get_session(msg.from_user.id)
    prompt_set = "✅ задан" if (session and session["system_prompt"]) else "❌ не задан"
    await msg.answer(
        f"📊 *Статус KomoGPT*\n\n"
        f"✅ Подписка до: *{user['paid_until']}*\n"
        f"🤖 Модель: *{model_name}*\n"
        f"🔓 Моделей доступно: *{avail}* из {len(MODELS)}\n"
        f"⚙️ Системный промпт: {prompt_set}",
        reply_markup=main_menu_kb(model_name)
    )

@router.message(Command("login"))
async def cmd_login(msg: Message):
    import secrets, httpx, hashlib
    from config import BOT_TOKEN
    code = secrets.token_urlsafe(12)
    bot_secret = hashlib.sha256(BOT_TOKEN.encode()).hexdigest()[:16]
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post("http://localhost:8000/api/auth/create_code",
                json={"user_id": msg.from_user.id, "code": code, "bot_secret": bot_secret})
    except Exception:
        pass
    await msg.answer(
        "🌐 *Вход на сайт KomoVPN*\n\n"
        "Скопируй код и вставь на сайте:\n\n"
        f"`{code}`\n\n"
        "⏱ Код действует *10 минут*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Открыть сайт", url="https://lklunallm.icu")],
            [InlineKeyboardButton(text="📱 Mini App", url="https://lklunallm.icu/miniapp")],
        ])
    )

@router.callback_query(F.data == "my_status")
async def cb_status(cb: CallbackQuery):
    user = await get_user(cb.from_user.id)
    tier = get_user_tier(user)
    model_id = await get_current_model(cb.from_user.id)
    model_name = MODELS.get(model_id, {}).get("name", model_id)
    if tier < 0:
        await cb.message.edit_text("❌ Нет активной подписки.", reply_markup=no_access_kb())
        await cb.answer()
        return
    avail = len(allowed_models(tier))
    await cb.message.edit_text(
        f"📊 *Статус*\n\n"
        f"✅ Подписка до: *{user['paid_until']}*\n"
        f"🤖 Модель: *{model_name}*\n"
        f"🔓 Доступно: *{avail}* из {len(MODELS)} моделей",
        reply_markup=main_menu_kb(model_name)
    )
    await cb.answer()

# ─── /export ──────────────────────────────────────────────────────────────────

@router.message(Command("export"))
async def cmd_export(msg: Message):
    await do_export(msg.from_user.id, msg)

@router.callback_query(F.data == "export_hist")
async def cb_export(cb: CallbackQuery):
    await do_export(cb.from_user.id, cb.message)
    await cb.answer()

async def do_export(user_id: int, target: Message):
    model_id = await get_current_model(user_id)
    history = await get_history(user_id, model_id, limit=200)
    if not history:
        await target.answer("📭 История пуста.")
        return
    model_name = MODELS.get(model_id, {}).get("name", model_id)
    lines = [f"# KomoGPT — История чата\n# Модель: {model_name}\n"]
    for m in history:
        role = "Вы" if m["role"] == "user" else f"🤖 {model_name}"
        lines.append(f"\n**{role}:**\n{m['content']}\n")
    text = "\n".join(lines)
    buf = io.BytesIO(text.encode())
    buf.name = f"komogpt_{model_id}.md"
    from aiogram.types import BufferedInputFile
    await target.answer_document(
        BufferedInputFile(buf.getvalue(), filename=buf.name),
        caption=f"📤 История чата — {model_name}"
    )

# ─── /clear ───────────────────────────────────────────────────────────────────

@router.message(Command("clear"))
async def cmd_clear(msg: Message):
    session = await get_session(msg.from_user.id)
    model = session["model"] if session else None
    await clear_history(msg.from_user.id, model)
    model_name = MODELS.get(model, {}).get("name", model or "—")
    await msg.answer(f"🗑 История *{model_name}* очищена.", reply_markup=main_menu_kb(model_name))

@router.callback_query(F.data == "clear_hist")
async def cb_clear(cb: CallbackQuery):
    session = await get_session(cb.from_user.id)
    model = session["model"] if session else None
    await clear_history(cb.from_user.id, model)
    model_name = MODELS.get(model, {}).get("name", model or "—")
    await cb.message.edit_text(
        f"🆕 Новый чат!\n_История {model_name} очищена._",
        reply_markup=main_menu_kb(model_name)
    )
    await cb.answer("Очищено ✅")

# ─── Regenerate ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "regenerate")
async def cb_regenerate(cb: CallbackQuery):
    user = await get_user(cb.from_user.id)
    tier = get_user_tier(user)
    if tier < 0:
        await cb.answer("Нет подписки", show_alert=True)
        return
    model_id = await get_current_model(cb.from_user.id)
    last = await get_last_user_message(cb.from_user.id, model_id)
    if not last:
        await cb.answer("Нет сообщений для повтора", show_alert=True)
        return
    # Удаляем последний ответ ассистента из истории
    import aiosqlite
    async with aiosqlite.connect("/root/vpn_bot/vpn.db") as db:
        await db.execute(
            "DELETE FROM chat_history WHERE id=(SELECT MAX(id) FROM chat_history WHERE user_id=? AND model=? AND role='assistant')",
            (cb.from_user.id, model_id)
        )
        await db.execute(
            "DELETE FROM chat_history WHERE id=(SELECT MAX(id) FROM chat_history WHERE user_id=? AND model=? AND role='user')",
            (cb.from_user.id, model_id)
        )
        await db.commit()
    await cb.answer("🔄 Генерирую заново...")
    await do_chat(cb.from_user.id, last, cb.bot, cb.message)

# ─── Фото ─────────────────────────────────────────────────────────────────────

@router.message(F.photo)
async def handle_photo(msg: Message):
    user = await get_user(msg.from_user.id)
    tier = get_user_tier(user)
    if tier < 0:
        await msg.answer("⚠️ Нет подписки.", reply_markup=no_access_kb())
        return
    import base64 as _b64
    file = await msg.bot.get_file(msg.photo[-1].file_id)
    buf = io.BytesIO()
    await msg.bot.download_file(file.file_path, buf)
    img_b64 = _b64.b64encode(buf.getvalue()).decode()
    caption = msg.caption or "Что на этом изображении? Опиши подробно."
    await do_chat(msg.from_user.id, caption, msg.bot, msg, image_b64=img_b64)

# ─── Голосовые сообщения ──────────────────────────────────────────────────────

@router.message(F.voice)
async def handle_voice(msg: Message):
    user = await get_user(msg.from_user.id)
    tier = get_user_tier(user)
    if tier < 0:
        await msg.answer("⚠️ Нет подписки.", reply_markup=no_access_kb())
        return
    status = await msg.answer("🎤 _Распознаю речь..._")
    try:
        file = await msg.bot.get_file(msg.voice.file_id)
        buf = io.BytesIO()
        await msg.bot.download_file(file.file_path, buf)
        text = await transcribe_audio(buf.getvalue(), "voice.ogg")
        if not text.strip():
            await status.edit_text("❌ Не удалось распознать речь.")
            return
        await status.edit_text(f"🎤 *Распознано:* _{text}_")
        await do_chat(msg.from_user.id, text, msg.bot, msg)
    except Exception as e:
        await status.edit_text(f"❌ Ошибка распознавания: {e}")

# ─── Inline режим ─────────────────────────────────────────────────────────────

@router.inline_query()
async def inline_handler(query: InlineQuery):
    text = query.query.strip()
    if not text or len(text) < 3:
        return
    user = await get_user(query.from_user.id)
    tier = get_user_tier(user)
    if tier < 0:
        results = [InlineQueryResultArticle(
            id="no_access",
            title="❌ Нет подписки",
            description="Получи подписку в @KomoVpn_bot",
            input_message_content=InputTextMessageContent(message_text="Нужна подписка KomoVPN")
        )]
        await query.answer(results, cache_time=5)
        return

    model_id = await get_current_model(query.from_user.id)
    model_name = MODELS.get(model_id, {}).get("name", model_id)
    # Быстрый ответ без истории для inline
    try:
        answer = await chat_completion(model_id, [{"role": "user", "content": text}])
        short = answer[:200] + ("..." if len(answer) > 200 else "")
        results = [InlineQueryResultArticle(
            id=hashlib.md5(text.encode()).hexdigest()[:8],
            title=f"🤖 {model_name}",
            description=short,
            input_message_content=InputTextMessageContent(
                message_text=f"❓ *{text}*\n\n{answer}\n\n_— KomoGPT · {model_name}_"
            )
        )]
    except Exception as e:
        results = [InlineQueryResultArticle(
            id="err",
            title="❌ Ошибка",
            description=str(e),
            input_message_content=InputTextMessageContent(message_text=f"Ошибка: {e}")
        )]
    await query.answer(results, cache_time=30)

# ─── close / noop ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "web_login")
async def cb_web_login(cb: CallbackQuery):
    import secrets, httpx, hashlib
    from config import BOT_TOKEN
    code = secrets.token_urlsafe(12)
    bot_secret = hashlib.sha256(BOT_TOKEN.encode()).hexdigest()[:16]
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post("http://localhost:8000/api/auth/create_code",
                json={"user_id": cb.from_user.id, "code": code, "bot_secret": bot_secret})
    except Exception:
        pass
    await cb.message.edit_text(
        "🌐 *Вход на сайт KomoVPN*\n\n"
        "Скопируй код и вставь на сайте:\n\n"
        f"`{code}`\n\n"
        "⏱ Код действует *10 минут*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Открыть сайт", url="https://lklunallm.icu")],
            [InlineKeyboardButton(text="📱 Mini App", url="https://lklunallm.icu/miniapp")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_main_gpt")],
        ])
    )
    await cb.answer()

@router.callback_query(F.data == "back_main_gpt")
async def cb_back_main_gpt(cb: CallbackQuery):
    model_id = await get_current_model(cb.from_user.id)
    model_name = MODELS.get(model_id, {}).get("name", model_id)
    await cb.message.edit_text(
        f"🤖 *KomoGPT*\n\nМодель: *{model_name}*\nПросто напиши сообщение 👇",
        parse_mode="Markdown", reply_markup=main_menu_kb(model_name)
    )
    await cb.answer()


async def cb_close(cb: CallbackQuery):
    await cb.message.delete()
    await cb.answer()

@router.callback_query(F.data == "noop")
async def cb_noop(cb: CallbackQuery):
    await cb.answer()

# ─── Режимы ───────────────────────────────────────────────────────────────────

def modes_keyboard(current_mode: str) -> InlineKeyboardMarkup:
    rows = []
    for mid, m in MODES.items():
        mark = "✅ " if mid == current_mode else "   "
        rows.append([InlineKeyboardButton(text=f"{mark}{m['name']}", callback_data=f"mode:{mid}")])
    rows.append([InlineKeyboardButton(text="✕ Закрыть", callback_data="close")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

@router.message(Command("mode"))
async def cmd_mode(msg: Message):
    user = await get_user(msg.from_user.id)
    if get_user_tier(user) < 0:
        await msg.answer("⚠️ Нет подписки.", reply_markup=no_access_kb())
        return
    session = await get_session(msg.from_user.id)
    current = session["mode"] if session and "mode" in session.keys() else "default"
    await msg.answer("🎭 *Выбери режим:*\n_Режим задаёт роль бота_", reply_markup=modes_keyboard(current))

@router.callback_query(F.data == "choose_mode")
async def cb_choose_mode(cb: CallbackQuery):
    user = await get_user(cb.from_user.id)
    if get_user_tier(user) < 0:
        await cb.answer("Нет подписки", show_alert=True)
        return
    session = await get_session(cb.from_user.id)
    current = "default"
    try:
        if session: current = session["mode"]
    except Exception:
        pass
    await cb.message.edit_text("🎭 *Выбери режим:*", reply_markup=modes_keyboard(current))
    await cb.answer()

@router.callback_query(F.data.startswith("mode:"))
async def cb_set_mode(cb: CallbackQuery):
    mode_id = cb.data.split(":", 1)[1]
    if mode_id not in MODES:
        await cb.answer("Неизвестный режим", show_alert=True)
        return
    m = MODES[mode_id]
    # Сохраняем режим как системный промпт
    await set_system_prompt(cb.from_user.id, m["prompt"])
    # Сохраняем mode в сессии
    import aiosqlite
    async with aiosqlite.connect("/root/vpn_bot/vpn.db") as db:
        await db.execute(
            "INSERT INTO chat_sessions (user_id, mode) VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET mode=excluded.mode",
            (cb.from_user.id, mode_id)
        )
        await db.commit()
    model_id = await get_current_model(cb.from_user.id)
    model_name = MODELS.get(model_id, {}).get("name", model_id)
    await cb.message.edit_text(
        f"✅ Режим: *{m['name']}*\n\n"
        f"{'_' + m['prompt'][:100] + '_' if m['prompt'] else '_Без системного промпта_'}\n\n"
        f"Просто напиши сообщение 👇",
        reply_markup=main_menu_kb(model_name)
    )
    await cb.answer(m["name"])

# ─── Продолжи ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "continue_answer")
async def cb_continue(cb: CallbackQuery):
    user = await get_user(cb.from_user.id)
    tier = get_user_tier(user)
    if tier < 0:
        await cb.answer("Нет подписки", show_alert=True)
        return
    await cb.answer("➕ Продолжаю...")
    await do_chat(cb.from_user.id, "Продолжи с того места где остановился.", cb.bot, cb.message)

# ─── Основной обработчик текста ───────────────────────────────────────────────

@router.message(F.text)
async def handle_message(msg: Message, state: FSMContext):
    # Игнорируем если в FSM состоянии
    current = await state.get_state()
    if current:
        return

    user = await get_user(msg.from_user.id)
    tier = get_user_tier(user)
    if tier < 0:
        await msg.answer("⚠️ Нужна подписка *KomoVPN*.", reply_markup=no_access_kb())
        return
    await do_chat(msg.from_user.id, msg.text, msg.bot, msg)
