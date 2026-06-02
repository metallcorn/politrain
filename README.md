# Politrain 🇵🇱

AI-тренажёр польского языка для русскоязычных пользователей. Генерирует персонализированные упражнения через Mistral AI, адаптируется к уровню и прогрессу каждого пользователя.

## Возможности

**Тренировки**
- Ежедневные сессии с 8 типами упражнений: заполнение пропусков, выбор из вариантов, перевод, порядок слов, карточки, «верно/неверно», сборка из букв, угадай слово по описанию
- Бонусные тренировки с упражнениями уровня выше текущего
- Режим работы над ошибками
- Режим повторения пройденного
- AI-тесты по конкретным грамматическим темам

**Словарь**
- Интервальные повторения (SM-2) для запоминания слов
- Автодобавление новых слов когда пул заканчивается
- Статистика прогресса

**Умная генерация**
- Общий пул AI-упражнений: Mistral вызывается один раз, все пользователи получают упражнения из пула
- Жалоба на плохое упражнение — деактивируется глобально (никто больше не видит)
- 5 параллельных батчей генерации (grammar / lexical / judge / letter_tiles / word_definition)
- Упражнения тегируются темой грамматики для контекстной генерации

**Прогресс и геймификация**
- XP, стрики, достижения
- Прогресс по грамматическим темам (A0 → B1)
- Дашборд активности: кольцо цели, график по неделям/месяцам

**Дополнительно**
- AI-чат на польском с исправлением ошибок
- AI-объяснение любого ответа (2 уровня детализации, кешируется)
- Тренировка идиом
- Экзаменационные задания
- Распознавание речи (Deepgram)
- PWA — устанавливается на телефон как приложение

## Стек

| Слой | Технологии |
|---|---|
| Backend | Python, FastAPI, SQLAlchemy, SQLite |
| Frontend | React 18, Vite, Tailwind CSS, Zustand |
| AI | Mistral API (mistral-large-latest / mistral-small-latest) |
| Auth | JWT (python-jose) |
| Speech | Deepgram STT, Edge TTS |
| Deploy | nginx + uvicorn, HTTPS (Let's Encrypt), PWA |

## Структура проекта

```
politrain_code/
├── backend/
│   ├── main.py              # FastAPI app, миграции при старте
│   ├── models.py            # SQLAlchemy модели
│   ├── schemas.py           # Pydantic schemas
│   ├── prompts.py           # Все промты для Mistral
│   ├── routers/
│   │   ├── training.py      # Сессии, генерация упражнений, пул
│   │   ├── topics.py        # Грамматические темы и уроки
│   │   ├── vocabulary.py    # Словарный прогресс
│   │   ├── profile.py       # Профиль, достижения, дашборд
│   │   ├── admin.py         # Жалобы, статистика API, пул упражнений
│   │   ├── chat.py          # AI-чат
│   │   └── auth.py          # Регистрация, логин
│   └── services/
│       ├── mistral.py       # Обёртка Mistral API с логированием
│       ├── gamification.py  # XP, стрики, достижения
│       └── sm2.py           # Алгоритм интервального повторения
└── frontend/
    └── src/
        ├── pages/           # TrainingPage, ProfilePage, AdminPage...
        ├── components/
        │   ├── training/    # FillBlank, Flashcard, JudgeSentence...
        │   ├── gamification/# ActivityDashboard, XPBar...
        │   └── admin/       # MistralUsageChart
        └── api/index.js     # Все API вызовы
```

## Запуск

### Требования
- Python 3.11+
- Node.js 18+
- Mistral API key
- Deepgram API key (опционально, для речи)

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Создать .env (см. .env.example)
cp ../.env.example .env
# Заполнить SECRET_KEY, MISTRAL_API_KEY и др.

uvicorn main:app --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev        # разработка
npm run build      # production сборка → dist/
```

### nginx (production)
Проксирует `/api/` на uvicorn, отдаёт `frontend/dist/` статикой.
Обязательно: `proxy_read_timeout 90s` — Mistral может отвечать до 60 секунд.

## Типы упражнений

| Тип | Описание |
|---|---|
| `fill_blank` | Вставить пропущенное слово в польское предложение |
| `multiple_choice` | Выбрать правильный вариант из 4 |
| `translate` | Перевести фразу с русского на польский |
| `order_words` | Собрать предложение из перемешанных слов |
| `flashcard` | Карточка: польское слово → перевод |
| `judge_sentence` | Оценить правильность польского предложения |
| `letter_tiles` | Собрать слово из букв-плиток |
| `word_definition` | Угадать польское слово по описанию на польском |

## Лицензия

GPL v2
