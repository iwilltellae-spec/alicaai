# 💬 Character Chat Bot — Алиса

Личный Telegram-собеседник 18+. Девушка-персонаж, общается естественно и без цензуры,
через бесплатные LLM-модели OpenRouter.

---

## ✨ Что внутри

- **Персонаж «Алиса»** — описан в `src/character/persona.py`. Меняй текст — меняешь характер.
- **OpenRouter** как LLM-провайдер. По умолчанию `deepseek/deepseek-chat-v3.1:free`.
- **Возрастной gate** — при первом `/start` спрашивает подтверждение 18+.
- **Память** — последние 20 сообщений (настраивается), in-memory.
- **Whitelist** — бот приватный, отвечает только тебе.
- **Keep-alive** — сам себя пингует, чтобы Render free не засыпал.

---

## 🚀 Деплой на Render (как в voice-changer-bot)

### 1. Получи ключи

- **BOT_TOKEN** — [@BotFather](https://t.me/BotFather) → `/newbot` → новый бот.
- **OPENROUTER_API_KEY** — https://openrouter.ai → войди через Google/GitHub →
  https://openrouter.ai/keys → **Create Key**.
- **Твой Telegram user_id** — [@userinfobot](https://t.me/userinfobot).

### 2. Залей на GitHub

Создай **новый** репозиторий (отдельный от voice-changer-bot) и залей туда содержимое
папки `character-chat-bot/`.

### 3. Подключи к Render

1. https://dashboard.render.com → **New + → Blueprint**.
2. Выбери репозиторий.
3. Render найдёт `render.yaml` → попросит ввести 3 секрета:
   - `BOT_TOKEN`
   - `OPENROUTER_API_KEY`
   - `ALLOWED_USER_IDS` (твой Telegram ID)
4. **Apply** → 2-3 минуты на сборку.

### 4. Тест

В Telegram: `/start` → подтверди 18+ → начни писать.

---

## 🎭 Как поменять персонажа

Открой `src/character/persona.py` → меняй `PERSONA_TEXT` → залей в GitHub → Render передеплоит.

Можно сделать кого угодно: парня вместо девушки, друга, гота, доминатрикс, наоборот
застенчивую — модель подстраивается под промпт.

---

## 🧠 Как поменять модель

В Render → Environment → `OPENROUTER_MODEL` → впиши другую модель.

**Хорошие бесплатные на 2026:**
- `deepseek/deepseek-chat-v3.1:free` ⭐ — баланс качества и свободы
- `meta-llama/llama-3.3-70b-instruct:free` — умная, но иногда «правильная»
- `nousresearch/hermes-3-llama-3.1-405b:free` — большая, неплохой ролеплей
- `google/gemini-2.0-flash-exp:free` — быстрая, но цензурит

**Платные за копейки (если задушит качество):**
- `gryphe/mythomax-l2-13b` — ~$0.07/M токенов, легендарная для ролеплея
- `sao10k/l3-lunaris-8b` — ~$0.02/M, свежая ролеплей-модель
- `neversleep/llama-3-lumimaid-8b` — мягкая, эмоциональная

Положить $2 на OpenRouter = месяца на 2-3 активной болтовни.

Актуальный список: https://openrouter.ai/models?max_price=0

---

## ⚠️ Известные ограничения (free Render + free OpenRouter)

| Что | Как это выглядит | Что делать |
|---|---|---|
| Render free засыпает | Первый ответ после паузы — 30-60 сек | Keep-alive уже включён, но он не 100% |
| Память сбрасывается при деплое | После `git push` Алиса «забывает» | Это норма (без БД). Хочешь сохранить — нужен Postgres |
| OpenRouter free лимиты | `429 Too Many Requests` | Подожди 30 сек или смени модель |
| Модель «слетела» в отказ | «Я не могу обсуждать...» | `/reset` и переформулируй мягче |

---

## 🛠 Структура

```
character-chat-bot/
├── src/
│   ├── main.py
│   ├── config.py
│   ├── character/
│   │   └── persona.py          ← персонаж тут
│   ├── services/
│   │   ├── openrouter.py       ← клиент LLM
│   │   ├── memory.py           ← история + 18+ согласие
│   │   └── keepalive.py
│   ├── bot/
│   │   ├── menu.py
│   │   ├── handlers/
│   │   │   ├── age_gate.py     ← 18+ подтверждение
│   │   │   ├── chat.py         ← основной чат
│   │   │   └── commands.py     ← /help, /reset, /who
│   │   └── middlewares/
│   │       ├── dependencies.py
│   │       └── whitelist.py
│   └── utils/
│       └── logger.py
├── requirements.txt
├── render.yaml
├── .env.example
└── README.md
```
