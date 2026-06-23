"""Возрастной gate."""
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
    # Проверим persistent consent — у профиля в БД он мог сохраниться.
    profile = await storage.get(message.from_user.id)
    if profile.consented:
        memory.grant_consent(message.from_user.id)
    if memory.has_consent(message.from_user.id):
        girl = profile.get_active_girl()
        await storage.commit(profile)
        await message.answer(
            f"С возвращением 👋\nАктивна: <b>{girl.name}</b>\n\n"
            f"Просто пиши ей. Меню — /menu"
        )
        return
    await message.answer(AGE_GATE_TEXT, reply_markup=_consent_kb())


@router.callback_query(F.data == "age:yes")
async def consent_yes(query: CallbackQuery, memory: ChatMemory,
                      storage: ProfileStorage) -> None:
    memory.grant_consent(query.from_user.id)
    profile = await storage.get(query.from_user.id)
    profile.consented = True
    girl = profile.get_active_girl()
    await storage.commit(profile)
    logger.info("Consent: user=%s, balance=%d", query.from_user.id, profile.balance)
    await query.message.edit_text(
        f"Готово ✅\n\nТебя ждёт <b>{girl.name}</b>.\n"
        f"💰 Стартовый баланс: <b>{profile.balance} 🪙</b>\n\n"
        f"Просто напиши ей.\nМеню — /menu",
    )
    await query.answer()


@router.callback_query(F.data == "age:no")
async def consent_no(query: CallbackQuery) -> None:
    await query.message.edit_text("Окей. Возвращайся когда исполнится.")
    await query.answer()
