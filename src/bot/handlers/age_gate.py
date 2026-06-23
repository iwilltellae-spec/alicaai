"""
Возрастной gate: при первом /start спрашиваем подтверждение 18+.
Без подтверждения чат не отвечает.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from src.services.memory import ChatMemory
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = Router(name="age_gate")


AGE_GATE_TEXT = (
    "<b>🔞 Подтверждение возраста</b>\n\n"
    "Этот бот — приватный собеседник 18+. Внутри может быть откровенный контент, "
    "включая эротические темы.\n\n"
    "Подтверди, что тебе исполнилось <b>18 лет</b> и ты осознанно соглашаешься "
    "на такое общение."
)

WELCOME_AFTER_CONSENT = (
    "Привет 🙈\n"
    "Я Алиса. Ну что, познакомимся?\n\n"
    "<i>Команды: /help</i>"
)


def _consent_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Мне 18+", callback_data="age:yes"),
                InlineKeyboardButton(text="❌ Нет", callback_data="age:no"),
            ]
        ]
    )


@router.message(Command("start"))
async def cmd_start(message: Message, memory: ChatMemory) -> None:
    if memory.has_consent(message.from_user.id):
        await message.answer("Я тут 🥰 Напиши мне.")
        return
    await message.answer(AGE_GATE_TEXT, reply_markup=_consent_keyboard())


@router.callback_query(F.data == "age:yes")
async def consent_yes(query: CallbackQuery, memory: ChatMemory) -> None:
    memory.grant_consent(query.from_user.id)
    logger.info("Consent granted: user=%s", query.from_user.id)
    await query.message.edit_text(WELCOME_AFTER_CONSENT)
    await query.answer()


@router.callback_query(F.data == "age:no")
async def consent_no(query: CallbackQuery) -> None:
    await query.message.edit_text(
        "Окей, тогда этот бот не для тебя. Возвращайся, когда исполнится 18."
    )
    await query.answer()
