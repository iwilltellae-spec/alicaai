"""
Мега-конструктор девушки. 20 шагов через FSM aiogram.
Каждый шаг = inline-кнопки. Можно отменить или вернуться.

Шаги:
 1. Имя
 2. Возраст
 3. Город
 4. Кем работает
 5. Кто она для тебя (тип отношений)
 6. Тип фигуры
 7. Рост
 8. Грудь
 9. Цвет волос
10. Длина волос
11. Цвет глаз
12. Особые черты (мульти)
13. Стиль одежды
14. Темперамент
15. Характер (2-4 черты, мульти)
16. Мат
17. Сленг
18. Эмодзи
19. Уровень флирта
20. Хобби (2-4, мульти)
21. Что любит (2-4, мульти)
22. Что не любит (1-3, мульти)
23. Страхи (1-2, мульти)
24. Фантазии (мульти)
25. Табу в интиме (мульти)
26. Превью → подтверждение
"""
from __future__ import annotations

from typing import Any

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from src.character import options as opt
from src.character.girl import Girl
from src.services.profile import COST_NEW_GIRL, MAX_GIRLS, ProfileStorage
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = Router(name="wizard")


class W(StatesGroup):
    name = State()
    age = State()
    city = State()
    city_custom = State()
    occupation = State()
    relationship = State()
    body = State()
    height = State()
    breast = State()
    hair_color = State()
    hair_length = State()
    eyes = State()
    special = State()
    clothes = State()
    temperament = State()
    character = State()
    swear = State()
    slang = State()
    emoji = State()
    flirt = State()
    hobbies = State()
    likes = State()
    dislikes = State()
    fears = State()
    fantasies = State()
    taboo = State()
    preview = State()


# ============== helpers ==============

def _kb(options: list[tuple[str, str]], prefix: str, *, columns: int = 2,
        with_back: bool = True, with_skip: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура из плоских опций."""
    rows: list[list[InlineKeyboardButton]] = []
    buf: list[InlineKeyboardButton] = []
    for code, label in options:
        buf.append(InlineKeyboardButton(text=label, callback_data=f"{prefix}:{code}"))
        if len(buf) == columns:
            rows.append(buf)
            buf = []
    if buf:
        rows.append(buf)
    bottom: list[InlineKeyboardButton] = []
    if with_skip:
        bottom.append(InlineKeyboardButton(text="⏭ Пропустить", callback_data=f"{prefix}:__skip__"))
    if with_back:
        bottom.append(InlineKeyboardButton(text="❌ Отменить", callback_data="wiz:cancel"))
    if bottom:
        rows.append(bottom)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _multi_kb(options: list[tuple[str, str]], prefix: str, selected: set[str],
              *, columns: int = 2) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    buf: list[InlineKeyboardButton] = []
    for code, label in options:
        mark = "✅ " if code in selected else "▫️ "
        buf.append(InlineKeyboardButton(text=mark + label, callback_data=f"{prefix}:{code}"))
        if len(buf) == columns:
            rows.append(buf)
            buf = []
    if buf:
        rows.append(buf)
    rows.append([
        InlineKeyboardButton(text="✅ Далее", callback_data=f"{prefix}:__done__"),
        InlineKeyboardButton(text="❌ Отменить", callback_data="wiz:cancel"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _label(options: list[tuple[str, str]], code: str) -> str:
    for c, l in options:
        if c == code:
            return l
    return code


def _labels(options: list[tuple[str, str]], codes: list[str]) -> list[str]:
    return [_label(options, c) for c in codes]


async def _show_step(message: Message, title: str, step: int, total: int,
                     text: str, keyboard: InlineKeyboardMarkup) -> None:
    header = f"<b>Шаг {step}/{total}</b>  ·  {title}\n\n{text}"
    await message.edit_text(header, reply_markup=keyboard)


TOTAL = 26


# ============== entry ==============

async def start_wizard(message: Message, state: FSMContext, storage: ProfileStorage,
                       *, edit_id: str | None = None) -> None:
    """Запускается из меню /girls. edit_id != None — редактирование существующей."""
    profile = storage.get(message.from_user.id)

    if edit_id:
        if edit_id not in profile.girls:
            await message.answer("Не нашла такую девушку.")
            return
        girl_dict = profile.girls[edit_id]
        await state.update_data(_edit_id=edit_id, **girl_dict)
        intro = f"✏️ <b>Редактируем {girl_dict.get('name', '—')}</b>"
    else:
        if len(profile.girls) >= MAX_GIRLS:
            await message.answer(
                f"😬 У тебя уже максимум девушек ({MAX_GIRLS}). Удали кого-нибудь."
            )
            return
        if profile.balance < COST_NEW_GIRL:
            await message.answer(
                f"💰 Не хватает баланса.\n"
                f"Нужно {COST_NEW_GIRL} 🪙, у тебя {profile.balance} 🪙."
            )
            return
        await state.update_data()
        intro = (
            "✨ <b>Создание новой девушки</b>\n"
            f"<i>Стоимость:</i> {COST_NEW_GIRL} 🪙\n\n"
            "Прошагаем по анкете. Каждый шаг можно пропустить — будет дефолт."
        )

    msg = await message.answer(intro + "\n\nГотов?", reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Начать", callback_data="wiz:begin")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="wiz:cancel")],
        ],
    ))
    await state.update_data(_msg_id=msg.message_id)


@router.callback_query(F.data == "wiz:begin")
async def wiz_begin(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(W.name)
    await _show_step(
        cb.message, "Имя", 1, TOTAL,
        "Как её зовут?\n<i>Напиши имя сообщением.</i>",
        InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🎲 Случайное", callback_data="wiz:random_name"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="wiz:cancel"),
        ]]),
    )
    await cb.answer()


@router.callback_query(F.data == "wiz:cancel")
async def wiz_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cb.message.edit_text("❌ Отменено.")
    await cb.answer()


# ============== шаг 1: имя ==============

RANDOM_NAMES = ["Алиса", "Кира", "Лера", "Маша", "Соня", "Юля", "Аня",
                "Настя", "Полина", "Ева", "Ника", "Карина", "Алёна"]


@router.callback_query(W.name, F.data == "wiz:random_name")
async def name_random(cb: CallbackQuery, state: FSMContext) -> None:
    import random
    name = random.choice(RANDOM_NAMES)
    await state.update_data(name=name)
    await _goto_age(cb.message, state)
    await cb.answer(f"Назвали её {name}")


@router.message(W.name, F.text)
async def name_text(message: Message, state: FSMContext) -> None:
    name = message.text.strip()[:24]
    if not name or name.startswith("/"):
        await message.answer("Введи нормальное имя.")
        return
    await state.update_data(name=name)
    # удалим предыдущее сообщение бота и юзера
    data = await state.get_data()
    msg_id = data.get("_msg_id")
    try:
        await message.delete()
    except Exception:  # noqa: BLE001
        pass
    msg = await message.answer("⏳")
    await state.update_data(_msg_id=msg.message_id)
    await _goto_age(msg, state)


async def _goto_age(message: Message, state: FSMContext) -> None:
    await state.set_state(W.age)
    await _show_step(
        message, "Возраст", 2, TOTAL,
        "Сколько ей лет?",
        _kb(opt.AGES, "age", columns=3),
    )


# ============== шаг 2: возраст ==============

@router.callback_query(W.age, F.data.startswith("age:"))
async def age_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "__skip__":
        await state.update_data(age=int(code))
    await state.set_state(W.city)
    await _show_step(
        cb.message, "Город", 3, TOTAL,
        "Откуда она?",
        _kb(opt.CITIES, "city", columns=2),
    )
    await cb.answer()


# ============== шаг 3: город ==============

@router.callback_query(W.city, F.data.startswith("city:"))
async def city_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code == "other":
        await state.set_state(W.city_custom)
        await cb.message.edit_text("✏️ Напиши название города сообщением.")
        await cb.answer()
        return
    if code != "__skip__":
        await state.update_data(city=_label(opt.CITIES, code))
    await _goto_occupation(cb.message, state)
    await cb.answer()


@router.message(W.city_custom, F.text)
async def city_text(message: Message, state: FSMContext) -> None:
    city = message.text.strip()[:40]
    if not city:
        return
    await state.update_data(city=city)
    try:
        await message.delete()
    except Exception:  # noqa: BLE001
        pass
    msg = await message.answer("⏳")
    await state.update_data(_msg_id=msg.message_id)
    await _goto_occupation(msg, state)


async def _goto_occupation(message: Message, state: FSMContext) -> None:
    await state.set_state(W.occupation)
    await _show_step(
        message, "Чем занимается", 4, TOTAL,
        "Кем работает / чем живёт?",
        _kb(opt.OCCUPATIONS, "occ", columns=2),
    )


# ============== шаг 4: работа ==============

@router.callback_query(W.occupation, F.data.startswith("occ:"))
async def occ_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "__skip__":
        await state.update_data(occupation=_label(opt.OCCUPATIONS, code))
    await state.set_state(W.relationship)
    await _show_step(
        cb.message, "Кто она тебе", 5, TOTAL,
        "Какие у вас отношения?",
        _kb(opt.RELATIONSHIP_TYPES, "rel", columns=1),
    )
    await cb.answer()


# ============== шаг 5: отношения ==============

@router.callback_query(W.relationship, F.data.startswith("rel:"))
async def rel_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "__skip__":
        await state.update_data(relationship=_label(opt.RELATIONSHIP_TYPES, code))
    await state.set_state(W.body)
    await _show_step(
        cb.message, "Фигура", 6, TOTAL,
        "Какая у неё фигура?",
        _kb(opt.BODY_TYPES, "body", columns=1),
    )
    await cb.answer()


# ============== шаги внешности ==============

@router.callback_query(W.body, F.data.startswith("body:"))
async def body_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "__skip__":
        await state.update_data(body_type=_label(opt.BODY_TYPES, code))
    await state.set_state(W.height)
    await _show_step(cb.message, "Рост", 7, TOTAL, "Какого роста?",
                     _kb(opt.HEIGHTS, "h", columns=1))
    await cb.answer()


@router.callback_query(W.height, F.data.startswith("h:"))
async def height_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "__skip__":
        await state.update_data(height=_label(opt.HEIGHTS, code))
    await state.set_state(W.breast)
    await _show_step(cb.message, "Грудь", 8, TOTAL, "Размер груди?",
                     _kb(opt.BREASTS, "br", columns=2))
    await cb.answer()


@router.callback_query(W.breast, F.data.startswith("br:"))
async def breast_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "__skip__":
        await state.update_data(breast=_label(opt.BREASTS, code))
    await state.set_state(W.hair_color)
    await _show_step(cb.message, "Волосы (цвет)", 9, TOTAL, "Цвет волос?",
                     _kb(opt.HAIR_COLORS, "hc", columns=2))
    await cb.answer()


@router.callback_query(W.hair_color, F.data.startswith("hc:"))
async def hc_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "__skip__":
        await state.update_data(hair_color=_label(opt.HAIR_COLORS, code))
    await state.set_state(W.hair_length)
    await _show_step(cb.message, "Волосы (длина)", 10, TOTAL, "Длина волос?",
                     _kb(opt.HAIR_LENGTH, "hl", columns=2))
    await cb.answer()


@router.callback_query(W.hair_length, F.data.startswith("hl:"))
async def hl_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "__skip__":
        await state.update_data(hair_length=_label(opt.HAIR_LENGTH, code))
    await state.set_state(W.eyes)
    await _show_step(cb.message, "Глаза", 11, TOTAL, "Цвет глаз?",
                     _kb(opt.EYES, "ey", columns=2))
    await cb.answer()


@router.callback_query(W.eyes, F.data.startswith("ey:"))
async def eyes_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "__skip__":
        await state.update_data(eyes=_label(opt.EYES, code))
    await state.set_state(W.special)
    await state.update_data(_special_sel=[])
    await _show_step(
        cb.message, "Особые черты", 12, TOTAL,
        "Выбери несколько (или ни одной):",
        _multi_kb(opt.SPECIAL_FEATURES, "sp", set()),
    )
    await cb.answer()


# ============== мульти-выбор: особые черты ==============

@router.callback_query(W.special, F.data.startswith("sp:"))
async def special_toggle(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    data = await state.get_data()
    sel: list[str] = list(data.get("_special_sel", []))
    if code == "__done__":
        labels = _labels(opt.SPECIAL_FEATURES, [c for c in sel if c != "none"])
        await state.update_data(special=labels or ["—"])
        await state.set_state(W.clothes)
        await _show_step(cb.message, "Стиль одежды", 13, TOTAL,
                         "Как любит одеваться?",
                         _kb(opt.CLOTHING_STYLE, "cl", columns=1))
        await cb.answer()
        return
    if code in sel:
        sel.remove(code)
    else:
        sel.append(code)
    await state.update_data(_special_sel=sel)
    await cb.message.edit_reply_markup(
        reply_markup=_multi_kb(opt.SPECIAL_FEATURES, "sp", set(sel)),
    )
    await cb.answer()


@router.callback_query(W.clothes, F.data.startswith("cl:"))
async def cl_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "__skip__":
        await state.update_data(style_clothes=_label(opt.CLOTHING_STYLE, code))
    await state.set_state(W.temperament)
    await _show_step(cb.message, "Темперамент", 14, TOTAL, "Какой темперамент?",
                     _kb(opt.TEMPERAMENTS, "tmp", columns=1))
    await cb.answer()


@router.callback_query(W.temperament, F.data.startswith("tmp:"))
async def tmp_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "__skip__":
        await state.update_data(temperament=_label(opt.TEMPERAMENTS, code))
    await state.set_state(W.character)
    await state.update_data(_char_sel=[])
    await _show_step(
        cb.message, "Характер", 15, TOTAL,
        "Выбери 2-4 черты характера:",
        _multi_kb(opt.CHARACTER_TRAITS, "ch", set()),
    )
    await cb.answer()


@router.callback_query(W.character, F.data.startswith("ch:"))
async def ch_toggle(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    data = await state.get_data()
    sel: list[str] = list(data.get("_char_sel", []))
    if code == "__done__":
        if not sel:
            await cb.answer("Выбери хотя бы одну черту", show_alert=True)
            return
        await state.update_data(character=_labels(opt.CHARACTER_TRAITS, sel[:4]))
        await state.set_state(W.swear)
        await _show_step(cb.message, "Мат", 16, TOTAL, "Как у неё с матом?",
                         _kb(opt.SPEECH_SWEAR, "sw", columns=1))
        await cb.answer()
        return
    if code in sel:
        sel.remove(code)
    elif len(sel) < 4:
        sel.append(code)
    else:
        await cb.answer("Максимум 4", show_alert=False)
        return
    await state.update_data(_char_sel=sel)
    await cb.message.edit_reply_markup(
        reply_markup=_multi_kb(opt.CHARACTER_TRAITS, "ch", set(sel)),
    )
    await cb.answer()


@router.callback_query(W.swear, F.data.startswith("sw:"))
async def sw_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "__skip__":
        await state.update_data(speech_swearing=_label(opt.SPEECH_SWEAR, code))
    await state.set_state(W.slang)
    await _show_step(cb.message, "Сленг", 17, TOTAL, "Как говорит — сленг и сокращения?",
                     _kb(opt.SPEECH_SLANG, "sl", columns=1))
    await cb.answer()


@router.callback_query(W.slang, F.data.startswith("sl:"))
async def sl_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "__skip__":
        await state.update_data(speech_slang=_label(opt.SPEECH_SLANG, code))
    await state.set_state(W.emoji)
    await _show_step(cb.message, "Эмодзи", 18, TOTAL, "Как часто шлёт эмодзи?",
                     _kb(opt.EMOJI_FREQ, "em", columns=1))
    await cb.answer()


@router.callback_query(W.emoji, F.data.startswith("em:"))
async def em_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "__skip__":
        await state.update_data(emoji_freq=_label(opt.EMOJI_FREQ, code))
    await state.set_state(W.flirt)
    await _show_step(cb.message, "Флирт", 19, TOTAL, "Уровень флирта?",
                     _kb(opt.FLIRT_LEVEL, "fl", columns=1))
    await cb.answer()


@router.callback_query(W.flirt, F.data.startswith("fl:"))
async def fl_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "__skip__":
        await state.update_data(flirt_level=_label(opt.FLIRT_LEVEL, code))
    await state.set_state(W.hobbies)
    await state.update_data(_hob_sel=[])
    await _show_step(
        cb.message, "Хобби", 20, TOTAL,
        "Выбери 2-4 хобби:",
        _multi_kb(opt.HOBBIES, "hb", set()),
    )
    await cb.answer()


@router.callback_query(W.hobbies, F.data.startswith("hb:"))
async def hb_toggle(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    data = await state.get_data()
    sel: list[str] = list(data.get("_hob_sel", []))
    if code == "__done__":
        await state.update_data(hobbies=_labels(opt.HOBBIES, sel[:4]))
        await state.set_state(W.likes)
        await state.update_data(_lk_sel=[])
        await _show_step(cb.message, "Что любит", 21, TOTAL,
                         "Выбери 2-4 что она любит:",
                         _multi_kb(opt.LIKES, "lk", set()))
        await cb.answer()
        return
    if code in sel:
        sel.remove(code)
    elif len(sel) < 4:
        sel.append(code)
    else:
        await cb.answer("Максимум 4")
        return
    await state.update_data(_hob_sel=sel)
    await cb.message.edit_reply_markup(
        reply_markup=_multi_kb(opt.HOBBIES, "hb", set(sel)),
    )
    await cb.answer()


@router.callback_query(W.likes, F.data.startswith("lk:"))
async def lk_toggle(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    data = await state.get_data()
    sel: list[str] = list(data.get("_lk_sel", []))
    if code == "__done__":
        await state.update_data(likes=_labels(opt.LIKES, sel[:4]))
        await state.set_state(W.dislikes)
        await state.update_data(_dl_sel=[])
        await _show_step(cb.message, "Что НЕ любит", 22, TOTAL,
                         "Выбери 1-3 что её бесит:",
                         _multi_kb(opt.DISLIKES, "dl", set()))
        await cb.answer()
        return
    if code in sel:
        sel.remove(code)
    elif len(sel) < 4:
        sel.append(code)
    else:
        await cb.answer("Максимум 4")
        return
    await state.update_data(_lk_sel=sel)
    await cb.message.edit_reply_markup(
        reply_markup=_multi_kb(opt.LIKES, "lk", set(sel)),
    )
    await cb.answer()


@router.callback_query(W.dislikes, F.data.startswith("dl:"))
async def dl_toggle(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    data = await state.get_data()
    sel: list[str] = list(data.get("_dl_sel", []))
    if code == "__done__":
        await state.update_data(dislikes=_labels(opt.DISLIKES, sel[:3]))
        await state.set_state(W.fears)
        await state.update_data(_fr_sel=[])
        await _show_step(cb.message, "Страхи", 23, TOTAL,
                         "Чего боится? (1-2)",
                         _multi_kb(opt.FEARS, "fr", set()))
        await cb.answer()
        return
    if code in sel:
        sel.remove(code)
    elif len(sel) < 3:
        sel.append(code)
    else:
        await cb.answer("Максимум 3")
        return
    await state.update_data(_dl_sel=sel)
    await cb.message.edit_reply_markup(
        reply_markup=_multi_kb(opt.DISLIKES, "dl", set(sel)),
    )
    await cb.answer()


@router.callback_query(W.fears, F.data.startswith("fr:"))
async def fr_toggle(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    data = await state.get_data()
    sel: list[str] = list(data.get("_fr_sel", []))
    if code == "__done__":
        await state.update_data(fears=_labels(opt.FEARS, [c for c in sel if c != "none"][:2]))
        await state.set_state(W.fantasies)
        await state.update_data(_fa_sel=[])
        await _show_step(cb.message, "Фантазии 🔞", 24, TOTAL,
                         "Что её заводит? (мульти-выбор, можно пропустить):",
                         _multi_kb(opt.FANTASIES, "fa", set()))
        await cb.answer()
        return
    if code in sel:
        sel.remove(code)
    elif len(sel) < 2:
        sel.append(code)
    else:
        await cb.answer("Максимум 2")
        return
    await state.update_data(_fr_sel=sel)
    await cb.message.edit_reply_markup(
        reply_markup=_multi_kb(opt.FEARS, "fr", set(sel)),
    )
    await cb.answer()


@router.callback_query(W.fantasies, F.data.startswith("fa:"))
async def fa_toggle(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    data = await state.get_data()
    sel: list[str] = list(data.get("_fa_sel", []))
    if code == "__done__":
        await state.update_data(fantasies=_labels(opt.FANTASIES, sel))
        await state.set_state(W.taboo)
        await state.update_data(_tb_sel=[])
        await _show_step(cb.message, "Табу", 25, TOTAL,
                         "Чего НЕ делает в интиме:",
                         _multi_kb(opt.INTIMATE_TABOO, "tb", set()))
        await cb.answer()
        return
    if code in sel:
        sel.remove(code)
    else:
        sel.append(code)
    await state.update_data(_fa_sel=sel)
    await cb.message.edit_reply_markup(
        reply_markup=_multi_kb(opt.FANTASIES, "fa", set(sel)),
    )
    await cb.answer()


@router.callback_query(W.taboo, F.data.startswith("tb:"))
async def tb_toggle(cb: CallbackQuery, state: FSMContext, storage: ProfileStorage) -> None:
    code = cb.data.split(":", 1)[1]
    data = await state.get_data()
    sel: list[str] = list(data.get("_tb_sel", []))
    if code == "__done__":
        await state.update_data(intimate_taboo=_labels(opt.INTIMATE_TABOO,
                                                      [c for c in sel if c != "none"]))
        await _show_preview(cb.message, state, storage)
        await cb.answer()
        return
    if code in sel:
        sel.remove(code)
    else:
        sel.append(code)
    await state.update_data(_tb_sel=sel)
    await cb.message.edit_reply_markup(
        reply_markup=_multi_kb(opt.INTIMATE_TABOO, "tb", set(sel)),
    )
    await cb.answer()


# ============== preview & save ==============

async def _show_preview(message: Message, state: FSMContext,
                        storage: ProfileStorage) -> None:
    data = await state.get_data()
    # отфильтруем служебные ключи
    clean = {k: v for k, v in data.items() if not k.startswith("_")}
    girl = Girl(**clean) if "_edit_id" not in data else Girl(
        id=data["_edit_id"], **{k: v for k, v in clean.items() if k != "id"}
    )

    profile = storage.get(message.chat.id)
    is_edit = "_edit_id" in data

    text = (
        f"<b>{girl.name}</b>, {girl.age} · {girl.city}\n"
        f"<i>{', '.join(girl.character)}</i>\n\n"
        f"💼 {girl.occupation}\n"
        f"💗 {girl.relationship}\n\n"
        f"<b>Внешность</b>\n"
        f"• {girl.body_type}, {girl.height}\n"
        f"• {girl.breast}\n"
        f"• Волосы: {girl.hair_color}, {girl.hair_length}\n"
        f"• Глаза: {girl.eyes}\n"
        f"• Особое: {', '.join(girl.special) if girl.special else '—'}\n"
        f"• Стиль: {girl.style_clothes}\n\n"
        f"<b>Манера речи</b>\n"
        f"• Мат: {girl.speech_swearing}\n"
        f"• Сленг: {girl.speech_slang}\n"
        f"• Эмодзи: {girl.emoji_freq}\n\n"
        f"<b>Личность</b>\n"
        f"• Темперамент: {girl.temperament}\n"
        f"• Хобби: {', '.join(girl.hobbies) if girl.hobbies else '—'}\n"
        f"• Любит: {', '.join(girl.likes) if girl.likes else '—'}\n"
        f"• Не любит: {', '.join(girl.dislikes) if girl.dislikes else '—'}\n"
        f"• Страхи: {', '.join(girl.fears) if girl.fears else '—'}\n\n"
        f"<b>Интим</b>\n"
        f"• Флирт: {girl.flirt_level}\n"
        f"• Фантазии: {', '.join(girl.fantasies) if girl.fantasies else '—'}\n"
        f"• Табу: {', '.join(girl.intimate_taboo) if girl.intimate_taboo else 'нет'}\n"
    )

    if not is_edit:
        text += f"\n💰 Стоимость: <b>{COST_NEW_GIRL} 🪙</b>"
        save_label = f"✅ Создать ({COST_NEW_GIRL} 🪙)"
    else:
        save_label = "💾 Сохранить изменения"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=save_label, callback_data="wiz:save")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="wiz:cancel")],
    ])
    await state.set_state(W.preview)
    await message.edit_text(text, reply_markup=kb)


@router.callback_query(W.preview, F.data == "wiz:save")
async def wiz_save(cb: CallbackQuery, state: FSMContext,
                   storage: ProfileStorage) -> None:
    data = await state.get_data()
    clean = {k: v for k, v in data.items() if not k.startswith("_")}
    profile = storage.get(cb.from_user.id)
    is_edit = "_edit_id" in data

    if is_edit:
        girl = Girl(id=data["_edit_id"],
                    **{k: v for k, v in clean.items() if k != "id"})
    else:
        if profile.balance < COST_NEW_GIRL:
            await cb.answer("Не хватает баланса 😢", show_alert=True)
            return
        girl = Girl(**clean)
        profile.balance -= COST_NEW_GIRL

    profile.save_girl(girl)
    if not profile.active_girl_id or not is_edit:
        profile.set_active(girl.id)
    storage.commit(profile)

    await state.clear()
    msg = (
        f"✅ {'Сохранено' if is_edit else 'Создана'}: <b>{girl.name}</b>\n"
        f"<i>Теперь она активна. Просто пиши ей.</i>\n\n"
        f"💰 Баланс: {profile.balance} 🪙"
    )
    await cb.message.edit_text(msg)
    await cb.answer()
