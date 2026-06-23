"""
Мега-конструктор девушки. ~26 шагов через FSM aiogram.

Опции хранятся как (code, label, prompt_text):
- label идёт в кнопку (короткий)
- prompt_text сохраняется в Girl (длинный, для промпта)
"""
from __future__ import annotations

from typing import Any

from aiogram import F, Router
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
from src.services.memory import ChatMemory
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


TOTAL = 26


# ============== helpers ==============

def _kb(options: list[tuple[str, str, str]], prefix: str, *, columns: int = 2,
        with_skip: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура из 3-tuple опций (code, label, prompt_text). Кнопки = label."""
    rows: list[list[InlineKeyboardButton]] = []
    buf: list[InlineKeyboardButton] = []
    for code, label, _ in options:
        buf.append(InlineKeyboardButton(text=label, callback_data=f"{prefix}:{code}"))
        if len(buf) == columns:
            rows.append(buf)
            buf = []
    if buf:
        rows.append(buf)
    bottom: list[InlineKeyboardButton] = []
    if with_skip:
        bottom.append(InlineKeyboardButton(text="⏭ Пропустить", callback_data=f"{prefix}:__skip__"))
    bottom.append(InlineKeyboardButton(text="❌ Отмена", callback_data="wiz:cancel"))
    rows.append(bottom)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _multi_kb(options: list[tuple[str, str, str]], prefix: str, selected: set[str],
              *, columns: int = 2) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    buf: list[InlineKeyboardButton] = []
    for code, label, _ in options:
        mark = "✅ " if code in selected else "▫️ "
        buf.append(InlineKeyboardButton(text=mark + label, callback_data=f"{prefix}:{code}"))
        if len(buf) == columns:
            rows.append(buf)
            buf = []
    if buf:
        rows.append(buf)
    rows.append([
        InlineKeyboardButton(text="✅ Далее", callback_data=f"{prefix}:__done__"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="wiz:cancel"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _prompt_of(options: list[tuple[str, str, str]], code: str) -> str:
    for c, _, p in options:
        if c == code:
            return p
    return code


def _prompts_of(options: list[tuple[str, str, str]], codes: list[str]) -> list[str]:
    return [p for p in (_prompt_of(options, c) for c in codes) if p]


async def _show_step(message: Message, title: str, step: int, total: int,
                     text: str, keyboard: InlineKeyboardMarkup) -> None:
    header = f"<b>Шаг {step}/{total}</b>  ·  {title}\n\n{text}"
    try:
        await message.edit_text(header, reply_markup=keyboard)
    except Exception:  # noqa: BLE001
        # Если редактирование не получилось (например, сообщение от другого бота),
        # отправляем новым.
        await message.answer(header, reply_markup=keyboard)


# ============== entry ==============

async def start_wizard(message: Message, user_id: int, state: FSMContext,
                       storage: ProfileStorage,
                       *, edit_id: str | None = None) -> None:
    """user_id передаём явно — message.from_user может быть ботом если message от callback."""
    profile = await storage.get(user_id)

    if edit_id:
        if edit_id not in profile.girls:
            await message.answer("Не нашла такую девушку. Попробуй из меню.")
            return
        girl_dict = dict(profile.girls[edit_id])
        await state.update_data(_edit_id=edit_id, _user_id=user_id, **girl_dict)
        intro = f"✏️ <b>Редактируем {girl_dict.get('name', '—')}</b>"
    else:
        if len(profile.girls) >= MAX_GIRLS:
            await message.answer(
                f"😬 У тебя уже максимум девушек ({MAX_GIRLS}). Удали кого-нибудь."
            )
            return
        if profile.balance < COST_NEW_GIRL:
            await message.answer(
                f"💰 Не хватает.\nНужно {COST_NEW_GIRL} 🪙, у тебя {profile.balance} 🪙."
            )
            return
        await state.update_data(_user_id=user_id)
        intro = (
            "✨ <b>Создание новой девушки</b>\n"
            f"<i>Стоимость:</i> {COST_NEW_GIRL} 🪙\n\n"
            "Прошагаем по анкете. Каждый параметр влияет на её поведение."
        )

    msg = await message.answer(intro + "\n\nГотов?", reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Начать", callback_data="wiz:begin")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="wiz:cancel")],
        ],
    ))


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
    try:
        await cb.message.edit_text("❌ Отменено.")
    except Exception:  # noqa: BLE001
        await cb.message.answer("❌ Отменено.")
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
    try:
        await message.delete()
    except Exception:  # noqa: BLE001
        pass
    msg = await message.answer("⏳")
    await _goto_age(msg, state)


async def _goto_age(message: Message, state: FSMContext) -> None:
    await state.set_state(W.age)
    await _show_step(message, "Возраст", 2, TOTAL, "Сколько ей лет?",
                     _kb(opt.AGES, "age", columns=4))


@router.callback_query(W.age, F.data.startswith("age:"))
async def age_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "__skip__":
        await state.update_data(age=int(code))
    await state.set_state(W.city)
    await _show_step(cb.message, "Город", 3, TOTAL, "Откуда она?",
                     _kb(opt.CITIES, "city", columns=2))
    await cb.answer()


@router.callback_query(W.city, F.data.startswith("city:"))
async def city_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code == "other":
        await state.set_state(W.city_custom)
        await cb.message.edit_text("✏️ Напиши название города сообщением.")
        await cb.answer()
        return
    if code != "__skip__":
        await state.update_data(city=_prompt_of(opt.CITIES, code))
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
    await _goto_occupation(msg, state)


async def _goto_occupation(message: Message, state: FSMContext) -> None:
    await state.set_state(W.occupation)
    await _show_step(message, "Чем занимается", 4, TOTAL, "Кем работает / чем живёт?",
                     _kb(opt.OCCUPATIONS, "occ", columns=2))


@router.callback_query(W.occupation, F.data.startswith("occ:"))
async def occ_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "__skip__":
        await state.update_data(occupation=_prompt_of(opt.OCCUPATIONS, code))
    await state.set_state(W.relationship)
    await _show_step(cb.message, "Кто она тебе", 5, TOTAL, "Какие у вас отношения?",
                     _kb(opt.RELATIONSHIP_TYPES, "rel", columns=2))
    await cb.answer()


@router.callback_query(W.relationship, F.data.startswith("rel:"))
async def rel_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "__skip__":
        await state.update_data(relationship=_prompt_of(opt.RELATIONSHIP_TYPES, code))
    await state.set_state(W.body)
    await _show_step(cb.message, "Фигура", 6, TOTAL, "Какая у неё фигура?",
                     _kb(opt.BODY_TYPES, "body", columns=2))
    await cb.answer()


@router.callback_query(W.body, F.data.startswith("body:"))
async def body_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "__skip__":
        await state.update_data(body_type=_prompt_of(opt.BODY_TYPES, code))
    await state.set_state(W.height)
    await _show_step(cb.message, "Рост", 7, TOTAL, "Какого роста?",
                     _kb(opt.HEIGHTS, "h", columns=3))
    await cb.answer()


@router.callback_query(W.height, F.data.startswith("h:"))
async def height_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "__skip__":
        await state.update_data(height=_prompt_of(opt.HEIGHTS, code))
    await state.set_state(W.breast)
    await _show_step(cb.message, "Грудь", 8, TOTAL, "Размер груди?",
                     _kb(opt.BREASTS, "br", columns=3))
    await cb.answer()


@router.callback_query(W.breast, F.data.startswith("br:"))
async def breast_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "__skip__":
        await state.update_data(breast=_prompt_of(opt.BREASTS, code))
    await state.set_state(W.hair_color)
    await _show_step(cb.message, "Волосы (цвет)", 9, TOTAL, "Цвет волос?",
                     _kb(opt.HAIR_COLORS, "hc", columns=3))
    await cb.answer()


@router.callback_query(W.hair_color, F.data.startswith("hc:"))
async def hc_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "__skip__":
        await state.update_data(hair_color=_prompt_of(opt.HAIR_COLORS, code))
    await state.set_state(W.hair_length)
    await _show_step(cb.message, "Волосы (длина)", 10, TOTAL, "Длина волос?",
                     _kb(opt.HAIR_LENGTH, "hl", columns=2))
    await cb.answer()


@router.callback_query(W.hair_length, F.data.startswith("hl:"))
async def hl_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "__skip__":
        await state.update_data(hair_length=_prompt_of(opt.HAIR_LENGTH, code))
    await state.set_state(W.eyes)
    await _show_step(cb.message, "Глаза", 11, TOTAL, "Цвет глаз?",
                     _kb(opt.EYES, "ey", columns=3))
    await cb.answer()


@router.callback_query(W.eyes, F.data.startswith("ey:"))
async def eyes_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "__skip__":
        await state.update_data(eyes=_prompt_of(opt.EYES, code))
    await state.set_state(W.special)
    await state.update_data(_special_sel=[])
    await _show_step(cb.message, "Особые черты", 12, TOTAL,
                     "Выбери несколько (или ни одной):",
                     _multi_kb(opt.SPECIAL_FEATURES, "sp", set()))
    await cb.answer()


# ----- multi -----

async def _multi_handler(
    cb: CallbackQuery, state: FSMContext, prefix: str,
    options_list: list[tuple[str, str, str]], key_sel: str,
    max_pick: int, next_step_fn,
) -> None:
    code = cb.data.split(":", 1)[1]
    data = await state.get_data()
    sel: list[str] = list(data.get(key_sel, []))
    if code == "__done__":
        await next_step_fn(cb, state, sel)
        return
    if code in sel:
        sel.remove(code)
    elif len(sel) < max_pick:
        sel.append(code)
    else:
        await cb.answer(f"Максимум {max_pick}")
        return
    await state.update_data(**{key_sel: sel})
    try:
        await cb.message.edit_reply_markup(
            reply_markup=_multi_kb(options_list, prefix, set(sel)),
        )
    except Exception:  # noqa: BLE001
        pass
    await cb.answer()


@router.callback_query(W.special, F.data.startswith("sp:"))
async def sp_handler(cb: CallbackQuery, state: FSMContext) -> None:
    async def go_next(cb, state, sel):
        clean = [c for c in sel if c != "none"]
        await state.update_data(special=_prompts_of(opt.SPECIAL_FEATURES, clean))
        await state.set_state(W.clothes)
        await _show_step(cb.message, "Стиль одежды", 13, TOTAL, "Как любит одеваться?",
                         _kb(opt.CLOTHING_STYLE, "cl", columns=2))
        await cb.answer()
    await _multi_handler(cb, state, "sp", opt.SPECIAL_FEATURES, "_special_sel", 4, go_next)


@router.callback_query(W.clothes, F.data.startswith("cl:"))
async def cl_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "__skip__":
        await state.update_data(style_clothes=_prompt_of(opt.CLOTHING_STYLE, code))
    await state.set_state(W.temperament)
    await _show_step(cb.message, "Темперамент", 14, TOTAL, "Какой темперамент?",
                     _kb(opt.TEMPERAMENTS, "tmp", columns=2))
    await cb.answer()


@router.callback_query(W.temperament, F.data.startswith("tmp:"))
async def tmp_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "__skip__":
        await state.update_data(temperament=_prompt_of(opt.TEMPERAMENTS, code))
    await state.set_state(W.character)
    await state.update_data(_char_sel=[])
    await _show_step(cb.message, "Характер (2-4)", 15, TOTAL,
                     "Выбери 2-4 черты характера:",
                     _multi_kb(opt.CHARACTER_TRAITS, "ch", set()))
    await cb.answer()


@router.callback_query(W.character, F.data.startswith("ch:"))
async def ch_handler(cb: CallbackQuery, state: FSMContext) -> None:
    async def go_next(cb, state, sel):
        if not sel:
            await cb.answer("Выбери хотя бы одну", show_alert=True)
            return
        await state.update_data(character=_prompts_of(opt.CHARACTER_TRAITS, sel[:4]))
        await state.set_state(W.swear)
        await _show_step(cb.message, "Мат", 16, TOTAL, "Как у неё с матом?",
                         _kb(opt.SPEECH_SWEAR, "sw", columns=2))
        await cb.answer()
    await _multi_handler(cb, state, "ch", opt.CHARACTER_TRAITS, "_char_sel", 4, go_next)


@router.callback_query(W.swear, F.data.startswith("sw:"))
async def sw_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "__skip__":
        await state.update_data(speech_swearing=_prompt_of(opt.SPEECH_SWEAR, code))
    await state.set_state(W.slang)
    await _show_step(cb.message, "Сленг", 17, TOTAL, "Сленг и сокращения?",
                     _kb(opt.SPEECH_SLANG, "sl", columns=2))
    await cb.answer()


@router.callback_query(W.slang, F.data.startswith("sl:"))
async def sl_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "__skip__":
        await state.update_data(speech_slang=_prompt_of(opt.SPEECH_SLANG, code))
    await state.set_state(W.emoji)
    await _show_step(cb.message, "Эмодзи", 18, TOTAL, "Как часто шлёт эмодзи?",
                     _kb(opt.EMOJI_FREQ, "em", columns=2))
    await cb.answer()


@router.callback_query(W.emoji, F.data.startswith("em:"))
async def em_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "__skip__":
        await state.update_data(emoji_freq=_prompt_of(opt.EMOJI_FREQ, code))
    await state.set_state(W.flirt)
    await _show_step(cb.message, "Флирт", 19, TOTAL, "Уровень флирта?",
                     _kb(opt.FLIRT_LEVEL, "fl", columns=2))
    await cb.answer()


@router.callback_query(W.flirt, F.data.startswith("fl:"))
async def fl_pick(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    if code != "__skip__":
        await state.update_data(flirt_level=_prompt_of(opt.FLIRT_LEVEL, code))
    await state.set_state(W.hobbies)
    await state.update_data(_hob_sel=[])
    await _show_step(cb.message, "Хобби (2-4)", 20, TOTAL, "Выбери 2-4 хобби:",
                     _multi_kb(opt.HOBBIES, "hb", set()))
    await cb.answer()


@router.callback_query(W.hobbies, F.data.startswith("hb:"))
async def hb_handler(cb: CallbackQuery, state: FSMContext) -> None:
    async def go_next(cb, state, sel):
        await state.update_data(hobbies=_prompts_of(opt.HOBBIES, sel[:4]))
        await state.set_state(W.likes)
        await state.update_data(_lk_sel=[])
        await _show_step(cb.message, "Что любит", 21, TOTAL, "Выбери 2-4:",
                         _multi_kb(opt.LIKES, "lk", set()))
        await cb.answer()
    await _multi_handler(cb, state, "hb", opt.HOBBIES, "_hob_sel", 4, go_next)


@router.callback_query(W.likes, F.data.startswith("lk:"))
async def lk_handler(cb: CallbackQuery, state: FSMContext) -> None:
    async def go_next(cb, state, sel):
        await state.update_data(likes=_prompts_of(opt.LIKES, sel[:4]))
        await state.set_state(W.dislikes)
        await state.update_data(_dl_sel=[])
        await _show_step(cb.message, "Что НЕ любит", 22, TOTAL, "Выбери 1-3 что её бесит:",
                         _multi_kb(opt.DISLIKES, "dl", set()))
        await cb.answer()
    await _multi_handler(cb, state, "lk", opt.LIKES, "_lk_sel", 4, go_next)


@router.callback_query(W.dislikes, F.data.startswith("dl:"))
async def dl_handler(cb: CallbackQuery, state: FSMContext) -> None:
    async def go_next(cb, state, sel):
        await state.update_data(dislikes=_prompts_of(opt.DISLIKES, sel[:3]))
        await state.set_state(W.fears)
        await state.update_data(_fr_sel=[])
        await _show_step(cb.message, "Страхи", 23, TOTAL, "Чего боится? (0-2)",
                         _multi_kb(opt.FEARS, "fr", set()))
        await cb.answer()
    await _multi_handler(cb, state, "dl", opt.DISLIKES, "_dl_sel", 3, go_next)


@router.callback_query(W.fears, F.data.startswith("fr:"))
async def fr_handler(cb: CallbackQuery, state: FSMContext) -> None:
    async def go_next(cb, state, sel):
        clean = [c for c in sel if c != "none"]
        await state.update_data(fears=_prompts_of(opt.FEARS, clean[:2]))
        await state.set_state(W.fantasies)
        await state.update_data(_fa_sel=[])
        await _show_step(cb.message, "Фантазии 🔞", 24, TOTAL,
                         "Что её заводит (мульти):",
                         _multi_kb(opt.FANTASIES, "fa", set()))
        await cb.answer()
    await _multi_handler(cb, state, "fr", opt.FEARS, "_fr_sel", 2, go_next)


@router.callback_query(W.fantasies, F.data.startswith("fa:"))
async def fa_handler(cb: CallbackQuery, state: FSMContext) -> None:
    async def go_next(cb, state, sel):
        await state.update_data(fantasies=_prompts_of(opt.FANTASIES, sel))
        await state.set_state(W.taboo)
        await state.update_data(_tb_sel=[])
        await _show_step(cb.message, "Табу", 25, TOTAL, "Чего НЕ делает в интиме:",
                         _multi_kb(opt.INTIMATE_TABOO, "tb", set()))
        await cb.answer()
    await _multi_handler(cb, state, "fa", opt.FANTASIES, "_fa_sel", 10, go_next)


@router.callback_query(W.taboo, F.data.startswith("tb:"))
async def tb_handler(cb: CallbackQuery, state: FSMContext,
                     storage: ProfileStorage) -> None:
    code = cb.data.split(":", 1)[1]
    data = await state.get_data()
    sel: list[str] = list(data.get("_tb_sel", []))
    if code == "__done__":
        clean = [c for c in sel if c != "none"]
        await state.update_data(intimate_taboo=_prompts_of(opt.INTIMATE_TABOO, clean))
        await _show_preview(cb, state, storage)
        await cb.answer()
        return
    if code in sel:
        sel.remove(code)
    else:
        sel.append(code)
    await state.update_data(_tb_sel=sel)
    try:
        await cb.message.edit_reply_markup(
            reply_markup=_multi_kb(opt.INTIMATE_TABOO, "tb", set(sel)),
        )
    except Exception:  # noqa: BLE001
        pass
    await cb.answer()


# ============== preview & save ==============

async def _show_preview(cb: CallbackQuery, state: FSMContext,
                        storage: ProfileStorage) -> None:
    data = await state.get_data()
    user_id = data.get("_user_id", cb.from_user.id)
    is_edit = "_edit_id" in data
    clean = {k: v for k, v in data.items() if not k.startswith("_")}

    if is_edit:
        girl = Girl(id=data["_edit_id"], **{k: v for k, v in clean.items() if k != "id"})
    else:
        girl = Girl(**clean)

    profile = await storage.get(user_id)
    text = _format_preview(girl, is_edit, profile.balance)
    save_label = (
        "💾 Сохранить" if is_edit else f"✅ Создать ({COST_NEW_GIRL} 🪙)"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=save_label, callback_data="wiz:save")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="wiz:cancel")],
    ])
    await state.set_state(W.preview)
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except Exception:  # noqa: BLE001
        await cb.message.answer(text, reply_markup=kb)


def _format_preview(g: Girl, is_edit: bool, balance: int) -> str:
    txt = (
        f"<b>{g.name}</b>, {g.age} · {g.city}\n"
        f"<i>{', '.join(g.character) or '—'}</i>\n\n"
        f"💼 {g.occupation}\n"
        f"💗 {g.relationship}\n\n"
        f"<b>Внешность</b>\n"
        f"• {g.body_type}, {g.height}\n"
        f"• {g.breast}\n"
        f"• Волосы: {g.hair_color}, {g.hair_length}\n"
        f"• Глаза: {g.eyes}\n"
        f"• Особое: {', '.join(g.special) if g.special else '—'}\n"
        f"• Стиль: {g.style_clothes}\n\n"
        f"<b>Манера речи</b>\n"
        f"• Мат: {g.speech_swearing}\n"
        f"• Сленг: {g.speech_slang}\n"
        f"• Эмодзи: {g.emoji_freq}\n\n"
        f"<b>Личность</b>\n"
        f"• Темперамент: {g.temperament}\n"
        f"• Хобби: {', '.join(g.hobbies) if g.hobbies else '—'}\n"
        f"• Любит: {', '.join(g.likes) if g.likes else '—'}\n"
        f"• Не любит: {', '.join(g.dislikes) if g.dislikes else '—'}\n"
        f"• Страхи: {', '.join(g.fears) if g.fears else '—'}\n\n"
        f"<b>Интим</b>\n"
        f"• Флирт: {g.flirt_level}\n"
        f"• Фантазии: {', '.join(g.fantasies) if g.fantasies else '—'}\n"
        f"• Табу: {', '.join(g.intimate_taboo) if g.intimate_taboo else 'нет'}\n"
    )
    if not is_edit:
        txt += f"\n💰 Баланс {balance} 🪙 · Стоимость <b>{COST_NEW_GIRL} 🪙</b>"
    return txt


@router.callback_query(W.preview, F.data == "wiz:save")
async def wiz_save(cb: CallbackQuery, state: FSMContext,
                   storage: ProfileStorage, memory: ChatMemory) -> None:
    data = await state.get_data()
    user_id = data.get("_user_id", cb.from_user.id)
    is_edit = "_edit_id" in data
    clean = {k: v for k, v in data.items() if not k.startswith("_")}

    profile = await storage.get(user_id)

    if is_edit:
        girl = Girl(id=data["_edit_id"],
                    **{k: v for k, v in clean.items() if k != "id"})
    else:
        if profile.balance < COST_NEW_GIRL:
            await cb.answer("Не хватает 🪙", show_alert=True)
            return
        girl = Girl(**clean)
        profile.balance -= COST_NEW_GIRL

    profile.save_girl(girl)
    if not is_edit:
        profile.set_active(girl.id)
        await memory.reset(user_id, girl.id)
    await storage.commit(profile)

    await state.clear()
    msg = (
        f"✅ {'Сохранено' if is_edit else 'Создана'}: <b>{girl.name}</b>\n"
        f"<i>Сейчас активна — пиши прямо в чат.</i>\n\n"
        f"💰 Баланс: {profile.balance} 🪙"
    )
    try:
        await cb.message.edit_text(msg)
    except Exception:  # noqa: BLE001
        await cb.message.answer(msg)
    await cb.answer()
