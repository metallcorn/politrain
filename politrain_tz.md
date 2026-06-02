# Politrain — Техническое задание
**AI-тренажёр польского языка**
Версия: 1.0 | Дата: май 2026

---

## Содержание

1. [Общее описание](#1-общее-описание)
2. [Стек технологий](#2-стек-технологий)
3. [Архитектура](#3-архитектура)
4. [База данных](#4-база-данных)
5. [API](#5-api)
6. [Авторизация](#6-авторизация)
7. [Онбординг](#7-онбординг)
8. [Модуль: Правила](#8-модуль-правила)
9. [Модуль: Тренировка](#9-модуль-тренировка)
10. [Модуль: Чат](#10-модуль-чат)
11. [Модуль: Экзамен B1](#11-модуль-экзамен-b1)
12. [Геймификация](#12-геймификация)
13. [Профиль и аналитика](#13-профиль-и-аналитика)
14. [Адаптивность](#14-адаптивность)
15. [AI интеграция](#15-ai-интеграция)
16. [STT/TTS заглушки](#16-stttts-заглушки)
17. [Фронтенд](#17-фронтенд)
18. [Деплой](#18-деплой)
19. [Структура проекта](#19-структура-проекта)
20. [Дневная генерация заданий](#20-дневная-генерация-заданий)
21. [Режимы тренировки](#21-режимы-тренировки)
22. [Настройки контента](#22-настройки-контента)

---

## 1. Общее описание

**Politrain** — веб-приложение для самостоятельного изучения польского языка с AI-тьютором. Цель — довести пользователя до уровня B1 через структурированные уроки, адаптивные упражнения, живой диалог и подготовку к официальному экзамену.

### Целевая аудитория
Русско- и англоязычные пользователи, изучающие польский язык самостоятельно.

### Ключевые принципы
- Адаптация под уровень и слабые места конкретного пользователя
- Объяснение правил с обоснованием (почему так, а не иначе)
- Геймификация без навязчивости
- Минимум текста, максимум практики
- Мягкая коррекция ошибок без демотивации

---

## 2. Стек технологий

### Бэкенд
| Компонент | Технология | Версия |
|---|---|---|
| Язык | Python | 3.11+ |
| Фреймворк | FastAPI | latest |
| ORM | SQLAlchemy | 2.x |
| БД | SQLite | — |
| Миграции | Alembic | latest |
| Аутентификация | JWT (python-jose) | — |
| Хеширование паролей | bcrypt (passlib) | — |
| HTTP клиент | httpx | latest |
| Валидация | Pydantic v2 | — |
| Сервер | Uvicorn | latest |

### Фронтенд
| Компонент | Технология |
|---|---|
| Фреймворк | React 18 |
| Сборщик | Vite |
| Стили | Tailwind CSS |
| Роутинг | React Router v6 |
| Состояние | Zustand |
| HTTP | Axios |
| Анимации | Framer Motion |
| Иконки | Lucide React |

### Внешние сервисы
| Сервис | Назначение |
|---|---|
| Mistral API | LLM для AI функций |
| STT | Заглушка (интерфейс готов) |
| TTS | Заглушка (интерфейс готов) |

### Инфраструктура
- VPS: mikrus.xyz (LXC контейнер)
- Веб-сервер: nginx (reverse proxy)
- SSL: Let's Encrypt (certbot)
- Процессы: systemd
- Домен: politrain.metallcorn.online

---

## 3. Архитектура

```
[Браузер / Телефон]
        │
        ▼
[nginx :443 SSL]
        │
        ├──► /api/* ──► [FastAPI :8000] ──► [SQLite]
        │                      │
        │                      └──► [Mistral API]
        │
        └──► /* ──► [React SPA (статика)]
```

### Принципы
- SPA фронтенд, все роуты на клиенте через React Router
- REST API на бэкенде, JSON
- JWT в Authorization header (Bearer)
- Фронт собирается в статику через `vite build`, отдаётся nginx
- Бэкенд запускается как systemd сервис

---

## 4. База данных

### Таблица `users`
```sql
id              INTEGER PRIMARY KEY
username        TEXT UNIQUE NOT NULL
password_hash   TEXT NOT NULL
native_language TEXT NOT NULL          -- 'ru' | 'en'
target_language TEXT NOT NULL DEFAULT 'pl'
level           TEXT NOT NULL DEFAULT 'A0'  -- A0 | A1 | A2 | B1
xp              INTEGER DEFAULT 0
streak_days     INTEGER DEFAULT 0
last_activity   DATE
onboarding_done BOOLEAN DEFAULT FALSE
created_at      DATETIME DEFAULT NOW
```

### Таблица `topics`
```sql
id              INTEGER PRIMARY KEY
slug            TEXT UNIQUE NOT NULL   -- 'alphabet', 'cases', 'verbs' итд
title_ru        TEXT NOT NULL
title_en        TEXT NOT NULL
description_ru  TEXT
description_en  TEXT
level_required  TEXT NOT NULL          -- минимальный уровень для разблокировки
order_index     INTEGER                -- порядок в списке
parent_id       INTEGER REFERENCES topics(id)  -- для подтем
```

### Таблица `user_topic_progress`
```sql
id              INTEGER PRIMARY KEY
user_id         INTEGER REFERENCES users(id)
topic_id        INTEGER REFERENCES topics(id)
status          TEXT DEFAULT 'locked'  -- locked | available | in_progress | done | needs_review
score           REAL DEFAULT 0.0       -- 0.0 - 1.0
attempts        INTEGER DEFAULT 0
last_practiced  DATETIME
```

### Таблица `vocabulary`
```sql
id              INTEGER PRIMARY KEY
polish          TEXT NOT NULL
translation_ru  TEXT NOT NULL
translation_en  TEXT NOT NULL
example_sentence TEXT
topic_id        INTEGER REFERENCES topics(id)
level           TEXT NOT NULL
```

### Таблица `user_vocabulary`
```sql
id              INTEGER PRIMARY KEY
user_id         INTEGER REFERENCES users(id)
vocab_id        INTEGER REFERENCES vocabulary(id)
ease_factor     REAL DEFAULT 2.5       -- SM-2 параметр
interval_days   INTEGER DEFAULT 1      -- SM-2 интервал
next_review     DATE                   -- когда следующее повторение
repetitions     INTEGER DEFAULT 0      -- количество повторений
correct_streak  INTEGER DEFAULT 0
last_reviewed   DATETIME
```

### Таблица `exercises`
```sql
id              INTEGER PRIMARY KEY
type            TEXT NOT NULL     -- fill_blank | translate | order_words | multiple_choice | write
topic_id        INTEGER REFERENCES topics(id)
level           TEXT NOT NULL
question        TEXT NOT NULL
correct_answer  TEXT NOT NULL
options         TEXT              -- JSON массив для multiple_choice
hint            TEXT
explanation     TEXT              -- почему именно такой ответ
```

### Таблица `user_exercise_history`
```sql
id              INTEGER PRIMARY KEY
user_id         INTEGER REFERENCES users(id)
exercise_id     INTEGER REFERENCES exercises(id)
is_correct      BOOLEAN
user_answer     TEXT
time_spent_sec  INTEGER
created_at      DATETIME DEFAULT NOW
```

### Таблица `chat_sessions`
```sql
id              INTEGER PRIMARY KEY
user_id         INTEGER REFERENCES users(id)
created_at      DATETIME DEFAULT NOW
ended_at        DATETIME
message_count   INTEGER DEFAULT 0
topic           TEXT               -- тема разговора если была задана
```

### Таблица `chat_messages`
```sql
id              INTEGER PRIMARY KEY
session_id      INTEGER REFERENCES chat_sessions(id)
role            TEXT NOT NULL      -- 'user' | 'assistant'
content         TEXT NOT NULL
corrections     TEXT               -- JSON: [{original, corrected, explanation}]
created_at      DATETIME DEFAULT NOW
```

### Таблица `achievements`
```sql
id              INTEGER PRIMARY KEY
slug            TEXT UNIQUE NOT NULL
title_ru        TEXT NOT NULL
title_en        TEXT NOT NULL
description_ru  TEXT
description_en  TEXT
icon            TEXT               -- emoji или название иконки
xp_reward       INTEGER DEFAULT 0
condition_type  TEXT               -- streak | vocab_count | topic_done | xp итд
condition_value INTEGER
```

### Таблица `user_achievements`
```sql
id              INTEGER PRIMARY KEY
user_id         INTEGER REFERENCES users(id)
achievement_id  INTEGER REFERENCES achievements(id)
earned_at       DATETIME DEFAULT NOW
```

### Таблица `daily_activity`
```sql
id              INTEGER PRIMARY KEY
user_id         INTEGER REFERENCES users(id)
date            DATE NOT NULL
xp_earned       INTEGER DEFAULT 0
exercises_done  INTEGER DEFAULT 0
chat_messages   INTEGER DEFAULT 0
minutes_spent   INTEGER DEFAULT 0
```

---

## 5. API

### Базовый URL
```
https://politrain.metallcorn.online/api/v1
```

### Авторизация
```
POST   /auth/register
POST   /auth/login
POST   /auth/logout
GET    /auth/me
```

### Онбординг
```
GET    /onboarding/status
POST   /onboarding/settings          -- язык, цели
GET    /onboarding/placement-test    -- получить 10 вопросов теста
POST   /onboarding/placement-test    -- отправить ответы, получить уровень
```

### Темы и правила
```
GET    /topics                       -- список всех тем с прогрессом пользователя
GET    /topics/{slug}                -- детали темы
GET    /topics/{slug}/lesson         -- AI генерирует объяснение правила
POST   /topics/{slug}/lesson/next    -- следующий пример или упражнение на закрепление
POST   /topics/{slug}/complete       -- отметить тему как пройденную
```

### Словарь
```
GET    /vocabulary                   -- слова пользователя
GET    /vocabulary/due               -- слова на повторение сегодня (SM-2)
POST   /vocabulary/{id}/review       -- отметить результат повторения
GET    /vocabulary/stats             -- статистика словаря
```

### Тренировка
```
GET    /training/session             -- получить набор упражнений для сессии
POST   /training/answer              -- отправить ответ на упражнение
GET    /training/stats               -- статистика тренировок
```

### Чат
```
POST   /chat/session                 -- начать новую сессию
GET    /chat/session/{id}            -- история сессии
POST   /chat/session/{id}/message    -- отправить сообщение
GET    /chat/sessions                -- список всех сессий
```

### Экзамен B1
```
GET    /exam/tasks                   -- список типов заданий
GET    /exam/task/{type}             -- получить задание
POST   /exam/task/{type}/submit      -- отправить ответ на проверку AI
GET    /exam/history                 -- история попыток
```

### Профиль и геймификация
```
GET    /profile                      -- полный профиль: уровень, XP, streak, слабые места
GET    /profile/achievements         -- все достижения (earned + locked)
GET    /profile/activity             -- история активности по дням
GET    /profile/weak-spots           -- темы где низкий процент правильных ответов
PUT    /profile/settings             -- изменить язык интерфейса итд
```

### STT/TTS заглушки
```
POST   /stt/transcribe               -- заглушка, возвращает {"text": "", "status": "not_implemented"}
POST   /tts/synthesize               -- заглушка, возвращает {"audio": null, "status": "not_implemented"}
```

---

## 6. Авторизация

### Регистрация
- Поля: `username` (мин. 3 символа, только латиница/цифры), `password` (мин. 8 символов)
- Пароль хешируется через bcrypt
- После регистрации сразу выдаётся JWT

### Вход
- POST `/auth/login` с `username` + `password`
- Возвращает `access_token` (JWT, срок 30 дней)
- Токен хранится в localStorage на фронте
- При каждом запросе передаётся в `Authorization: Bearer <token>`

### Защита роутов
- Все `/api/v1/*` эндпоинты кроме `/auth/*` требуют валидный JWT
- На фронте: если 401 → редирект на /login

---

## 7. Онбординг

Показывается только при первом входе (`onboarding_done = false`).

### Шаг 1 — Язык интерфейса
- Выбор: Русский / English
- Сохраняется в профиль, влияет на язык всех объяснений и переводов

### Шаг 2 — Язык обучения
- Пока только: Polski
- UI готов для добавления языков в будущем

### Шаг 3 — Тест на определение уровня
10 вопросов, генерируются AI (Mistral) с учётом типов:

| № | Тип | Пример |
|---|---|---|
| 1-2 | Перевод слова (A0) | "как будет 'кошка' по-польски?" |
| 3-4 | Выбрать правильную форму (A1) | "Mam ___ (brat/brata/bracie)" |
| 5-6 | Окончание глагола (A1) | "Ona czyta__ książkę" |
| 7-8 | Понять фразу (A2) | "Что значит: Gdzie jest toaleta?" |
| 9-10 | Составить предложение (A2) | Составь фразу из слов: [ja, lubić, muzyka] |

**Подсчёт уровня:**
- 0-3 правильных → A0
- 4-6 → A1
- 7-9 → A2
- 10 → сразу B1 (редкий случай)

После теста: экран с результатом, объяснением уровня и кнопкой "Начать обучение".

---

## 8. Модуль: Правила

### Список тем (начальный набор)

#### Уровень A0
- Алфавит и произношение
- Приветствия и базовые фразы
- Числа 1-100
- Цвета и базовые прилагательные
- Дни недели, месяцы

#### Уровень A1
- Личные местоимения
- Глагол "być" (быть)
- Настоящее время глаголов (-ać, -ić, -yć)
- Именительный падеж (Mianownik)
- Родительный падеж (Dopełniacz)
- Базовые вопросы (Kto? Co? Gdzie? Kiedy?)

#### Уровень A2
- Винительный падеж (Biernik)
- Дательный падеж (Celownik)
- Прошедшее время
- Будущее время
- Степени сравнения прилагательных
- Числительные и даты

#### Уровень B1
- Творительный падеж (Narzędnik)
- Местный падеж (Miejscownik)
- Звательный падеж (Wołacz)
- Условное наклонение
- Глаголы движения
- Несовершенный и совершенный вид глагола

### Структура урока по теме

1. **Заголовок + краткое описание** — что изучаем и зачем
2. **Объяснение правила** — AI генерирует текст на родном языке пользователя, структурированно:
   - Базовое правило (1-2 предложения)
   - Таблица или схема если нужна (форматируется как markdown)
   - 3 примера с переводом
   - Типичные ошибки которые делают русскоязычные/англоязычные
3. **Интерактивные примеры** — пользователь нажимает "следующий пример", AI подбирает новые
4. **Мини-тест** — 5 упражнений на закрепление (из базы exercises)
5. **Итог** — процент правильных, тема отмечается как пройденная или "требует повторения"

### Генерация объяснений (Mistral)

Системный промпт для урока:
```
Ты преподаватель польского языка. Объясняй правила на {native_language}.
Стиль: дружелюбный, конкретный, без воды.
Уровень пользователя: {level}.
Давай примеры от простого к сложному.
Указывай типичные ошибки носителей {native_language}.
Форматируй ответ в markdown.
Не пиши длинные введения, сразу к делу.
```

---

## 9. Модуль: Тренировка

### Типы упражнений

#### 1. Карточки слов (Flashcards)
- Карточка показывает слово на одной стороне
- Анимация flip (Framer Motion) при нажатии — показывает перевод + пример предложения
- Кнопки: "Знаю" / "Не знаю" / "Сложно"
- SM-2 алгоритм пересчитывает интервал повторения

**SM-2 логика:**
```
"Знаю"   → quality = 5, ease_factor растёт, интервал увеличивается
"Сложно" → quality = 3, ease_factor не меняется
"Не знаю"→ quality = 0, интервал сбрасывается до 1 дня
```

#### 2. Заполни пропуск (Fill in the blank)
- Предложение с пропуском: `Ona ___ do szkoły.` (idzie)
- Ввод текстом или выбор из 4 вариантов (зависит от уровня)
- После ответа: правильно/неправильно + объяснение почему

#### 3. Составь предложение (Word order)
- Слова перемешаны, нужно расставить в правильном порядке
- Drag-and-drop на десктопе, tap-to-place на мобиле
- Показывает правильный вариант после ответа

#### 4. Переведи фразу
- Короткая фраза на родном языке → пишешь по-польски
- AI (Mistral) проверяет ответ: принимает близкие варианты, объясняет разницу
- Не требует точного совпадения, оценивает смысл и грамматику

#### 5. Выбери правильную форму (Multiple choice)
- Вопрос: `Mam ___` с 4 вариантами: `brat / brata / bracie / bratem`
- Сразу показывает правильный ответ с объяснением падежа

### Сессия тренировки

- Сессия = 10-15 упражнений
- Система миксует типы упражнений
- Приоритет: слова из `user_vocabulary` где `next_review <= today`
- Потом: упражнения по темам где низкий score
- Потом: новый материал по текущему уровню

### Экран результатов сессии
- Правильных: X из Y
- XP заработано
- Слова которые нужно повторить
- Кнопки: "Ещё сессия" / "В меню"

---

## 10. Модуль: Чат

### Принципы
- Свободный разговор на польском
- AI поддерживает беседу, не читает лекции
- Коррекция ошибок — мягко, в конце сообщения, курсивом
- Не исправляет каждую мелочь — только существенные ошибки

### Формат коррекции
Если пользователь написал: `Ja lubię bardzo muzyka`

AI отвечает по теме разговора, потом добавляет:
```
_Кстати: "lubię muzykę" — после "lubić" нужен винительный падеж (biernik): muzyka → muzykę_
```

### Темы для чата (предлагаются если пользователь не знает о чём говорить)
- Расскажи о своём дне
- Опиши свой город
- Что ты делал на выходных?
- Поговорим о еде
- Твои планы на будущее
- Свободная тема

### Системный промпт для чата
```
Ты дружелюбный польский собеседник. Уровень пользователя: {level}.
Разговариваешь на польском. Отвечай по теме, естественно.
Адаптируй сложность под уровень пользователя.
Если видишь грамматическую ошибку — в конце сообщения мягко укажи на неё
на {native_language}, формат: "Кстати: [оригинал] → [правильно] — [краткое объяснение]"
Не исправляй больше 1-2 ошибок за сообщение.
Не начинай каждое сообщение с исправления — сначала ответь по теме.
```

### История чата
- Хранится в БД (chat_sessions + chat_messages)
- Пользователь видит список прошлых сессий
- Может продолжить старую сессию или начать новую

---

## 11. Модуль: Экзамен B1

Раздел разблокируется когда пользователь достигает уровня A2.

### Типы заданий (по формату реального экзамена B1)

#### 1. Rozumienie tekstów pisanych (Чтение)
- Текст 200-300 слов на польском (генерируется AI)
- 5 вопросов с выбором ответа
- AI проверяет и объясняет правильные ответы

#### 2. Rozumienie ze słuchu (Аудирование)
- Заглушка в MVP
- Кнопка есть, при нажатии: "Скоро будет доступно"

#### 3. Poprawność gramatyczna (Грамматика)
- 20 вопросов на грамматику уровня B1
- Все типы падежей, виды глаголов, времена

#### 4. Pisanie (Письмо)
- Задание: написать письмо / email / сообщение по заданной ситуации
- Объём: 80-100 слов
- AI оценивает по критериям:
  - Выполнение задания (0-5 баллов)
  - Словарный запас (0-5 баллов)
  - Грамматика (0-5 баллов)
  - Связность текста (0-5 баллов)
- Возвращает оценку + конкретные комментарии

#### 5. Mówienie (Говорение)
- Заглушка в MVP
- Кнопка есть, при нажатии: "Скоро будет доступно"

### Результаты экзамена
- Итоговый процент готовности к B1
- Разбивка по категориям
- Рекомендации что подтянуть

---

## 12. Геймификация

### XP система

| Действие | XP |
|---|---|
| Правильный ответ в упражнении | +10 |
| Неправильный ответ | +2 (за попытку) |
| Завершить тему | +50 |
| Завершить сессию тренировки | +30 |
| Сообщение в чате | +5 |
| День streak | +20 × (день streak) |
| Получить достижение | по достижению |

### Уровни профиля (игровые, не языковые)

| Уровень | XP порог | Название |
|---|---|---|
| 1 | 0 | Новичок |
| 2 | 200 | Ученик |
| 3 | 500 | Студент |
| 4 | 1000 | Знаток |
| 5 | 2000 | Полиглот |
| 6 | 4000 | Мастер |
| 7 | 8000 | Эксперт |
| 8 | 15000 | Легенда |

### Streak (серия дней)
- Засчитывается день если сделано минимум 1 упражнение или 5 сообщений в чате
- Счётчик виден на главной странице
- При заходе если вчера не занимался — streak сгорает, уведомление

### Достижения

| Slug | Название | Условие |
|---|---|---|
| first_lesson | Первый шаг | Завершить первый урок |
| week_streak | Неделя подряд | 7 дней streak |
| month_streak | Месяц подряд | 30 дней streak |
| vocab_100 | Сотня слов | 100 слов в словаре |
| vocab_500 | Пятьсот слов | 500 слов в словаре |
| chat_starter | Разговорчивый | Первые 10 сообщений в чате |
| chat_100 | Болтун | 100 сообщений в чате |
| all_a1 | Уровень A1 | Пройти все темы A1 |
| all_a2 | Уровень A2 | Пройти все темы A2 |
| b1_ready | Готов к B1 | Пройти все темы B1 |
| perfect_session | Отличник | Сессия без единой ошибки |
| speed_demon | Быстрый | 10 правильных ответов за 2 минуты |

### Прогресс к B1
На главной странице — горизонтальная шкала прогресса:
```
Прогресс к B1: [████████░░░░░░░░░░░░] 42%
```
Считается как: (пройденные темы / всего тем) × 100

---

## 13. Профиль и аналитика

### Страница профиля
- Аватар (генерируется из инициалов, без загрузки)
- Username, дата регистрации
- Текущий языковой уровень (A0-B1) с прогресс-баром до следующего
- Игровой уровень + XP прогресс-бар
- Streak счётчик с календарём активности (GitHub-style heatmap)
- Достижения: полученные (цветные) + заблокированные (серые)

### Слабые места
Автоматически вычисляются:
- Топ-3 темы с наименьшим score
- Топ-5 слов которые чаще всего неправильно отвечают
- Типы упражнений где процент ошибок выше среднего

Отображаются на главной как рекомендации: "Рекомендуем повторить: Падежи (34%)"

### Статистика
- Дней обучения всего
- Слов выучено
- Упражнений выполнено
- Часов в приложении
- Сообщений в чате

---

## 14. Адаптивность

### Определение слабых мест
После каждого упражнения система обновляет score темы:
```
new_score = (old_score × (attempts - 1) + result) / attempts
```
где `result` = 1.0 (правильно) или 0.0 (неправильно)

### Адаптация контента
- Если score темы < 0.6 → тема помечается "needs_review"
- При формировании сессии тренировки приоритет темам с низким score
- В чате AI знает слабые места через системный промпт и может аккуратно практиковать их в разговоре

### Рекомендации на главной
Блок "Что сегодня делать":
1. Слова на повторение (SM-2 due)
2. Рекомендованная тема для повторения
3. Продолжить начатую тему если есть

---

## 15. AI интеграция

### Модель
- **Mistral** (конкретная модель: `mistral-large-latest` или `open-mistral-nemo` для экономии)
- API ключ в `.env` файле, никогда не в коде

### Промпты

Все промпты хранятся в отдельном файле `backend/prompts.py` как константы.

#### Промпт для объяснения темы
```python
TOPIC_EXPLANATION_PROMPT = """
Ты преподаватель польского языка. Объясняй правила на {native_language}.
Стиль: дружелюбный, конкретный, без лишних слов.
Уровень пользователя: {level}.

Структура ответа (строго):
1. Суть правила (2-3 предложения)
2. Таблица или схема если нужна (markdown)
3. Три примера с переводом
4. Одна типичная ошибка носителей {native_language}

Тема: {topic_title}
"""
```

#### Промпт для проверки перевода
```python
TRANSLATION_CHECK_PROMPT = """
Пользователь изучает польский, уровень {level}.
Задание было: перевести "{source_text}" с {native_language} на польский.
Ответ пользователя: "{user_answer}"
Правильный ответ: "{correct_answer}"

Оцени ответ. Если смысл верный — засчитай как правильный даже если формулировка другая.
Ответь JSON: {{"correct": true/false, "explanation": "краткое объяснение на {native_language}"}}
Только JSON, без markdown.
"""
```

#### Промпт для чата
```python
CHAT_PROMPT = """
Ты дружелюбный польский собеседник. 
Уровень пользователя: {level}. Родной язык: {native_language}.
Слабые места пользователя: {weak_spots}.

Правила:
- Отвечай на польском
- Адаптируй сложность лексики под уровень
- Если видишь грамматическую ошибку — в конце сообщения одной строкой на {native_language}:
  "Кстати: [что написал] → [как правильно] — [одно слово объяснения]"
- Не исправляй больше 1 ошибки за раз
- Сначала отвечай по теме, потом исправление
- Будь кратким, естественным
"""
```

#### Промпт для оценки письма (B1 экзамен)
```python
WRITING_EVALUATION_PROMPT = """
Ты экзаменатор польского языка уровня B1.
Задание: {task_description}
Ответ студента: {student_text}

Оцени по критериям (каждый 0-5 баллов):
1. Выполнение задания
2. Словарный запас
3. Грамматика  
4. Связность текста

Ответь JSON:
{{
  "scores": {{"task": 0-5, "vocabulary": 0-5, "grammar": 0-5, "coherence": 0-5}},
  "total": 0-20,
  "feedback": "2-3 предложения общего комментария на {native_language}",
  "corrections": ["конкретная ошибка 1", "конкретная ошибка 2"]
}}
Только JSON.
"""
```

### Управление контекстом чата
- В каждый запрос передаётся история последних 20 сообщений
- Более старые сообщения обрезаются
- Системный промпт + история + новое сообщение пользователя

### Обработка ошибок API
- Timeout: 30 секунд
- Retry: 2 попытки при 5xx ошибках
- При недоступности: показывать пользователю "AI временно недоступен, попробуй позже"

---

## 16. STT/TTS заглушки

### STT (Speech-to-Text)
```python
# backend/services/stt.py
async def transcribe(audio_data: bytes) -> dict:
    return {
        "text": "",
        "status": "not_implemented",
        "message": "STT будет добавлен в следующей версии"
    }
```

На фронте: кнопка микрофона видна, но при нажатии показывает toast "Скоро будет доступно".

### TTS (Text-to-Speech)
```python
# backend/services/tts.py  
async def synthesize(text: str, language: str = "pl") -> dict:
    return {
        "audio": None,
        "status": "not_implemented",
        "message": "TTS будет добавлен в следующей версии"
    }
```

На фронте: кнопка динамика видна рядом с польскими текстами, но неактивна (серая).

Интерфейс написан так чтобы при реализации STT/TTS достаточно было заменить тело функции.

---

## 17. Фронтенд

### Структура страниц

```
/                    → редирект на /dashboard или /login
/login               → форма входа
/register            → форма регистрации
/onboarding          → онбординг (только первый раз)
/dashboard           → главная: прогресс, рекомендации, streak
/topics              → список тем
/topics/:slug        → урок по теме
/training            → выбор тренировки
/training/session    → сессия упражнений
/chat                → список сессий чата
/chat/:id            → конкретная сессия чата
/exam                → список экзаменационных заданий
/exam/:type          → задание конкретного типа
/profile             → профиль пользователя
```

### Компоненты

```
components/
  layout/
    Navbar.jsx           -- навигация
    Sidebar.jsx          -- боковое меню (десктоп)
    BottomNav.jsx        -- нижняя навигация (мобиль)
  
  auth/
    LoginForm.jsx
    RegisterForm.jsx
  
  onboarding/
    LanguageSelect.jsx
    PlacementTest.jsx
    LevelResult.jsx
  
  topics/
    TopicList.jsx
    TopicCard.jsx
    LessonView.jsx
    ExerciseBlock.jsx
  
  training/
    Flashcard.jsx        -- с анимацией flip
    FillBlank.jsx
    WordOrder.jsx        -- drag and drop
    TranslatePhrase.jsx
    MultipleChoice.jsx
    SessionResult.jsx
  
  chat/
    ChatWindow.jsx
    MessageBubble.jsx
    CorrectionNote.jsx   -- мягкое исправление ошибок
    TopicSuggestions.jsx
  
  gamification/
    XPBar.jsx
    StreakCounter.jsx
    AchievementBadge.jsx
    ProgressToB1.jsx
    ActivityHeatmap.jsx
  
  ui/
    Button.jsx
    Input.jsx
    Card.jsx
    Toast.jsx
    Modal.jsx
    Spinner.jsx
    ProgressBar.jsx
```

### Дизайн
- Цветовая схема: чисто белый фон, акцентный цвет — тёмно-синий (#1e40af) с польским флагом как вдохновение
- Шрифт: Inter
- Мобиль-первый подход (большинство пользователей будут с телефона)
- Тёмная тема — не в MVP

### Адаптивность
- Мобиль (< 768px): BottomNav, карточки на всю ширину
- Десктоп (> 768px): Sidebar, двухколоночный layout на некоторых страницах

---

## 18. Деплой

### Структура на сервере

```
/home/politrain/
  backend/              -- Python FastAPI приложение
  frontend/dist/        -- собранный React (статика)
  .env                  -- переменные окружения (не в git)

/etc/nginx/sites-available/politrain
/etc/systemd/system/politrain-backend.service
```

### Переменные окружения (.env)
```
SECRET_KEY=<случайная строка для JWT>
MISTRAL_API_KEY=<ключ>
DEEPGRAM_API_KEY=<ключ, пока не используется>
DATABASE_URL=sqlite:///./politrain.db
ENVIRONMENT=production
```

### systemd сервис (backend)
```ini
[Unit]
Description=Politrain FastAPI Backend
After=network.target

[Service]
User=politrain
WorkingDirectory=/home/politrain/backend
ExecStart=/home/politrain/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always
EnvironmentFile=/home/politrain/.env

[Install]
WantedBy=multi-user.target
```

### nginx конфиг
```nginx
server {
    listen 443 ssl;
    server_name politrain.metallcorn.online;

    ssl_certificate /etc/letsencrypt/live/politrain.metallcorn.online/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/politrain.metallcorn.online/privkey.pem;

    # Фронтенд (статика)
    location / {
        root /home/politrain/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # API
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}

server {
    listen 80;
    server_name politrain.metallcorn.online;
    return 301 https://$host$request_uri;
}
```

### Деплой новой версии
```bash
# Бэкенд
cd /home/politrain/backend
git pull
source ../venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
systemctl restart politrain-backend

# Фронтенд
cd /home/politrain/frontend
git pull
npm install
npm run build
# nginx подхватывает автоматически
```

---

## 19. Структура проекта

```
politrain/
├── backend/
│   ├── main.py                  -- FastAPI app, роуты подключаются здесь
│   ├── database.py              -- SQLAlchemy engine, session
│   ├── models.py                -- все SQLAlchemy модели
│   ├── schemas.py               -- Pydantic схемы (request/response)
│   ├── auth.py                  -- JWT логика
│   ├── prompts.py               -- все AI промпты
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── migrations/
│   └── routers/
│       ├── auth.py
│       ├── onboarding.py
│       ├── topics.py
│       ├── vocabulary.py
│       ├── training.py
│       ├── chat.py
│       ├── exam.py
│       └── profile.py
│   └── services/
│       ├── mistral.py           -- обёртка над Mistral API
│       ├── stt.py               -- заглушка
│       ├── tts.py               -- заглушка
│       ├── sm2.py               -- алгоритм интервального повторения
│       └── gamification.py     -- XP, streak, достижения
│
├── frontend/
│   ├── index.html
│   ├── vite.config.js
│   ├── tailwind.config.js
│   ├── package.json
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── api/                 -- axios инстанс + функции запросов
│       ├── store/               -- Zustand стор
│       ├── pages/               -- страницы (по роутам)
│       └── components/          -- компоненты (см. раздел 17)
│
├── .env.example
├── .gitignore
└── README.md
```

---

## Приоритеты разработки

### MVP (Phase 1)
1. Авторизация
2. Онбординг + тест уровня
3. Модуль Правила (5-6 тем A0-A1)
4. Модуль Тренировка (карточки + заполни пропуск)
5. Streak счётчик
6. Базовый профиль

### Phase 2
1. Модуль Чат
2. Все типы упражнений
3. SM-2 алгоритм
4. Полная геймификация (XP, уровни, достижения)
5. Слабые места + рекомендации

### Phase 3
1. Модуль Экзамен B1
2. Все темы A2-B1
3. STT/TTS (реальная реализация)
4. Статистика и аналитика

---

---

## 20. Дневная генерация заданий

### Принцип
Задания генерируются заранее — при первом входе пользователя в новый день. Не на лету во время сессии. Это даёт:
- Быстрый старт сессии без ожидания AI
- Контроль над соотношением типов контента
- Возможность кешировать и не жечь токены при каждом упражнении

### Таблица `daily_exercises`
```sql
id              INTEGER PRIMARY KEY
user_id         INTEGER REFERENCES users(id)
date            DATE NOT NULL
exercise_type   TEXT NOT NULL      -- flashcard | fill_blank | translate | order_words | multiple_choice
content         TEXT NOT NULL      -- JSON с данными упражнения
source          TEXT NOT NULL      -- 'new' | 'weak' | 'review'
topic_id        INTEGER REFERENCES topics(id)
content_type    TEXT               -- 'conversational' | 'idiom' | 'situational' | 'grammar'
is_completed    BOOLEAN DEFAULT FALSE
is_correct      BOOLEAN
completed_at    DATETIME
generated_at    DATETIME DEFAULT NOW
```

### Логика генерации (запускается при первом входе в день)

```python
async def generate_daily_exercises(user_id: int, date: date):
    """
    Генерирует пул заданий на день для пользователя.
    Запускается один раз в день при первом входе.
    Если пул уже есть на сегодня — пропускает.
    """
    user = get_user(user_id)
    prefs = get_user_content_preferences(user_id)
    
    # Целевое количество заданий на день
    DAILY_TARGET = 20
    
    # Соотношение источников
    new_count      = int(DAILY_TARGET * 0.40)   # 8 новых
    weak_count     = int(DAILY_TARGET * 0.35)   # 7 повторений слабых мест
    review_count   = int(DAILY_TARGET * 0.25)   # 5 повторений успешных
    
    # Соотношение типов контента (из настроек пользователя)
    content_mix = {
        'conversational': prefs.conversational_weight,  # разговорные фразы
        'idiom':          prefs.idiom_weight,           # идиомы и устойчивые выражения
        'situational':    prefs.situational_weight,     # ситуативные диалоги
        'grammar':        prefs.grammar_weight,         # грамматические конструкции
    }
    
    # 1. Слабые места из БД (не генерируем, берём существующие)
    weak_exercises = get_weak_exercises(user_id, limit=weak_count)
    
    # 2. Старые успешные на повторение (SM-2 due)
    review_exercises = get_due_vocabulary(user_id, limit=review_count)
    
    # 3. Новые задания — генерируем через Mistral
    new_exercises = await generate_new_exercises(
        user=user,
        count=new_count,
        content_mix=content_mix,
        exclude_seen=get_seen_exercise_ids(user_id)  # чтобы не повторять
    )
    
    # Сохраняем всё в daily_exercises
    save_daily_exercises(user_id, date, weak_exercises + review_exercises + new_exercises)
```

### Промпт для генерации новых заданий

```python
DAILY_GENERATION_PROMPT = """
Ты генератор упражнений для изучения польского языка.

Пользователь:
- Уровень: {level}
- Родной язык: {native_language}
- Пройденные темы: {completed_topics}
- Слабые места: {weak_topics}

Сгенерируй {count} упражнений. Строго соблюдай это соотношение типов контента:
- {conversational_pct}% — живые разговорные фразы (то что реально говорят, не учебные примеры)
- {idiom_pct}% — идиомы и устойчивые выражения с объяснением
- {situational_pct}% — ситуативные фразы (магазин, транспорт, работа, врач, кафе)
- {grammar_pct}% — грамматические конструкции в живых примерах (не "Ala ma kota")

Типы упражнений — миксуй равномерно:
- fill_blank: предложение с пропуском
- translate: фраза с {native_language} на польский
- order_words: слова в неправильном порядке
- multiple_choice: выбор из 4 вариантов
- flashcard: слово или фраза для заучивания

Важные требования:
- Каждое задание уникально, не повторяй похожие конструкции
- Примеры должны быть живыми и актуальными, не из учебника 1970-х
- Добавляй юмор и абсурд где уместно — такое лучше запоминается
- Для идиом всегда давай буквальный перевод + реальный смысл
- Сложность строго соответствует уровню {level}

Ответь ТОЛЬКО валидным JSON массивом без markdown:
[
  {{
    "type": "fill_blank",
    "content_type": "situational",
    "question": "W kawiarni: Poproszę ___ kawy. (одна чашка)",
    "correct_answer": "filiżankę",
    "options": null,
    "hint": "biernik od filiżanka",
    "explanation": "После числительных и слов количества нужен родительный падеж, но здесь прямое дополнение — бiernik",
    "translation": "В кафе: Пожалуйста, одну чашку кофе."
  }},
  ...
]
"""
```

### Защита от повторений

```python
# В таблице user_exercise_history хранится content_hash каждого задания
# При генерации передаём в промпт список хешей последних 200 заданий
# Mistral генерирует новые — система проверяет на похожесть через простое сравнение строк
# Если похожесть > 80% — задание отбрасывается и запрашивается замена

content_hash = hashlib.md5(question.encode()).hexdigest()[:8]
```

### Обработка ошибок генерации
- Если Mistral недоступен при входе — используем задания из локального пула (таблица `exercises` в БД)
- Показываем пользователю: "Сегодня работаем с сохранёнными заданиями"
- Повторная попытка генерации через 30 минут в фоне

---

## 21. Режимы тренировки

Три отдельных режима доступны из раздела "Тренировка":

### Режим 1: Дневная сессия (основной)

Микс из сгенерированного дневного пула (40% новое / 35% слабые / 25% повторение).

- Длина сессии: 10-20 заданий (пользователь выбирает в настройках: короткая/стандартная/длинная)
- Задания идут в случайном порядке внутри пула
- После каждого ответа: мгновенный фидбек + объяснение
- В конце: итоговый экран с XP, статистикой, что повторить

**Экран итогов дневной сессии:**
```
✅ Правильно: 14 из 18
⚡ XP заработано: +180
🔥 Streak: 5 дней

Новые слова сегодня: 6
Требуют повторения: 4

[Посмотреть ошибки]  [В меню]
```

### Режим 2: Работа над ошибками

Только задания из `user_exercise_history` где `is_correct = false`.

**Логика:**
- Задание считается "исправленным" когда пользователь ответил правильно 3 раза подряд
- После этого задание уходит из режима ошибок
- Если ошибок нет — показывает экран "Чисто! Нет заданий для проработки" с конфетти

**Сортировка:**
1. Сначала самые частые ошибки (по количеству неправильных ответов)
2. Потом самые свежие ошибки
3. Потом старые нераскрытые

**UI:** Красная метка на кнопке режима показывает количество заданий для проработки.

### Режим 3: Только новое

Только задания с `source = 'new'` из дневного пула + непройденные задания из базы по текущей теме.

- Без повторений старого
- Подходит для пользователей кто хочет быстро двигаться вперёд
- Предупреждение: "Без повторений слова забываются быстрее"

### Переключение режимов

На странице `/training` — три карточки с описанием каждого режима:

```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  📅 Дневная     │  │  🔴 Ошибки      │  │  ✨ Новое       │
│  сессия         │  │  работа над     │  │  только новый   │
│                 │  │  ошибками       │  │  материал       │
│  18 заданий     │  │  4 задания      │  │  8 заданий      │
│  готово         │  │  ждут           │  │  доступно       │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

---

## 22. Настройки контента

### Таблица `user_content_preferences`
```sql
id                    INTEGER PRIMARY KEY
user_id               INTEGER REFERENCES users(id) UNIQUE
conversational_weight REAL DEFAULT 0.25    -- разговорные фразы
idiom_weight          REAL DEFAULT 0.25    -- идиомы
situational_weight    REAL DEFAULT 0.25    -- ситуативные
grammar_weight        REAL DEFAULT 0.25    -- грамматика
session_length        TEXT DEFAULT 'standard'  -- short(10) | standard(15) | long(20)
daily_goal_minutes    INTEGER DEFAULT 15
updated_at            DATETIME
```

Сумма всех weight всегда = 1.0, валидируется на бэкенде.

### UI настроек контента

Находится в профиле пользователя, раздел "Настройки тренировок".

Четыре слайдера (или визуальное распределение в виде pie/bar):
```
Разговорные фразы  [████████░░] 40%
Идиомы             [█████░░░░░] 25%
Ситуативные        [████░░░░░░] 20%
Грамматика         [███░░░░░░░] 15%
                              ────
                              100%
```

При изменении одного слайдера остальные пропорционально пересчитываются чтобы сумма всегда = 100%.

Дополнительные настройки:
- **Длина сессии:** Короткая (10) / Стандартная (15) / Длинная (20)
- **Дневная цель:** слайдер 5-60 минут
- **Напоминания:** время уведомления (заглушка в MVP)

После сохранения настроек — следующая дневная генерация учитывает новые веса.

### API для настроек
```
GET  /profile/content-preferences       -- текущие настройки
PUT  /profile/content-preferences       -- обновить настройки
```

*Документ актуален на май 2026. Версия 1.0*
