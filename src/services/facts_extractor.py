"""
Извлечение долгосрочных фактов о пользователе.

После каждых N пар сообщений вызываем LLM, отдаём:
- Новые сообщения переписки
- Уже сохранённые факты (чтобы не повторял)

Получаем строго НОВЫЕ факты, без дубликатов.
Дополнительно — дедуп на выходе через нормализацию строки.
"""
from __future__ import annotations

import re

from src.services.openrouter import OpenRouterClient, OpenRouterError
from src.utils.logger import get_logger

logger = get_logger(__name__)


EXTRACT_PROMPT = """\
Ты — экстрактор фактов о ПОЛЬЗОВАТЕЛЕ из переписки.

В переписке две роли:
- ПОЛЬЗОВАТЕЛЬ (помечен "ОН:") — это собеседник мужчина
- ДЕВУШКА (помечен "ОНА:") — это AI-персонаж

⚠️ КРИТИЧЕСКИ ВАЖНО:
- Тебе нужны факты ТОЛЬКО О ПОЛЬЗОВАТЕЛЕ.
- Игнорируй ВСЁ что говорит про себя ДЕВУШКА (её имя, возраст, работу, и т.п.).
- Бери ТОЛЬКО утверждения которые ПОЛЬЗОВАТЕЛЬ сказал о СЕБЕ.
- Если девушка спросила "тебе сколько?" и пользователь ответил "25" — это факт \
  пользователя ("Ему 25 лет").
- Если девушка сказала "мне 25" — это НЕ факт пользователя, ИГНОРИРОВАТЬ.

⚠️ НЕ ПОВТОРЯЙ УЖЕ ИЗВЕСТНЫЕ ФАКТЫ:
Ниже список фактов которые УЖЕ сохранены. Не выводи их повторно даже \
другими словами. Выводи ТОЛЬКО действительно новую информацию.

УЖЕ ИЗВЕСТНО О ПОЛЬЗОВАТЕЛЕ:
{known_facts}

Если ничего НОВОГО о пользователе нет — верни ровно слово: НИЧЕГО

Что считаем фактом (если этого ещё нет в списке выше):
- имя, возраст, город, работа, учёба
- семья, питомцы
- хобби, любимая еда, музыка, игры
- важные события, мнения, состояние

Формат вывода (короткие утверждения в третьем лице, по одному на строке):
Зовут Саша
Ему 28 лет
Работает программистом

Без нумерации, без тире, максимум 5 фактов.

ПЕРЕПИСКА:
{conversation}

НОВЫЕ ФАКТЫ:"""


def _normalize(s: str) -> str:
    """Для дедупа: убираем пунктуацию, в нижний регистр."""
    s = re.sub(r"[^\w\s]", "", s.lower())
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _is_similar(a: str, b: str) -> bool:
    """Грубая похожесть: одна строка содержится в другой ИЛИ оба содержат
    одинаковое ключевое слово вокруг общих маркеров (зовут, лет, работает)."""
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if na in nb or nb in na:
        return True
    # пересечение слов > 70%
    wa, wb = set(na.split()), set(nb.split())
    if wa and wb:
        common = wa & wb
        if len(common) / min(len(wa), len(wb)) > 0.7:
            return True
    return False


async def extract_facts(
    llm: OpenRouterClient,
    history: list[dict],
    known_facts: list[str],
    last_n: int = 12,
) -> list[str]:
    if not history:
        return []
    tail = history[-last_n:]
    conv_lines = []
    for m in tail:
        role = "ОН" if m["role"] == "user" else "ОНА"
        content = m["content"] if isinstance(m["content"], str) else str(m["content"])
        conv_lines.append(f"{role}: {content}")
    conv = "\n".join(conv_lines)

    known_block = (
        "\n".join(f"- {f}" for f in known_facts) if known_facts else "(пока ничего)"
    )

    try:
        reply = await llm.chat(
            [{"role": "user", "content": EXTRACT_PROMPT.format(
                conversation=conv, known_facts=known_block,
            )}],
            temperature=0.2,
            max_tokens=300,
        )
    except OpenRouterError as e:
        logger.warning("Facts extraction failed: %s", e)
        return []

    reply = reply.strip()
    if not reply or reply.upper().startswith("НИЧЕГО"):
        return []

    # Парсим строки.
    candidates: list[str] = []
    for line in reply.split("\n"):
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^[-•*\d.)\s]+", "", line).strip()
        if not line or len(line) > 200:
            continue
        if line.upper().startswith("НИЧЕГО"):
            continue
        candidates.append(line)

    # Дедуп против known + против самих себя.
    result: list[str] = []
    for c in candidates:
        if any(_is_similar(c, k) for k in known_facts):
            continue
        if any(_is_similar(c, r) for r in result):
            continue
        result.append(c)

    return result[:5]
