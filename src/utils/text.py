"""Утилиты текста: курсив, разбиение на сообщения, форматирование дат."""
from __future__ import annotations

import datetime
import re

# *текст* → <i>текст</i> для Telegram HTML.
# Не трогаем переносы строк внутри (одна звёздочка-обёртка на короткое действие).
_ASTERISK = re.compile(r"\*([^*\n]{1,200})\*")

RUS_MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]
RUS_WEEKDAYS = [
    "понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье",
]


def asterisks_to_italic(text: str) -> str:
    """*обнимаю* → <i>обнимаю</i>. Не ломает уже существующий HTML."""
    return _ASTERISK.sub(r"<i>\1</i>", text)


def split_messages(text: str, max_parts: int = 4) -> list[str]:
    """
    Разбивает ответ модели на отдельные сообщения по пустой строке (\\n\\n).
    Это формат «реальный человек в мессенджере»: 2-3 коротких сообщения подряд.
    Ограничено max_parts, иначе склеиваем хвост.
    """
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not parts:
        return [text.strip()] if text.strip() else []
    if len(parts) > max_parts:
        head = parts[: max_parts - 1]
        tail = " ".join(parts[max_parts - 1:])
        parts = head + [tail]
    return parts


def typing_pause(text: str) -> float:
    """Сколько секунд «печатать» сообщение длиной N символов.
    Целимся на ~25-30 знаков/сек (быстрая печать в мессенджере),
    минимум 0.7с, максимум 2.5с — иначе ждать утомительно."""
    return max(0.7, min(2.5, 0.5 + len(text) * 0.03))


def format_date_ru(dt: datetime.datetime) -> str:
    return f"{dt.day} {RUS_MONTHS[dt.month - 1]} {dt.year}"


def time_of_day_label(hour: int) -> str:
    if 5 <= hour < 11:
        return "утро"
    if 11 <= hour < 17:
        return "день"
    if 17 <= hour < 23:
        return "вечер"
    return "глубокая ночь"
