"""Сборка системного промпта (статика + динамика + факты)."""
from __future__ import annotations

import datetime
from typing import Optional

from src.character.girl import Girl
from src.services.mood import Mood
from src.services.weather import Weather
from src.utils.text import RUS_WEEKDAYS, format_date_ru, time_of_day_label


def build_system_prompt(
    *,
    girl: Girl,
    mood: Mood,
    weather: Optional[Weather],
    now: datetime.datetime,
    facts: Optional[list[str]] = None,
    style: str = "reply",
) -> str:
    weekday = RUS_WEEKDAYS[now.weekday()]
    tod = time_of_day_label(now.hour)
    date_str = format_date_ru(now)

    facts_text = ""
    if facts:
        facts_text = "\n".join(f"- {f}" for f in facts)

    parts = [girl.to_system_prompt(user_facts=facts_text)]
    parts.append("\n# СЕЙЧАС (используй естественно, не зачитывай как сводку)")
    parts.append(f"- Дата: {date_str}, {weekday}, {tod} ({now.strftime('%H:%M')} по Москве)")
    if weather:
        parts.append(f"- Погода у тебя в {weather.city}: {weather.temp_c}°C, {weather.description}")
    parts.append(f"- Твоё настроение: {mood.label}")

    if style == "initiative":
        parts.append(
            "\n# Ты пишешь ПЕРВОЙ\n"
            "Он давно молчит. Напиши сама — что-то простое, по настроению. "
            "1-2 коротких сообщения, без формального «привет»."
        )
    elif style == "photo":
        parts.append(
            "\n# Он прислал фото\n"
            "Посмотри что на нём и отреагируй естественно, коротко, с эмоцией."
        )

    if mood.score <= -1.5:
        parts.append("\n⚠️ Ты на него обижена. Прохладнее, короче, с дистанцией.")
    elif mood.score >= 2:
        parts.append("\n💕 Ты сейчас очень любишь его. Теплее, нежнее.")

    return "\n".join(parts)
