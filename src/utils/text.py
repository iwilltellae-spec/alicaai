"""Утилиты текста: курсив, разбиение на сообщения, форматирование дат."""
from __future__ import annotations

import datetime
import re

# *текст* — удаляем целиком вместе с содержимым (по запросу пользователя
# никаких "*обнимаю*", "*смущаюсь*" и подобного на выходе).
_ASTERISK = re.compile(r"\s*\*[^*\n]{1,200}\*\s*")

RUS_MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]
RUS_WEEKDAYS = [
    "понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье",
]


def strip_asterisks(text: str) -> str:
    """*обнимаю* → '' (полностью убираем «актёрские ремарки» из ответа)."""
    out = _ASTERISK.sub(" ", text)
    # Чистим возможные двойные пробелы.
    out = re.sub(r"[ \t]{2,}", " ", out)
    # И убираем пробелы вокруг переносов строк.
    out = re.sub(r" *\n *", "\n", out)
    return out.strip()


# Старое имя для обратной совместимости.
asterisks_to_italic = strip_asterisks


def split_messages(text: str, max_parts: int = 8) -> list[str]:
    """
    Разбивает ответ модели на отдельные сообщения.

    Алгоритм:
    1. Сначала режем по пустой строке (\\n\\n) — основной разделитель.
    2. Если какой-то кусок всё равно длинный (>140 символов) — режем дальше
       по предложениям, чтобы не было «3 коротких + 1 простыня».
    3. Жёсткий потолок max_parts, иначе склеиваем хвост.
    """
    raw_parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not raw_parts:
        return [text.strip()] if text.strip() else []

    # Дополнительное дробление длинных кусков по предложениям.
    parts: list[str] = []
    for p in raw_parts:
        if len(p) <= 140:
            parts.append(p)
            continue
        # Режем по . ! ? но сохраняем знак в результате.
        sentences = re.split(r"(?<=[.!?…])\s+", p)
        cur = ""
        for s in sentences:
            if not cur:
                cur = s
            elif len(cur) + 1 + len(s) <= 140:
                cur = cur + " " + s
            else:
                parts.append(cur.strip())
                cur = s
        if cur.strip():
            parts.append(cur.strip())

    if len(parts) > max_parts:
        head = parts[: max_parts - 1]
        tail = " ".join(parts[max_parts - 1:])
        parts = head + [tail]
    return parts


def typing_pause(text: str) -> float:
    """Реалистичная пауза «как будто печатает».
    Целимся на ~15-20 знаков/сек (нормальная печать на телефоне),
    минимум 1.5с, максимум 5с."""
    return max(1.5, min(5.0, 0.8 + len(text) * 0.06))


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
