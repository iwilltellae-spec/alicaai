"""Главное меню, профиль, список девушек."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from src.services.memory import ChatMemory
from src.services.profile import COST_NEW_GIRL, DAILY_BONUS, MAX_GIRLS, ProfileStorage
from src.utils.logger import get_logger

from .wizard import start_wizard

logger = get_logger(__name__)
router = Router(name="menu")


def _main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Профиль", callback_data="mn:profile")],
        [InlineKeyboardButton(text="👯 Мои девушки", callback_data="mn:girls")],
        [InlineKeyboardButton(text="🎁 Ежедневный бонус", callback_data="mn:bonus")],
        [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="mn:help")],
    ])


async def _render_home(message_or_cb, storage: ProfileStorage, *, edit: bool) -> None:
    user_id = message_or_cb.from_user.id
    profile = await storage.get(user_id)
    girl = profile.get_active_girl()
    await storage.commit(profile)
    text = (
        f"<b>🏠 Главное меню</b>\n\n"
        f"💗 Активна: <b>{girl.name}</b>\n"
        f"💰 Баланс: <b>{profile.balance} 🪙</b>\n"
        f"👯 Девушек: {len(profile.girls)} / {MAX_GIRLS}"
    )
    if edit:
        await message_or_cb.message.edit_text(text, reply_markup=_main_menu_kb())
    else:
        await message_or_cb.answer(text, reply_markup=_main_menu_kb())


@router.message(Command("menu"))
async def cmd_menu(message: Message, storage: ProfileStorage,
                   memory: ChatMemory) -> None:
    if not memory.has_consent(message.from_user.id):
        await message.answer("Сначала /start и подтверди возраст.")
        return
    await _render_home(message, storage, edit=False)


@router.callback_query(F.data == "mn:home")
async def cb_home(cb: CallbackQuery, storage: ProfileStorage) -> None:
    await _render_home(cb, storage, edit=True)
    await cb.answer()


# ============== ПРОФИЛЬ ==============

@router.callback_query(F.data == "mn:profile")
async def cb_profile(cb: CallbackQuery, storage: ProfileStorage,
                     memory: ChatMemory) -> None:
    profile = await storage.get(cb.from_user.id)
    girl = profile.get_active_girl()
    msg_count = await memory.message_count(cb.from_user.id, girl.id)
    facts = await memory.get_facts(cb.from_user.id, girl.id)
    text = (
        f"<b>👤 Твой профиль</b>\n\n"
        f"🆔 <code>{cb.from_user.id}</code>\n"
        f"💰 Баланс: <b>{profile.balance} 🪙</b>\n"
        f"👯 Девушек: <b>{len(profile.girls)}</b> / {MAX_GIRLS}\n"
        f"💬 Сообщений с активной: <b>{msg_count}</b>\n"
        f"🧠 Фактов о тебе запомнила: <b>{len(facts)}</b>\n\n"
        f"💗 Активна: <b>{girl.name}</b>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Что обо мне помнит",
                              callback_data="mn:facts")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="mn:home")],
    ])
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data == "mn:facts")
async def cb_facts(cb: CallbackQuery, storage: ProfileStorage,
                   memory: ChatMemory) -> None:
    profile = await storage.get(cb.from_user.id)
    girl = profile.get_active_girl()
    facts = await memory.get_facts(cb.from_user.id, girl.id)
    if not facts:
        text = (
            f"<b>🧠 Что {girl.name} о тебе помнит</b>\n\n"
            f"<i>Пока ничего. Поговори с ней — со временем она запомнит "
            f"важные факты о тебе и будет их использовать.</i>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="mn:profile")],
        ])
    else:
        lines = "\n".join(f"• {f}" for f in facts)
        text = f"<b>🧠 Что {girl.name} о тебе помнит</b>\n\n{lines}"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Очистить память обо мне",
                                  callback_data="mn:facts_clear")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="mn:profile")],
        ])
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data == "mn:facts_clear")
async def cb_facts_clear(cb: CallbackQuery, storage: ProfileStorage,
                         memory: ChatMemory) -> None:
    profile = await storage.get(cb.from_user.id)
    girl = profile.get_active_girl()
    # Очищаем только факты, историю не трогаем.
    if memory._db:  # noqa: SLF001
        await memory._db.clear_facts(cb.from_user.id, girl.id)  # noqa: SLF001
    memory._mem_facts.pop((cb.from_user.id, girl.id), None)  # noqa: SLF001
    await cb.answer("Память обо мне очищена ✅", show_alert=False)
    await cb_facts(cb, storage, memory)


# ============== БОНУС ==============

@router.callback_query(F.data == "mn:bonus")
async def cb_bonus(cb: CallbackQuery, storage: ProfileStorage) -> None:
    profile = await storage.get(cb.from_user.id)
    got = profile.claim_daily_bonus()
    await storage.commit(profile)
    if got > 0:
        text = (f"🎁 <b>Бонус!</b>\n\n+{got} 🪙\n"
                f"Баланс: <b>{profile.balance} 🪙</b>\n\n"
                f"<i>Возвращайся завтра.</i>")
    else:
        text = (f"⏳ <b>Уже получил сегодня.</b>\n\n"
                f"Возвращайся через ~24 часа.\n"
                f"Баланс: <b>{profile.balance} 🪙</b>")
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="mn:home")]],
    ))
    await cb.answer()


# ============== HELP ==============

@router.callback_query(F.data == "mn:help")
async def cb_help(cb: CallbackQuery) -> None:
    text = (
        "<b>ℹ️ Как пользоваться</b>\n\n"
        "• Пиши сообщения активной девушке.\n"
        "• <b>/menu</b> — это меню.\n"
        "• <b>/reset</b> — стереть память активного диалога.\n\n"
        f"<b>💰 Экономика</b>\n"
        f"• Старт: 100 🪙\n"
        f"• Создание девушки: {COST_NEW_GIRL} 🪙\n"
        f"• Ежедневный бонус: +{DAILY_BONUS} 🪙\n\n"
        "<b>🧠 Память</b>\n"
        "Со временем она запоминает важные факты о тебе и помнит между сессиями."
    )
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="mn:home")]],
    ))
    await cb.answer()


# ============== СПИСОК ДЕВУШЕК ==============

@router.callback_query(F.data == "mn:girls")
async def cb_girls(cb: CallbackQuery, storage: ProfileStorage) -> None:
    profile = await storage.get(cb.from_user.id)
    girls = profile.list_girls()
    rows = []
    for g in girls:
        active = " ✅" if g.id == profile.active_girl_id else ""
        rows.append([InlineKeyboardButton(
            text=f"{g.name}, {g.age}{active}",
            callback_data=f"gl:open:{g.id}",
        )])
    rows.append([InlineKeyboardButton(
        text=f"✨ Создать новую ({COST_NEW_GIRL} 🪙)",
        callback_data="gl:new",
    )])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="mn:home")])
    await cb.message.edit_text(
        f"<b>👯 Мои девушки</b>\n\n"
        f"<i>Активная отмечена ✅</i>\n"
        f"Слотов: {len(girls)} / {MAX_GIRLS}\n"
        f"Баланс: {profile.balance} 🪙",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("gl:open:"))
async def cb_girl_open(cb: CallbackQuery, storage: ProfileStorage) -> None:
    gid = cb.data.split(":", 2)[2]
    profile = await storage.get(cb.from_user.id)
    if gid not in profile.girls:
        await cb.answer("Не найдена", show_alert=True)
        return
    from src.character.girl import Girl
    g = Girl.from_dict(profile.girls[gid])
    is_active = (gid == profile.active_girl_id)
    can_delete = (gid != "default_alisa")

    text = (
        f"<b>{g.name}</b>, {g.age} · {g.city}\n"
        f"<i>{', '.join(g.character) or '—'}</i>\n\n"
        f"💼 {g.occupation}\n"
        f"💗 {g.relationship}\n"
        f"👗 {g.style_clothes}\n"
        f"🎨 Хобби: {', '.join(g.hobbies) if g.hobbies else '—'}\n"
        f"💋 Флирт: {g.flirt_level}\n"
    )
    if is_active:
        text += "\n✅ <i>Сейчас активна.</i>"

    rows: list[list[InlineKeyboardButton]] = []
    if not is_active:
        rows.append([InlineKeyboardButton(text="✅ Сделать активной",
                                          callback_data=f"gl:activate:{gid}")])
    rows.append([InlineKeyboardButton(text="✏️ Редактировать",
                                      callback_data=f"gl:edit:{gid}")])
    if can_delete:
        rows.append([InlineKeyboardButton(text="🗑 Удалить",
                                          callback_data=f"gl:del:{gid}")])
    rows.append([InlineKeyboardButton(text="◀️ К списку", callback_data="mn:girls")])

    await cb.message.edit_text(text,
                               reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await cb.answer()


@router.callback_query(F.data.startswith("gl:activate:"))
async def cb_activate(cb: CallbackQuery, storage: ProfileStorage,
                      memory: ChatMemory) -> None:
    gid = cb.data.split(":", 2)[2]
    profile = await storage.get(cb.from_user.id)
    if profile.set_active(gid):
        # Память диалога — отдельная для каждой девушки, ничего стирать не надо.
        await storage.commit(profile)
        from src.character.girl import Girl
        g = Girl.from_dict(profile.girls[gid])
        await cb.answer(f"Активна: {g.name}")
        await cb_girl_open(cb, storage)
    else:
        await cb.answer("Ошибка", show_alert=True)


@router.callback_query(F.data.startswith("gl:del:"))
async def cb_del_confirm(cb: CallbackQuery) -> None:
    gid = cb.data.split(":", 2)[2]
    await cb.message.edit_text(
        "🗑 <b>Точно удалить?</b>\nЭто действие нельзя отменить.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить",
                                  callback_data=f"gl:delok:{gid}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data=f"gl:open:{gid}")],
        ]),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("gl:delok:"))
async def cb_del_do(cb: CallbackQuery, storage: ProfileStorage,
                    memory: ChatMemory) -> None:
    gid = cb.data.split(":", 2)[2]
    profile = await storage.get(cb.from_user.id)
    if await storage.remove_girl(profile, gid):
        await memory.reset(cb.from_user.id, gid)
        await cb.answer("Удалена")
    else:
        await cb.answer("Не получилось", show_alert=True)
    await cb_girls(cb, storage)


@router.callback_query(F.data == "gl:new")
async def cb_new_girl(cb: CallbackQuery, storage: ProfileStorage,
                      state: FSMContext) -> None:
    user_id = cb.from_user.id
    profile = await storage.get(user_id)
    if len(profile.girls) >= MAX_GIRLS:
        await cb.answer(f"Максимум {MAX_GIRLS}. Удали кого-то.", show_alert=True)
        return
    if profile.balance < COST_NEW_GIRL:
        await cb.answer(
            f"Не хватает {COST_NEW_GIRL - profile.balance} 🪙", show_alert=True,
        )
        return
    # ВАЖНО: передаём user_id явно, чтобы start_wizard не путал бота с юзером.
    await start_wizard(cb.message, user_id, state, storage)
    await cb.answer()


@router.callback_query(F.data.startswith("gl:edit:"))
async def cb_edit_girl(cb: CallbackQuery, storage: ProfileStorage,
                       state: FSMContext) -> None:
    gid = cb.data.split(":", 2)[2]
    user_id = cb.from_user.id
    await start_wizard(cb.message, user_id, state, storage, edit_id=gid)
    await cb.answer()
