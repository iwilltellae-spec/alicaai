"""
Обработчик запросов «пришли фото» / «скинь фото».

Триггер — фраза в сообщении. Если девушка имеет референс-фото — генерируем
через Nano Banana с image-to-image. Если нет — просим юзера загрузить.

Сцена для фото генерится отдельным лёгким вызовом основной LLM:
«какая сцена сейчас была бы уместна?» — учитывая контекст диалога.
"""
from __future__ import annotations

import asyncio
import datetime
import re

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.fsm.state import State, StatesGroup

from src.character.persona import build_system_prompt
from src.services.image_gen import ImageGenerator, appearance_summary
from src.services.memory import ChatMemory
from src.services.openrouter import OpenRouterClient, OpenRouterError
from src.services.profile import ProfileStorage
from src.services.weather import WeatherService
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = Router(name="photo_request")


# Триггер-фраза. Регулярка ловит варианты: «скинь фото», «пришли фотку», «скинь селфи».
_TRIGGER = re.compile(
    r"\b(скин[ьи]|пришл[иё]|отправ[ьи]|кинь|пиш?н[иь])\s+("
    r"фот[оку]|фотку|селфи|пик|пикчу|картинку)\b",
    re.IGNORECASE,
)


class PhotoFlow(StatesGroup):
    waiting_for_ref = State()


def is_photo_request(text: str) -> bool:
    return bool(_TRIGGER.search(text))


# ---------------- main handler ----------------

@router.message(F.text.func(lambda t: t and is_photo_request(t)))
async def handle_photo_request(
    message: Message,
    bot: Bot,
    state: FSMContext,
    llm: OpenRouterClient,
    memory: ChatMemory,
    weather: WeatherService,
    storage: ProfileStorage,
    image_gen: ImageGenerator,
) -> None:
    # Если в визарде — пропускаем.
    if await state.get_state() is not None:
        return
    if not memory.has_consent(message.from_user.id):
        return

    user_id = message.from_user.id
    profile = await storage.get(user_id)
    girl = profile.get_active_girl()

    # Сохраняем в историю как обычное сообщение пользователя.
    await memory.add_user(user_id, girl.id, message.text)

    # Если нет референса — просим загрузить и НЕ генерим.
    if not girl.reference_file_id:
        text = (
            f"📸 Чтобы <b>{girl.name}</b> могла прислать тебе фото, "
            f"добавь её <b>референс-фото</b>.\n\n"
            f"<i>Это базовое фото девушки, по которому будут генериться все "
            f"остальные снимки. Меняться будут только мимика, поза и фон — "
            f"лицо и фигура останутся теми же.</i>\n\n"
            f"Нажми кнопку и пришли фото:"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="📎 Загрузить референс",
                callback_data=f"ph:upload:{girl.id}",
            )
        ]])
        await message.answer(text, reply_markup=kb)
        return

    # Есть референс — генерим.
    await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_PHOTO)
    status_msg = await message.answer("📸 <i>щас сфоткаюсь…</i>")

    # 1. Сначала просим LLM придумать сцену с учётом контекста.
    scene_en = await _generate_scene(llm, memory, weather, girl, user_id, message.text)
    if not scene_en:
        scene_en = "casual selfie at home, soft smile, looking at camera"

    logger.info("Photo scene: %s", scene_en)

    # 2. Генерим картинку.
    appearance = appearance_summary(girl)
    img_bytes = await image_gen.generate(
        scene=scene_en,
        girl_appearance=appearance,
        reference_file_id=girl.reference_file_id,
    )

    try:
        await status_msg.delete()
    except Exception:  # noqa: BLE001
        pass

    if not img_bytes:
        # Модель отказала / упала — пишем по-человечески.
        await message.answer(
            "ой блин, не получилось сфоткать норм 🙈\nпотом ещё раз попробую"
        )
        return

    # 3. Шлём с короткой подписью «от Алисы».
    caption_text = await _generate_caption(llm, memory, weather, girl, user_id, scene_en)
    photo_file = BufferedInputFile(img_bytes, filename="selfie.jpg")
    await message.answer_photo(photo_file, caption=caption_text or None)

    # Сохраняем в историю что прислала фото.
    await memory.add_assistant(
        user_id, girl.id,
        f"[прислала фото: {scene_en}]" + (f" {caption_text}" if caption_text else ""),
    )


async def _generate_scene(
    llm: OpenRouterClient, memory: ChatMemory, weather, girl, user_id: int,
    user_text: str,
) -> str:
    """LLM решает какая сцена уместна сейчас. Возвращает EN-описание для Nano Banana."""
    history = await memory.get_history(user_id, girl.id)
    # Берём последние 6 сообщений для контекста.
    tail = history[-6:]
    ctx = "\n".join(
        f"{'HE' if m['role']=='user' else 'SHE'}: {m['content']}"
        for m in tail if isinstance(m.get('content'), str)
    )

    now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)
    hour = now.hour
    time_hint = (
        "early morning" if 5 <= hour < 11
        else "afternoon" if 11 <= hour < 17
        else "evening" if 17 <= hour < 23
        else "late night"
    )

    prompt = f"""\
You are designing a selfie scene for a virtual girlfriend chatbot.

Girl profile:
- Name: {girl.name}, {girl.age}
- City: {girl.city}
- Occupation: {girl.occupation}
- Style of clothes: {girl.style_clothes}
- Current mood: {memory.get_mood(user_id).label}
- Time of day: {time_hint}

Recent conversation:
{ctx if ctx else '(no context)'}

User just asked her to send a photo: "{user_text}"

Write ONE short English sentence describing what selfie would be MOST natural \
for her to take RIGHT NOW given the context. Include: location, pose, mood, lighting. \
Casual amateur phone selfie style. Keep it under 30 words. No NSFW.

Answer with ONLY the scene description, nothing else."""

    try:
        reply = await llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.9,
            max_tokens=80,
        )
        return reply.strip().strip('"').strip("'")[:300]
    except OpenRouterError as e:
        logger.warning("Scene gen failed: %s", e)
        return ""


async def _generate_caption(
    llm: OpenRouterClient, memory: ChatMemory, weather, girl, user_id: int,
    scene_en: str,
) -> str:
    """Короткая подпись «от Алисы» к фото."""
    prompt = f"""\
Ты — {girl.name}, девушка которая только что сфоткала селфи. \
Сцена: {scene_en}. Напиши КОРОТКУЮ подпись в духе твоего обычного стиля \
(маленькая буква, без точек в конце, можно эмодзи). \
1-7 слов максимум. Только подпись, без кавычек.

Например: "ну как тебе", "сижу скучаю", "вот я ща", "ыыы 🙈", "люблю утро такое".

Подпись:"""
    try:
        reply = await llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=1.0,
            max_tokens=30,
        )
        return reply.strip().strip('"').strip("'")[:80]
    except OpenRouterError:
        return ""


# ---------------- referense upload flow ----------------

@router.callback_query(F.data.startswith("ph:upload:"))
async def cb_upload_ref(cb: CallbackQuery, state: FSMContext) -> None:
    girl_id = cb.data.split(":", 2)[2]
    await state.set_state(PhotoFlow.waiting_for_ref)
    await state.update_data(_ref_girl_id=girl_id)
    await cb.message.edit_text(
        "📎 <b>Жду фото</b>\n\n"
        "Пришли мне обычное фото девушки (лицо + фигура хорошо видны).\n"
        "Это будет референс — все будущие селфи будут с этим лицом.\n\n"
        "<i>Чтобы отменить — /cancel</i>"
    )
    await cb.answer()


@router.message(PhotoFlow.waiting_for_ref, F.photo)
async def handle_ref_upload(
    message: Message, state: FSMContext,
    storage: ProfileStorage,
) -> None:
    from src.character.girl import Girl
    data = await state.get_data()
    girl_id = data.get("_ref_girl_id")
    if not girl_id:
        await state.clear()
        return

    profile = await storage.get(message.from_user.id)
    if girl_id not in profile.girls:
        await state.clear()
        await message.answer("Девушка не найдена 😢")
        return

    # Берём самое большое разрешение фото.
    file_id = message.photo[-1].file_id
    girl = Girl.from_dict(profile.girls[girl_id])
    girl.reference_file_id = file_id
    profile.save_girl(girl)
    await storage.commit(profile)

    await state.clear()
    await message.answer(
        f"✅ <b>Референс сохранён для {girl.name}</b>\n\n"
        f"Теперь напиши ей <i>«скинь фото»</i> — она пришлёт селфи "
        f"с этим лицом, в подходящей сцене."
    )


@router.message(PhotoFlow.waiting_for_ref, F.text)
async def handle_ref_text(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip().lower()
    if text in ("/cancel", "отмена", "/menu", "/start"):
        await state.clear()
        await message.answer("❌ Окей, отменил.")
        return
    await message.answer("Жду <b>фото</b> 📎. Или /cancel чтобы отменить.")
