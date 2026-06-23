"""Главное меню, профиль, список девушек, переключение, удаление."""
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


@router.message(Command("menu"))
async def cmd_menu(message: Message, storage: ProfileStorage, memory: ChatMemory) -> None:
    if not memory.has_consent(message.from_user.id):
        await message.answer("Сначала /start и подтверди возраст.")
        return
    profile = storage.get(message.from_user.id)
    girl = profile.get_active_girl()
    storage.commit(profile)
    await message.answer(
        f"<b>🏠 Главное меню</b>\n\n"
        f"💗 Активна: <b>{girl.name}</b>\n"
        f"💰 Баланс: <b>{profile.balance} 🪙</b>\n"
        f"👯 Девушек: {len(profile.girls)} / {MAX_GIRLS}",
        reply_markup=_main_menu_kb(),
    )


@router.callback_query(F.data == "mn:home")
async def cb_home(cb: CallbackQuery, storage: ProfileStorage) -> None:
    profile = storage.get(cb.from_user.id)
    girl = profile.get_active_girl()
    storage.commit(profile)
    await cb.message.edit_text(
        f"<b>🏠 Главное меню</b>\n\n"
        f"💗 Активна: <b>{girl.name}</b>\n"
        f"💰 Баланс: <b>{profile.balance} 🪙</b>\n"
        f"👯 Девушек: {len(profile.girls)} / {MAX_GIRLS}",
        reply_markup=_main_menu_kb(),
    )
    await cb.answer()


# ============== ПРОФИЛЬ ==============

@router.callback_query(F.data == "mn:profile")
async def cb_profile(cb: CallbackQuery, storage: ProfileStorage,
                     memory: ChatMemory) -> None:
    profile = storage.get(cb.from_user.id)
    girl = profile.get_active_girl()
    msg_count = memory.message_count(cb.from_user.id)
    await cb.message.edit_text(
        f"<b>👤 Твой профиль</b>\n\n"
        f"🆔 <code>{cb.from_user.id}</code>\n"
        f"💰 Баланс: <b>{profile.balance} 🪙</b>\n"
        f"👯 Девушек создано: <b>{len(profile.girls)}</b> / {MAX_GIRLS}\n"
        f"💬 Сообщений в текущем диалоге: <b>{msg_count}</b>\n\n"
        f"💗 Активна сейчас: <b>{girl.name}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="mn:home")],
        ]),
    )
    await cb.answer()


# ============== БОНУС ==============

@router.callback_query(F.data == "mn:bonus")
async def cb_bonus(cb: CallbackQuery, storage: ProfileStorage) -> None:
    profile = storage.get(cb.from_user.id)
    got = profile.claim_daily_bonus()
    storage.commit(profile)
    if got > 0:
        text = (
            f"🎁 <b>Бонус получен!</b>\n\n"
            f"+{got} 🪙\n"
            f"Баланс: <b>{profile.balance} 🪙</b>\n\n"
            f"<i>Возвращайся завтра.</i>"
        )
    else:
        text = (
            "⏳ <b>Уже получил сегодня.</b>\n\n"
            f"Возвращайся через ~24 часа.\n"
            f"Баланс: <b>{profile.balance} 🪙</b>"
        )
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="mn:home")]],
    ))
    await cb.answer()


# ============== HELP ==============

@router.callback_query(F.data == "mn:help")
async def cb_help(cb: CallbackQuery) -> None:
    text = (
        "<b>ℹ️ Как пользоваться</b>\n\n"
        "• Просто пиши сообщения активной девушке.\n"
        "• <b>/menu</b> — открыть это меню.\n"
        "• <b>/reset</b> — стереть память диалога с активной.\n\n"
        f"<b>💰 Экономика</b>\n"
        f"• Старт: 100 🪙\n"
        f"• Создание новой девушки: {COST_NEW_GIRL} 🪙\n"
        f"• Ежедневный бонус: +{DAILY_BONUS} 🪙\n\n"
        "<b>👯 Девушки</b>\n"
        f"• Можно создать до {MAX_GIRLS} разных персонажей.\n"
        "• У каждой 25+ параметров — все влияют на её поведение.\n"
        "• Любую можно отредактировать или удалить.\n"
        "• Дефолтную Алису удалить нельзя.\n\n"
        "<i>Память между перезагрузками сервиса сохраняется в /tmp.\n"
        "При новом деплое сбрасывается.</i>"
    )
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="mn:home")]],
    ))
    await cb.answer()


# ============== СПИСОК ДЕВУШЕК ==============

@router.callback_query(F.data == "mn:girls")
async def cb_girls(cb: CallbackQuery, storage: ProfileStorage) -> None:
    profile = storage.get(cb.from_user.id)
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
    profile = storage.get(cb.from_user.id)
    if gid not in profile.girls:
        await cb.answer("Не найдена", show_alert=True)
        return
    from src.character.girl import Girl
    g = Girl.from_dict(profile.girls[gid])
    is_active = (gid == profile.active_girl_id)
    can_delete = (gid != "default_alisa")

    text = (
        f"<b>{g.name}</b>, {g.age} · {g.city}\n"
        f"<i>{', '.join(g.character)}</i>\n\n"
        f"💼 {g.occupation}\n"
        f"💗 {g.relationship}\n"
        f"👗 {g.style_clothes}\n"
        f"🎨 Хобби: {', '.join(g.hobbies) if g.hobbies else '—'}\n"
        f"💋 Флирт: {g.flirt_level}\n"
    )
    if is_active:
        text += "\n✅ <i>Сейчас активна — пиши прямо в чат.</i>"

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
    profile = storage.get(cb.from_user.id)
    if profile.set_active(gid):
        # Сбрасываем историю диалога при переключении.
        memory.reset(cb.from_user.id)
        storage.commit(profile)
        from src.character.girl import Girl
        g = Girl.from_dict(profile.girls[gid])
        await cb.answer(f"Активна: {g.name}", show_alert=False)
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
    profile = storage.get(cb.from_user.id)
    if profile.remove_girl(gid):
        memory.reset(cb.from_user.id)
        storage.commit(profile)
        await cb.answer("Удалена", show_alert=False)
    else:
        await cb.answer("Не получилось", show_alert=True)
    await cb_girls(cb, storage)


@router.callback_query(F.data == "gl:new")
async def cb_new_girl(cb: CallbackQuery, storage: ProfileStorage,
                      state: FSMContext) -> None:
    profile = storage.get(cb.from_user.id)
    if len(profile.girls) >= MAX_GIRLS:
        await cb.answer(f"Уже максимум ({MAX_GIRLS}). Удали кого-то.", show_alert=True)
        return
    if profile.balance < COST_NEW_GIRL:
        await cb.answer(
            f"Не хватает: нужно {COST_NEW_GIRL}, у тебя {profile.balance} 🪙",
            show_alert=True,
        )
        return
    # Запускаем визард как сообщение.
    await cb.message.delete()
    await start_wizard(cb.message, state, storage)
    await cb.answer()


@router.callback_query(F.data.startswith("gl:edit:"))
async def cb_edit_girl(cb: CallbackQuery, storage: ProfileStorage,
                       state: FSMContext) -> None:
    gid = cb.data.split(":", 2)[2]
    await cb.message.delete()
    await start_wizard(cb.message, state, storage, edit_id=gid)
    await cb.answer()
