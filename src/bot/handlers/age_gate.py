"""Возрастной gate + переход в главное меню."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from src.services.memory import ChatMemory
from src.services.profile import ProfileStorage
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = Router(name="age_gate")


AGE_GATE_TEXT = (
    "<b>🔞 Подтверждение возраста</b>\n\n"
    "Этот бот — приватный собеседник 18+. Внутри откровенный контент, "
    "включая эротические темы.\n\n"
    "Подтверди, что тебе исполнилось <b>18 лет</b>."
)


def _consent_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Мне 18+", callback_data="age:yes"),
        InlineKeyboardButton(text="❌ Нет", callback_data="age:no"),
    ]])


@router.message(Command("start"))
async def cmd_start(message: Message, memory: ChatMemory,
                    storage: ProfileStorage) -> None:
    if memory.has_consent(message.from_user.id):
        profile = storage.get(message.from_user.id)
        girl = profile.get_active_girl()
        storage.commit(profile)
        await message.answer(
            f"С возвращением 👋\n"
            f"Активна: <b>{girl.name}</b>\n\n"
            f"Просто пиши ей. Или открой /menu."
        )
        return
    await message.answer(AGE_GATE_TEXT, reply_markup=_consent_kb())


@router.callback_query(F.data == "age:yes")
async def consent_yes(query: CallbackQuery, memory: ChatMemory,
                      storage: ProfileStorage) -> None:
    memory.grant_consent(query.from_user.id)
    profile = storage.get(query.from_user.id)
    girl = profile.get_active_girl()
    storage.commit(profile)
    logger.info("Consent: user=%s, balance=%d", query.from_user.id, profile.balance)

    await query.message.edit_text(
        f"Готово ✅\n\n"
        f"Тебя ждёт <b>{girl.name}</b>.\n"
        f"💰 Стартовый баланс: <b>{profile.balance} 🪙</b>\n\n"
        f"Просто напиши ей.\n"
        f"Открыть меню — /menu",
    )
    await query.answer()


@router.callback_query(F.data == "age:no")
async def consent_no(query: CallbackQuery) -> None:
    await query.message.edit_text("Окей. Возвращайся когда исполнится.")
    await query.answer()
