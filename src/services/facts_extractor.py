"""
Извлечение долгосрочных фактов о пользователе.

После каждых N пар «он-она» бот делает отдельный лёгкий вызов LLM:
«Прочитай эти 10 сообщений и выпиши важные ФАКТЫ о пользователе:
имя, работа, увлечения, что любит/не любит, важные события,
которые он упомянул. По одному факту в строку. Без воды.»

Эти факты складываются в БД и инжектятся в каждый системный промпт
персонажа. Так Алиса начинает по-настоящему помнить пользователя
между сессиями.
"""
from __future__ import annotations

import re

from src.services.openrouter import OpenRouterClient, OpenRouterError
from src.utils.logger import get_logger

logger = get_logger(__name__)


EXTRACT_PROMPT = """\
Ты — экстрактор фактов. Прочитай переписку и выпиши ТОЛЬКО новые важные ФАКТЫ \
О ПОЛЬЗОВАТЕЛЕ, которые он упомянул о себе и которые девушка должна запомнить.

ВАЖНО:
- Только факты О ПОЛЬЗОВАТЕЛЕ, не о девушке.
- Только то что он сам сказал в этой переписке.
- Если ничего нового — верни ровно слово: НИЧЕГО
- Каждый факт — короткое утверждение в одну строку.
- Максимум 5 фактов.

Что считается фактом:
- имя пользователя, возраст, город
- работа, профессия, учёба
- семья, питомцы
- хобби, любимая еда/музыка/игры
- важные события (что-то случилось)
- мнения и предпочтения, которые он выразил
- его настроение/состояние о котором он сказал

Формат вывода (без нумерации, без тире, без воды):
Зовут Саша
Работает программистом
У него кот Мурзик
Любит тёмное пиво

Переписка:
{conversation}

Факты:"""


async def extract_facts(
    llm: OpenRouterClient,
    history: list[dict],
    last_n: int = 12,
) -> list[str]:
    """Берёт последние last_n сообщений, возвращает список новых фактов."""
    if not history:
        return []
    tail = history[-last_n:]
    conv_lines = []
    for m in tail:
        role = "ОН" if m["role"] == "user" else "ОНА"
        content = m["content"] if isinstance(m["content"], str) else str(m["content"])
        conv_lines.append(f"{role}: {content}")
    conv = "\n".join(conv_lines)

    try:
        reply = await llm.chat(
            [{"role": "user", "content": EXTRACT_PROMPT.format(conversation=conv)}],
            temperature=0.2,
            max_tokens=300,
        )
    except OpenRouterError as e:
        logger.warning("Facts extraction failed: %s", e)
        return []

    reply = reply.strip()
    if not reply or reply.upper().startswith("НИЧЕГО"):
        return []

    # Парсим: каждая непустая строка = факт. Чистим маркеры.
    facts = []
    for line in reply.split("\n"):
        line = line.strip()
        if not line:
            continue
        # убираем маркеры списка
        line = re.sub(r"^[-•*\d.)\s]+", "", line).strip()
        if line and len(line) <= 200:
            facts.append(line)
    return facts[:5]
