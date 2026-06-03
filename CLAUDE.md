# Politrain — CLAUDE.md

AI-тренажёр польского языка. FastAPI + SQLite бэкенд, React + Vite фронтенд, Mistral AI для генерации упражнений.

> **ПРАВИЛО:** При добавлении любой новой фичи или изменении логики — сразу дописывай тест в раздел «Тестовые сценарии» и обновляй архитектурные комментарии. Не откладывай.

> **ЗАМОРОЖЕНО (не реализовывать без явного запроса):**
> - **Level-up exam** — автопредложение теста на повышение уровня (раз в неделю, условия: завершил темы + высокая точность). Требует: модель ExamSession, endpoint генерации, фронтенд-баннер. Слишком большая задача, отложена.

---

## Стек

- **Backend**: FastAPI, SQLAlchemy, SQLite (`backend/politrain.db`), Pydantic v2
- **Frontend**: React 18, Vite, Tailwind CSS, Zustand, Axios (`baseURL: '/api/v1'`)
- **AI**: Mistral API — `mistral-large-latest` для генерации упражнений (до 7 параллельных батчей: N grammar per-topic + N lexical per-topic + 3 глобальных judge/tiles/word_def, timeout=60с, fallback → small), `mistral-small-latest` только для словаря; каждый вызов логируется в `mistral_call_logs` с токенами и duration
- **PWA**: `vite-plugin-pwa` + Workbox service worker; иконки из `public/icon.svg` через `@vite-pwa/assets-generator`; HTTPS на `politrain.metallcorn.online` (Let's Encrypt); autoUpdate режим
- **Деплой**: nginx reverse proxy (`proxy_read_timeout 90s` — обязательно!), uvicorn, systemd (сервис не настроен — запускается вручную)

---

## Секреты и конфигурация

Все секреты в `/home/politrain/politrain_code/.env`. Никогда не хардкодить.
Ключевые переменные: `SECRET_KEY`, `MISTRAL_API_KEY`, `ADMIN_USERNAME`, `DATABASE_URL`.

---

## Типовые команды

### Перезапуск бэкенда (ОДНА команда — одно подтверждение)
```bash
kill $(ps aux | grep uvicorn | grep -v grep | awk '{print $2}') 2>/dev/null ; sleep 1 ; cd /home/politrain/politrain_code/backend ; env $(cat /home/politrain/politrain_code/.env | grep -v '^#' | xargs) venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 & sleep 3 ; curl -s http://localhost:8000/health
```
Всё через `;` (не `&&`) — не останавливается если kill ничего не нашёл. `cd` внутри одного вызова Bash меняет CWD для всей команды.
При ошибке смотреть: `cat /tmp/uvicorn.log`

### Сборка фронтенда
```bash
cd /home/politrain/politrain_code/frontend && npm run build
```
Dist отдаётся nginx из `frontend/dist/`.

### JWT-токен для тестирования API
```bash
cd /home/politrain/politrain_code/backend
SECRET=$(grep SECRET_KEY /home/politrain/politrain_code/.env | cut -d= -f2)
TOKEN=$(python3 -c "
import jwt, datetime
tok = jwt.encode({'sub': '2', 'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)}, '$SECRET', algorithm='HS256')
print(tok)
")
# user_id=2 = metallcorn (основной тестовый), user_id=1 = testuser
```

---

## Быстрый тест (ОДНА команда — одно подтверждение)

Запускать после рестарта. Покрывает всё основное — health, stats, сессии, словарь, жалобы.

```bash
SECRET=$(grep SECRET_KEY /home/politrain/politrain_code/.env | cut -d= -f2) ; TOKEN=$(python3 -c "import jwt,datetime; print(jwt.encode({'sub':'2','exp':datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=1)},'$SECRET',algorithm='HS256'))") ; echo "=health=" && curl -s http://localhost:8000/health && echo && echo "=stats=" && curl -s "http://localhost:8000/api/v1/training/stats" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json;d=json.load(sys.stdin);print('total:',d.get('total_exercises'),'today:',d.get('today_done'),'/',d.get('today_total'),'errors:',d.get('errors'))" && echo "=sessions=" && curl -s "http://localhost:8000/api/v1/training/session?mode=errors" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json;d=json.load(sys.stdin);exs=d.get('exercises',[]);src={};[src.update({e.get('source'):src.get(e.get('source'),0)+1}) for e in exs];print('errors:',len(exs),src)" && curl -s "http://localhost:8000/api/v1/vocabulary/stats" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json;d=json.load(sys.stdin);print('vocab:',d)" && echo "=reports=" && curl -s "http://localhost:8000/api/v1/admin/reports?resolved=false" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json;r=json.load(sys.stdin);print('open reports:',len(r));[print(' #'+str(x['id']),x.get('comment','')[:50]) for x in r]"
```

**Правило**: максимум ОДИН рестарт и ОДИН прогон теста за задачу. Все правки делать ДО рестарта.
Если тест прошёл успешно — сразу делать git коммит:
```bash
git -C /home/politrain/politrain_code add -A && git -C /home/politrain/politrain_code commit -m "описание изменений"
```
После коммита — попросить пользователя запустить `! git -C /home/politrain/politrain_code push origin main` или сделать push самостоятельно.

**Правило коммит-сообщений**: коммит описывает только изменения в **коде** (промты, логика, фронт). Изменения в **базе данных** (удалённые упражнения, деактивированные записи в пуле) — в коммит НЕ включать: БД не в гите, эта информация в истории бессмысленна.

## Тестовые сценарии после изменений

Детальные тесты — только если быстрый тест выявил проблему. Если видишь открытые жалобы — разобрать и обновить промты.

### 1. Бэкенд жив
```bash
curl -s http://localhost:8000/health
# ожидаем: {"status":"healthy"}
```

### 2. Логин
```bash
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"metallcorn","password":"MetallMeta11"}' | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print('OK' if d.get('access_token') else 'FAIL')"
```

### 3. Статистика тренировки
```bash
curl -s "http://localhost:8000/api/v1/training/stats" -H "Authorization: Bearer $TOKEN" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(d)"
# Проверяем: total_exercises, correct, errors (curriculum + AI, последние 14 дней),
#            today_done/today_total (не включает bonus и vocab)
```

### 4. Дневная сессия
```bash
curl -s "http://localhost:8000/api/v1/training/session?mode=daily" -H "Authorization: Bearer $TOKEN" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); exs=d.get('exercises',[]); src={}; [src.update({e.get('source'):src.get(e.get('source'),0)+1}) for e in exs]; print('count:', len(exs), 'daily_done:', d.get('daily_done'), 'sources:', src)"
# Проверяем: > 0 упражнений (или daily_done=True если уже пройдена сегодня)
# Возможные источники: weak/new/review/review_ai — НЕ bonus, НЕ vocab
```

### 5. Режим ошибок
```bash
curl -s "http://localhost:8000/api/v1/training/session?mode=errors" -H "Authorization: Bearer $TOKEN" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); exs=d.get('exercises',[]); print('count:', len(exs)); [print(' -', e.get('source'), e.get('type'), e.get('question','')[:50]) for e in exs[:5]]"
# Проверяем: source=error (curriculum) и/или source=error_ai (AI, только за 14 дней)
```

### 6. Только новые
```bash
curl -s "http://localhost:8000/api/v1/training/session?mode=new" -H "Authorization: Bearer $TOKEN" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print('count:', len(d.get('exercises',[])))"
# Проверяем: > 0, генерирует если дневной пул исчерпан
```

### 7. Бонусная сессия
```bash
curl -s "http://localhost:8000/api/v1/training/session?mode=bonus" -H "Authorization: Bearer $TOKEN" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print('count:', len(d.get('exercises',[])))"
```

### 8. Словарная сессия
```bash
curl -s "http://localhost:8000/api/v1/training/session?mode=vocab" -H "Authorization: Bearer $TOKEN" | \
  python3 -c "
import sys,json; d=json.load(sys.stdin)
exs=d.get('exercises',[])
print('count:', len(exs), '| all_vocab_done:', d.get('all_vocab_done'))
[print(' -', e.get('question'), '->', e.get('correct_answer','')[:30]) for e in exs[:3]]
"
# Проверяем: > 0 карточек (flashcard), поля question/correct_answer/vocab_id присутствуют
# Порядок в сессии: ошибочные → на повторение → новые
# Если all_vocab_done=True — значит пул слов исчерпан; vocab сессия должна вызвать _ensure_vocab_pool автоматически
# Проверить: если unseen слов < 10 для уровня пользователя → Mistral генерирует новые ДО сборки сессии
python3 -c "
import sqlite3
conn = sqlite3.connect('/home/politrain/politrain_code/backend/politrain.db')
c = conn.cursor()
c.execute('SELECT level FROM users WHERE id=2')
level = c.fetchone()[0]
c.execute('''SELECT COUNT(*) FROM vocabulary v WHERE NOT EXISTS
  (SELECT 1 FROM user_vocabulary uv WHERE uv.vocab_id=v.id AND uv.user_id=2)
  AND v.level IN (\"A0\",\"A1\",\"A2\")''')
print('New unseen words for level', level, ':', c.fetchone()[0])
"
# Ожидаем: > 10 новых слов; если < 10 — запрос vocab сессии пополнит пул
```

### 9. Статистика словаря
```bash
curl -s "http://localhost:8000/api/v1/vocabulary/stats" -H "Authorization: Bearer $TOKEN" | \
  python3 -m json.tool
# Проверяем: known_count, new_count, wrong_count, due_count, pending — все числа >= 0
```

### 10. Топик-упражнения (освоенные должны быть исключены)
```bash
curl -s "http://localhost:8000/api/v1/topics/accusative/lesson" -H "Authorization: Bearer $TOKEN" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print('count:', len(d.get('exercises',[])))"
# Проверяем: упражнения 12 (kawa) и 13 (brat) НЕ появляются (они освоены)
```

### 10в. topic_d — темы в дневном пуле
```bash
curl -s "http://localhost:8000/api/v1/training/session?mode=daily" -H "Authorization: Bearer $TOKEN" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); exs=d.get('exercises',[]); td=[e for e in exs if e.get('source')=='topic_d']; print('topic_d count:', len(td)); [print(' -', e.get('topic_id'), e.get('type'), e.get('question','')[:50]) for e in td[:4]]"
# Проверяем: 0-4 упражнений source=topic_d (2 темы × 2), topic_id заполнен, входят в today_done
```

### 10б. AI-тест по теме правила (mode=topic)
```bash
curl -s "http://localhost:8000/api/v1/training/session?mode=topic&topic=accusative" -H "Authorization: Bearer $TOKEN" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); exs=d.get('exercises',[]); print('count:', len(exs)); [print(' -', e.get('type'), e.get('question','')[:60]) for e in exs[:3]]"
# Проверяем: > 0 заданий типа fill_blank/multiple_choice, все про Biernik
# source="topic", не входит в today_done, ошибки попадают в errors mode
# Кнопка "Проверить знания" в TopicDetailPage → /training/session?mode=topic&topic=<slug>
```

### 11. Профиль (счётчики)
```bash
curl -s "http://localhost:8000/api/v1/profile" -H "Authorization: Bearer $TOKEN" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print('xp:', d.get('xp'), 'streak:', d.get('streak_days'), 'total_exercises:', d.get('total_exercises'), 'vocab_count:', d.get('vocab_count'))"
# total_exercises = curriculum (UserExerciseHistory) + AI completed (DailyExercise non-weak)
# vocab_count = UserVocabulary где correct_streak >= 1
```

### 12. AI-объяснение (explain endpoint)
```bash
curl -s -X POST "http://localhost:8000/api/v1/training/explain" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"exercise_type":"fill_blank","question":"Lubię ___ kawę.","correct_answer":"dobrą","user_answer":"dobry","is_correct":false,"level":1}' | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print('cached:', d.get('cached'), 'len:', len(d.get('text','')))"
# Проверяем: text непустой, cached=False при первом вызове, cached=True при повторном
```

### 13. Админ — статистика и жалобы
```bash
curl -s "http://localhost:8000/api/v1/admin/stats" -H "Authorization: Bearer $TOKEN" | \
  python3 -m json.tool
curl -s "http://localhost:8000/api/v1/admin/reports?resolved=false" -H "Authorization: Bearer $TOKEN" | \
  python3 -c "import sys,json; r=json.load(sys.stdin); print('open reports:', len(r)); [print(' #'+str(x['id']), x.get('comment','')[:60]) for x in r]"
# Если open reports > 0: разобрать каждую, обновить промты, закрыть в БД
```

### 14б. Оценка сессии
```bash
curl -s -X POST "http://localhost:8000/api/v1/training/session-rating" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"mode":"daily","rating":4,"comment":"тест","exercise_ids":[1,2,3]}' | \
  python3 -c "import sys,json; print(json.load(sys.stdin))"
# Проверяем: {"ok": true}
# В БД: SELECT id, mode, rating, comment FROM session_ratings ORDER BY id DESC LIMIT 1
```

### 15. Дашборд активности профиля
```bash
curl -s "http://localhost:8000/api/v1/profile/dashboard" -H "Authorization: Bearer $TOKEN" | \
  python3 -c "
import sys,json; d=json.load(sys.stdin)
print('today done:', d['today']['exercises_done'], '| goal:', d['today']['goal'])
print('week days:', len(d['week']), '| month days:', len(d['month']))
print('by_source:', {k: v['pct'] for k,v in d.get('by_source',{}).items()})
print('streak:', d['totals']['streak_days'], '| xp:', d['totals']['xp'])
"
# Проверяем: все поля присутствуют, числа >= 0
```

### 18. Ранги, серия, таблица лидеров
```bash
# Профиль — ранг из 25, best_streak, xp_rank_start
curl -s "http://localhost:8000/api/v1/profile" -H "Authorization: Bearer $TOKEN" | \
  python3 -c "
import sys,json; d=json.load(sys.stdin)
print('rank:', d['game_level_name'], f'({d[\"game_level\"]}/25)')
print('xp:', d['xp'], '| xp_rank_start:', d['xp_rank_start'], '| xp_to_next:', d['xp_to_next_level'])
print('streak:', d['streak_days'], '| best_streak:', d['best_streak'])
"
# Проверяем: game_level 1-25, xp_rank_start < xp, best_streak >= streak_days

# Таблица лидеров
curl -s "http://localhost:8000/api/v1/profile/leaderboard" -H "Authorization: Bearer $TOKEN" | \
  python3 -c "
import sys,json; d=json.load(sys.stdin)
print('my_rank:', d['my_rank'], '| total_users:', d['total_users'])
for e in d['entries']: print(f'  #{e[\"rank\"]} {e[\"username\"]} — {e[\"xp_today\"]} XP{\" <-- ты\" if e[\"is_current_user\"] else \"\"}')
"
# Проверяем: my_rank >= 1, entries отсортированы по xp_today desc, is_current_user у одной записи

# Dashboard — xp_today + xp в week/month
curl -s "http://localhost:8000/api/v1/profile/dashboard" -H "Authorization: Bearer $TOKEN" | \
  python3 -c "
import sys,json; d=json.load(sys.stdin)
print('xp_today:', d['today']['xp_today'])
print('best_streak:', d['totals']['best_streak'])
print('week xp sample:', [(x['day'],x.get('xp',0)) for x in d['week'][:3]])
"
# Проверяем: xp_today > 0 если занимался, week/month содержат поле xp
```

### 17. Пул упражнений (только ADMIN)
```bash
curl -s "http://localhost:8000/api/v1/admin/exercise-pool/stats" -H "Authorization: Bearer $TOKEN" | \
  python3 -c "
import sys,json; d=json.load(sys.stdin)
print('total:', d['total'], '| active:', d['active'], '| inactive:', d['inactive'])
print('by_type:', d.get('by_type'))
"
# Проверяем: total > 0 после хотя бы одной сессии, inactive = кол-во деактивированных жалобами

# Проверить что пул раздаёт упражнения (не генерирует):
python3 -c "
import sqlite3
conn = sqlite3.connect('/home/politrain/politrain_code/backend/politrain.db')
c = conn.cursor()
c.execute('SELECT COUNT(*) FROM exercise_pool')
print('pool size:', c.fetchone()[0])
c.execute('SELECT COUNT(*) FROM daily_exercises WHERE pool_exercise_id IS NOT NULL')
print('de with pool_id:', c.fetchone()[0])
"
```

### 16. Статистика расхода Mistral API (только ADMIN)
```bash
curl -s "http://localhost:8000/api/v1/admin/mistral-usage?days=7" -H "Authorization: Bearer $TOKEN" | \
  python3 -c "
import sys,json; d=json.load(sys.stdin)
t = d.get('totals',{})
print('calls:', t.get('calls'), '| tokens:', t.get('input_tokens',0)+t.get('output_tokens',0), '| cost $:', round(t.get('cost_usd',0),4))
print('purposes:', list(d.get('by_purpose',{}).keys())[:5])
print('days:', len(d.get('days',[])))
"
# Проверяем: calls > 0 если бэкенд использовался, cost_usd >= 0
```

### 14б. Тематическая генерация (topic-tagged new/bonus)
```bash
# Сбросить дневную и запросить новую сессию — проверить что новые упражнения имеют topic_title
SECRET=$(grep SECRET_KEY /home/politrain/politrain_code/.env | cut -d= -f2) ; TOKEN=$(python3 -c "import jwt,datetime; print(jwt.encode({'sub':'2','exp':datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=1)},'$SECRET',algorithm='HS256'))")
curl -s "http://localhost:8000/api/v1/training/session?mode=bonus" -H "Authorization: Bearer $TOKEN" | \
  python3 -c "
import sys, json
exs = json.load(sys.stdin).get('exercises', [])
tagged = [e for e in exs if e.get('topic_title')]
print(f'Total: {len(exs)}, with topic tag: {len(tagged)}')
for e in tagged[:5]:
    print(f'  [{e[\"type\"]}] {e[\"topic_title\"]} | {e.get(\"question\",\"\")[:50]}')
"
# Проверяем: grammar (fill_blank, multiple_choice) и lexical (flashcard, translate, order_words) имеют topic_title
# judge_sentence, letter_tiles, word_definition — глобальные батчи, темы не присваиваются (intentional)
# Проверить в БД: SELECT topic_id, COUNT(*) FROM daily_exercises WHERE source='bonus' AND date=date('now') GROUP BY topic_id
```

### 14в. Прогресс по темам после ответов
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('/home/politrain/politrain_code/backend/politrain.db')
c = conn.cursor()
c.execute('''SELECT t.slug, t.level_required, utp.status, ROUND(utp.score,2), utp.attempts
             FROM user_topic_progress utp JOIN topics t ON t.id=utp.topic_id
             WHERE utp.user_id=2 ORDER BY t.level_required, utp.score''')
for r in c.fetchall(): print(r)
"
# После ответов на new/bonus с topic_id — должны появляться/обновляться записи UserTopicProgress
```

### 14. Проверка качества генерации (LLM-ревью)
```bash
# Получить бонусные упражнения (быстро, mistral-small) и вывести читаемо:
curl -s "http://localhost:8000/api/v1/training/session?mode=bonus" -H "Authorization: Bearer $TOKEN" | \
  python3 -c "
import sys, json
exs = json.load(sys.stdin).get('exercises', [])
for i, e in enumerate(exs, 1):
    print(f'[{i}] {e[\"type\"]} | {e.get(\"question\",\"\")}')
    print(f'    answer: {e.get(\"correct_answer\",\"\")} | options: {e.get(\"options\")}')
    print(f'    hint: {e.get(\"hint\",\"\")} | translation: {e.get(\"translation\",\"\")}')
    print()
"
```
После получения — Claude проверяет как языковой ревьюер:
- **fill_blank**: ровно один `___`; ответ не присутствует в вопросе; hint не содержит ответ
- **order_words**: sorted(question.split(' / ')) == sorted(correct_answer.split()) — слова идентичны
- **judge_sentence**: ~50% должны быть false; `poszedłem/poszłam/byłem/byłam` → "true"; `ja poszedł/ja poszła` → "false"
- **multiple_choice**: correct_answer дословно совпадает с одним из options
- **translate**: фраза ≤ 10 слов; нет кальк с английского ("стоит руки и ноги" и т.п.)
- **flashcard**: нет `___` в question; question = польское слово/фраза целиком
- **word_definition**: question — описание слова по-польски (1-2 предложения); нет `___`; correct_answer — одно польское слово в словарной форме; ответ не содержится в question; hint — первая буква + категория ("K... — napój")
- **идиомы**: проверить что идиома реально существует в польском — Mistral изобретает правдоподобно звучащие несуществующие идиомы (пример: "pazur w kieszeni" = скупость — не существует)
- **fill_blank с двумя словами**: если в скобках базовая форма и ответ должен менять ОБА слова (напр. "Ta nowa"), убедиться что correct_answer полный
- **letter_tiles**: ровно один `___`; correct_answer — одно слово без пробелов; предпочтительно слова с диакритиками (ą ę ó ś ć ź ż ń ł)
- **word_definition**: нет `___` в question; correct_answer — одно слово без `/`; слово не присутствует в question

Если нашёл паттерн ошибок → обновить промт → перегенерировать бонус → перепроверить.
Не докапываться до единичных стилистических нюансов — только системные ошибки.
Единичные плохие упражнения — удалять из БД напрямую (`DELETE FROM daily_exercises WHERE id = X`).

---

## Прямые запросы к БД

```bash
python3 -c "
import sqlite3, json
conn = sqlite3.connect('/home/politrain/politrain_code/backend/politrain.db')
c = conn.cursor()

# Пользователи
c.execute('SELECT id, username, level, xp FROM users')
print('Users:', c.fetchall())

# DailyExercise по источникам
c.execute('SELECT source, is_completed, is_correct, COUNT(*) FROM daily_exercises GROUP BY source, is_completed, is_correct')
print('Daily exercises:', c.fetchall())

# История упражнений (последние 5)
c.execute('SELECT exercise_id, is_correct, created_at FROM user_exercise_history ORDER BY created_at DESC LIMIT 5')
print('Recent history:', c.fetchall())

# Словарный прогресс пользователя
c.execute('SELECT v.polish, uv.correct_streak, uv.next_review FROM user_vocabulary uv JOIN vocabulary v ON v.id=uv.vocab_id WHERE uv.user_id=2 ORDER BY uv.correct_streak DESC LIMIT 10')
print('User vocab progress:', c.fetchall())

# Словарь по уровням
c.execute('SELECT level, COUNT(*) FROM vocabulary GROUP BY level ORDER BY level')
print('Vocab by level:', c.fetchall())
"
```

---

## Архитектура бэкенда

```
backend/
  main.py          — FastAPI app, migrations при старте
  models.py        — SQLAlchemy ORM модели
  schemas.py       — Pydantic schemas (request/response)
  auth.py          — JWT, password hashing
  database.py      — SQLAlchemy session
  prompts.py       — ВСЕ промты для Mistral:
                     _EXERCISE_COMMON_RULES — общий блок правил (без format-переменных, конкатенируется в каждый промт)
                     GRAMMAR_EXERCISES_PROMPT — fill_blank + multiple_choice
                     LEXICAL_EXERCISES_PROMPT — flashcard + translate + order_words
                     JUDGE_EXERCISES_PROMPT — judge_sentence отдельно (50/50 true/false)
                     LETTER_TILES_PROMPT — letter_tiles отдельно (одно слово, дедуплицированные буквы-карточки)
                     WORD_DEFINITION_PROMPT — word_definition отдельно (загадка по-польски → пользователь пишет слово)
                     IDIOM_DRILL_PROMPT — fill_blank/letter_tiles из известных пользователю идиом
                     VOCAB_GENERATION_PROMPT, TRANSLATION_CHECK_PROMPT,
                     CHAT_SYSTEM_PROMPT и др.
  routers/
    training.py    — сессии (daily/errors/new/bonus/vocab/topic), ответы, статистика,
                     генерация пулов (_generate_exercises(topics=None) — параллельные батчи через asyncio.gather:
                     когда topics передан — N grammar батчей (fill_blank+mc per-topic) + N lexical батчей (flashcard+translate+order_words per-topic) + 3 глобальных (judge/tiles/word_def);
                     grammar и lexical упражнения тегируются topic_slug+topic_title из своего батча — тема ВСЕГДА соответствует содержимому;
                     judge_sentence/letter_tiles/word_definition генерируются глобально без темы (сложно привязать к конкретному правилу);
                     без topics — 5 глобальных батчей без тегов тем,
                     _select_topics_for_generation(user, db, n=2) — выбирает темы для генерации:
                       приоритет: (level_idx, score_asc) — нижний уровень + низкий прогресс первыми;
                       когда ≥60% A0..current_level done → подмешивает 1 тему следующего уровня;
                       7-дневная ротация: исключает темы недавно покрытые в new/bonus, fallback на recent,
                     _save_to_pool(item, level, topic_id, db) — сохраняет упражнение в ExercisePool; UNIQUE по question_norm; возвращает pool_id;
                       если запись уже есть без topic_id → обновляет topic_id и topic_title в content (ретроактивная тегировка),
                     _pool_draw(db, user_id, level, count) — берёт из пула упражнения не виденные пользователем (NOT IN subquery на pool_exercise_id),
                     _generate_daily_pool, _generate_bonus_pool — пул-приоритет: сначала _pool_draw, затем Mistral только для дефицита;
                       ВСЕ валидированные упражнения сохраняются в пул (не только deficit штук) — пул пополняется максимально;
                       в DailyExercise идут только первые deficit упражнений из сгенерированных;
                       bonus использует challenge_level = _next_level(user.level),
                       вызывают _select_topics_for_generation, передают topics в _generate_exercises, сохраняют topic_id в DailyExercise,
                     _generate_topic_exercises_for_daily — 2 слабые темы × 2 задания, source='topic_d', параллельно с основным пулом,
                     _generate_topic_pool — fill_blank+mc строго по теме с текстом статьи,
                     _ensure_vocab_pool, _seen_questions — дедупликация по истории,
                     _generate_idiom_drill_exercises — drill из UserKnownExpression,
                     POST /training/explain — AI-объяснение ответа (кешируется в AIExplanationCache); принимает translation для перевода предложения,
                     POST /training/session-complete — накопление total_training_seconds + ачивки,
                     POST /training/session-rating — оценка сессии 1-5 + комментарий + список exercise_ids)
    topics.py      — темы, уроки, упражнения по темам
    vocabulary.py  — статистика словаря (/vocabulary/stats)
    admin.py       — жалобы, пользователи, статистика (только ADMIN_USERNAME);
                     GET /admin/mistral-usage?days=30 — расход Mistral API: по дням (large/small стэк),
                       по purpose, по user_id; поля: calls, input_tokens, output_tokens, cost_usd
                       (large: $2/$6 за 1М input/output, small: $0.2/$0.6 за 1М);
                     GET /admin/exercise-pool/stats — статистика пула: total/active/inactive/by_level/by_type;
                     POST /admin/exercise-pool/{id}/toggle — переключение is_active вручную
    auth.py        — register, login, /me
    profile.py     — профиль, настройки, достижения, активность;
                     GET /profile/dashboard — дашборд активности: today (done/correct/minutes/goal),
                       week (7 дней из DailyActivity), month (30 дней), by_source (bucketed %),
                       totals (streak_days, best_streak, xp, total_time_seconds);
                     GET /profile/leaderboard — таблица лидеров: ±5 пользователей по xp_today, my_rank, total_users
    chat.py        — чат с AI собеседником
  services/
    mistral.py     — обёртка над Mistral API
    gamification.py — XP, стрики, достижения;
                       XP_RANKS — 25 рангов (Новичок I→Эксперт V, 0→128000 XP);
                       XP_CORRECT=10, XP_INCORRECT=2, XP_VOCAB=5 (SRS-карточки), vocab source="vocab" → 0 XP;
                       `get_game_level(xp)` → (rank_num, name, xp_to_next, rank_start) — 4 значения;
                       `update_streak()` обновляет streak_days и best_streak
    sm2.py         — алгоритм интервального повторения (SRS)
```

### Ключевые модели
- `User` — пользователь, level (A0-B1), xp, streak_days, `best_streak`, `total_training_seconds`
- `DailyExercise` — задания дня, source:
  - `weak` — curriculum упражнения из слабых тем
  - `new` — AI-сгенерированные новые задания; grammar (fill_blank/mc) и lexical (flashcard/translate/order_words) имеют topic_slug+topic_title в content — тема соответствует содержимому батча; judge/letter_tiles/word_def — глобальные без темы
  - `bonus` — AI-сгенерированные бонусные задания (сверх дневной нормы); аналогично grammar+lexical тегированы, judge/tiles/word_def без темы
  - `review` — словарные карточки из UserVocabulary по SRS-расписанию + 2 новых слова в день
  - `review_ai` — AI-задания на повторение по SRS (из new/bonus с истёкшим next_review)
  - `vocab` — карточки из режима "Слова" (не входят в daily_done счётчик)
  - `topic` — AI-сгенерированные задания по конкретной теме правила (не входят в daily_done, ошибки попадают в errors)
  - `topic_d` — AI-задания по слабым темам, встроенные в дневной пул (2 темы × 2 упражнения, входят в today_done, обновляют UserTopicProgress)
  - `practice` — микс пройденных AI-упражнений + curriculum слабые места (режим Повторение, без лимита в день, не входит в today_done)
  - SRS поля: `next_review DATE`, `srs_interval_days INT`, `srs_repetitions INT` — SM2 для AI-заданий
- `UserExerciseHistory` — история ответов на curriculum упражнения (exercise_id)
- `Exercise` — статические упражнения по темам (curriculum)
- `UserTopicProgress` — прогресс по темам; обновляется при ответе на topic/topic_d/new/bonus если topic_id заполнен;
  для new/bonus: min 3 ответа до статуса "done" (score≥0.6 + attempts≥3); запись создаётся автоматически если не существует
- `ExercisePool` — общий пул AI-упражнений для всех пользователей: exercise_type, level, topic_id, content (JSON), question_norm (UNIQUE), is_active, report_count, use_count
  - Источник: `_save_to_pool()` вызывается для ВСЕХ валидированных упражнений (не только тех что пошли в DailyExercise)
  - Раздача: `_pool_draw(user_id, level, count)` — берёт несмотренные пользователем упражнения (NOT IN по pool_exercise_id из daily_exercises)
  - Жалоба → `report_count += 1`; при `report_count >= 2` → `is_active=False` → никто больше не видит
  - `DailyExercise.pool_exercise_id` — FK на ExercisePool; ставится при раздаче ИЗ пула и при сохранении В пул
  - topic_d упражнения в пул НЕ сохраняются (per-user, по конкретным слабым темам)
- `GeneratedExerciseReport` — жалобы пользователей на AI-задания; `daily_exercise_id` → `pool_exercise_id` для деактивации в пуле
- `Vocabulary` — словарь польских слов (пополняется Мистралем)
- `UserVocabulary` — прогресс пользователя по словарю: ease_factor, interval_days, correct_streak, next_review
- `AIExplanationCache` — кеш AI-объяснений: cache_key=sha256(question|answer|is_correct|level|user_level|lang), level 1/2
- `UserKnownExpression` — идиомы/фразы которые пользователь знает (из flashcard quality≥4 без vocab_id), drilled_at
- `SessionRating` — оценка сессии пользователем: rating (1-5, nullable), comment, mode, exercise_ids (JSON), created_at
  - Сохраняется через `POST /training/session-rating`; rating необязателен — если не выставил, запись не создаётся
- `MistralCallLog` — лог каждого вызова Mistral API: model, purpose, user_id, input_tokens, output_tokens, success, duration_ms, created_at
  - Пишется через прямой sqlite3 (не ORM) в `services/mistral.py → _log_call()`; INSERT явно передаёт `datetime('now')` (ORM default не работает для raw sqlite)

### Логика словаря
- `correct_streak >= 1` → слово "знакомо", считается в vocab_count
- `correct_streak == 0` (есть запись в user_vocabulary) → слово ошибочное, приоритет в vocab сессии
- Ответил неверно в любом режиме → `correct_streak = 0` (слово возвращается)
- Дневная сессия автоматически добавляет 2 новых слова (source="review")
- Когда незнакомых слов < 20 → `_ensure_vocab_pool()` генерирует ещё 30 через Мистраля
- Во избежание повторов: Мистралю передаются последние 60 слов; бэкенд дополнительно дедуплицирует

### Логика ошибок (Работа над ошибками)
- Curriculum ошибки: `UserExerciseHistory` где последний attempt `is_correct=False` и `is_flagged=False`
- AI ошибки: `DailyExercise` где `is_completed=True AND is_correct=False AND source IN (bonus, new, topic, topic_d)`
  - Фильтр: `completed_at IS NOT NULL AND completed_at >= now()-14days` (старые NULL-записи игнорируются)
- Когда ошибка исправлена в режиме errors — `DailyExercise.is_correct` обновляется на True
- Пожаловался пользователь → `DailyExercise.is_correct=True` (исключается из ошибок и пулов)
- Идиомные flashcard (без vocab_id): "Не знал" → quality=3 → `is_correct=True` — НЕ попадают в ошибки, SRS возвращает карточку скоро

### SRS для AI-заданий
- Правильный ответ на `new/bonus/review_ai` → SM2 вычисляет `next_review` (1д → 6д → экспоненциально)
- Диакритическая ошибка → quality=3 (интервал короче)
- Неправильный ответ → `next_review=None`, `srs_repetitions=0` (задание уходит в errors mode)
- В дневном пуле: до 3 заданий с `next_review <= today` вытаскиваются как `source='review_ai'`
- `_seen_questions()` берёт 60 последних по `completed_at DESC` — только для Python-дедупликации, не передаётся Мистралю

### Освоенные упражнения (mastered)
- Функция `_mastered_exercise_ids()` в training.py и topics.py
- Критерий: последние 3 попытки в `UserExerciseHistory` все `is_correct=True`
- Исключаются из: дневного пула (weak_exs), упражнений по темам

---

## Фронтенд

```
frontend/src/
  api/index.js     — все API вызовы (baseURL: '/api/v1' — НЕ добавлять /api/v1 в путях)
                     profileApi.dashboard() → GET /profile/dashboard
                     adminApi.mistralUsage(days) → GET /admin/mistral-usage?days=N
  store/           — Zustand stores (auth, UI)
  pages/           — TrainingPage, TrainingSessionPage, AdminPage, ProfilePage,
                     DashboardPage, ChatPage, ...
  components/
    training/      — FillBlank, MultipleChoice, Flashcard, WordOrder, JudgeSentence, TranslatePhrase, LetterTilesBlank, WordDefinition
    ui/            — Button, Card, Input, ProgressBar, Skeleton (animate-pulse заглушки), Markdown (react-markdown wrapper)
    layout/        — Layout с min-w-0 на flex контейнере (важно для mobile); page transitions через key={location.pathname}
    gamification/  — ActivityDashboard: Ring (SVG кольцо цели), WeekChart (7 дней), MonthChart (30 дней), SourceBar (breakdown по источникам);
                       переключатель metric (exercises/XP) для Week и Month графиков; best_streak в chip серии;
                       Leaderboard — таблица лидеров по XP за сегодня, my_rank highlighted
    admin/         — MistralUsageChart: period selector 7/30/90 дней, stat cards, DayChart (stacked large/small), by-purpose bars, by-user table
```

### Аксиомы фронтенда
- Axios baseURL = `/api/v1` → пути без префикса: `api.get('/training/stats')` не `api.get('/api/v1/training/stats')`
- `is_admin` вычисляется сервером в `/auth/me`, сравнивая username с `ADMIN_USERNAME` из env
- Mobile layout: flex-контейнер должен иметь `min-w-0` иначе вылезает за экран
- Таймаут сессии: bonus/new/daily/topic = **85с**, остальные = 30с (Mistral до 60с + nginx 90с)
- При ошибке загрузки сессии — экран с кнопкой "Попробовать снова" (loadError state), не SessionResult 0/0
- IdiomCard (flashcard без vocab_id): autoAdvance=true — переход сразу после выбора "Знал/Не знал" без кнопки "Далее"
- Анимации в `index.css`: animate-shake (неверный ответ), animate-slide-in (новое задание), animate-float-up (XP float), animate-bounce-in (результат), animate-fade-in (страница/хинт), animate-scale-in
- Skeleton-экраны вместо спиннеров: `<Skeleton className="h-X w-X rounded-Y" />` — animate-pulse, используется во всех страницах загрузки
- Markdown рендерится через `react-markdown` (`Markdown.jsx`): используется в AI-объяснениях, hints, explanation во всех компонентах заданий
- Markdown в TopicDetailPage рендерится кастомным `parseTable` — таблицы ОБЯЗАТЕЛЬНО должны иметь непустую строку заголовков; таблица с `| | | |` в хедере не рендерится
- AI-объяснение: кнопка "Объяснить подробнее" → `POST /training/explain` (level=1), кнопка "Расскажи подробнее" → level=2; оба кешируются в AIExplanationCache
- Таймер сессии: `startTimeRef` запускается когда упражнения загружены (не во время ожидания Мистраля); по завершении → `POST /training/session-complete`
- Активное время в таймере: `visibilitychange` API — пауза при скрытии вкладки, возобновление при возврате; `activeTimeRef` + `lastVisibleRef`
- SessionResult кнопка "продолжить": mode-aware — vocab → "Ещё слова", topic → "Повторить тему", else → "Ещё задания"
- LetterTilesBlank перемешивание: Fisher-Yates (не `sort(() => Math.random() - 0.5)` — тот даёт неравномерный результат)
- LetterTilesBlank показывает `exercise.translation` под вопросом (серый курсив)
- SessionResult: звёздный рейтинг 1-5 + опциональный комментарий → `POST /training/session-rating`; exerciseIds передаются из TrainingSessionPage
- TrainingPage: бонус всегда виден — задизаблен (div вместо Link, opacity-50) пока не выполнена дневная; `Promise.allSettled` вместо `Promise.all` для устойчивости к частичным ошибкам API
- TopicDetailPage: skeleton вместо Spinner при загрузке; `last_result` из get_lesson предзаполняет exerciseResults; после ответа exerciseResults[ex.id] обновляется локально
- TrainingPage: режим "Повторение" (mode=practice) — только упражнения с is_correct=True (AI: new/bonus/review_ai/topic_d за 60 дней + curriculum не освоенные но последний ответ верный); ошибки (is_correct=False) остаются ТОЛЬКО в errors mode; без лимита в день; не считается в today_done
- SessionResult кнопка "продолжить" для practice: "Ещё задания" (mode=bonus)
- TrainingSessionPage: source badge показывает тему для ВСЕХ типов если `currentEx.topic_title` есть: "✨ Новое · Biernik"; все exercise types (включая judge/tiles/word_def) получают topic через round-robin в _generate_exercises
- multiple_choice options перемешиваются при каждой отдаче сессии (random.shuffle прямо перед return), чтобы пользователь не запоминал позиции
- ProfilePage: ActivityDashboard вместо ActivityHeatmap; данные из `profileApi.dashboard()` (GET /profile/dashboard); skeleton при загрузке
- AdminPage: вкладка "API" с MistralUsageChart; вкладки — ternary цепочка (`tab === 'X' ? ... : tab === 'Y' ? ...`), НЕ if/else
- Interest themes для генерации: `min(2, len(themes))` — не больше 2 тем интереса за батч (снижает пространство решений для Mistral)
- PWA: `public/icon.svg` → источник для всех иконок; пересборка иконок: `npx @vite-pwa/assets-generator --config pwa-assets.config.js`; service worker автообновляется (registerType: 'autoUpdate')

---

## Типичные ловушки

| Проблема | Причина | Решение |
|---|---|---|
| 404 на API | Добавлен `/api/v1` в путь при baseURL уже `/api/v1` | Убрать префикс |
| `NameError: func` | `from sqlalchemy import func` только внутри функции | Импорт на уровне модуля |
| Счётчик ошибок завышен | Старые DailyExercise с `completed_at=NULL` | Фильтр `IS NOT NULL` + 14 дней |
| Mobile overflow | flex item без `min-w-0` | Добавить `min-w-0` на flex child |
| Освоенные повторяются | topic exercises не фильтровали mastered | `_mastered_exercise_ids()` в topics.py |
| Импорт между роутерами | `from routers.training import X` → ModuleNotFoundError | Дублировать функцию или вынести в utils |
| Неизвестный тип упражнения | Мистраль генерирует "situational" и т.п. | `_validate_type()` отбрасывает всё кроме 8 допустимых (включая letter_tiles и word_definition) |
| Упражнения идут по порядку | Пользователь запоминает последовательность | `random.shuffle(exercises)` перед return в session endpoint |
| order_words слова в правильном порядке | Мистраль генерирует слова в том же порядке что и ответ | `_fix_order_words_exercise` перемешивает слова после валидации |
| vocab в daily счётчике | source="vocab" попадал в today_done | Фильтр `source.notin_(["bonus", "vocab"])` |
| Кальки в translate | Мистраль пишет "Это стоит руки и ноги" (с английского) | В LEXICAL_EXERCISES_PROMPT: использовать естественные русские фразы |
| poszedłem = ошибка | Мистраль генерит judge_sentence с правильной формой как false | В JUDGE_EXERCISES_PROMPT: явная таблица форм — poszedłem ВЕРНО, ja poszedł НЕВЕРНО |
| judge_sentence почти всегда true | Мистраль избегает генерировать ошибочные предложения | Отдельный JUDGE_EXERCISES_PROMPT с алгоритмом "сначала выбери тип ошибки, потом составь предложение", строгое 50/50 |
| judge_sentence с ___ | Мистраль иногда генерит fill_blank-образные judge | `_fix_judge_sentence_exercise` отбрасывает если в question есть ___ |
| mode=new таймаут/ошибка | Всегда вызывал генерацию даже если bonus уже есть | Проверять uncompleted_bonus перед `_generate_bonus_pool`, как mode=bonus |
| Повторяющиеся упражнения | Мистраль генерирует похожие вопросы каждый раз | `_seen_questions()` — Python-дедупликация последних 60 выполненных, не засорять промт |
| Мега-промт = плохое качество | Один промт на много типов — Мистраль путается | До 7 параллельных батчей: N grammar per-topic + N lexical per-topic + judge + letter_tiles + word_definition через asyncio.gather |
| daily_pool таймаут | mistral-large не укладывается в 25с для генерации упражнений | До 7 параллельных батчей по 2-3 упражнения, каждый timeout=60с, fallback на mistral-small |
| nginx обрывает соединение | proxy_read_timeout по умолчанию 60с, Mistral генерирует до 63с | proxy_read_timeout 90s в /etc/nginx/sites-available/default (требует root) |
| Таблица в статье не рендерится | Кастомный parseTable требует непустой заголовок | Всегда писать осмысленные названия колонок в первой строке таблицы |
| Бэкенд не видит изменения | Не перезапущен после правки | Всегда kill + restart |
| Фронт не видит изменения | Не пересобран | `npm run build` |
| Токен генерируется с ошибкой | `datetime.utcnow()` deprecated | Использовать `datetime.now(datetime.timezone.utc)` |
| review_ai не появляется в daily | next_review заполняется только при правильном ответе на new/bonus | Для теста: вручную `UPDATE daily_exercises SET next_review='2026-01-01' WHERE ...` |
| AI-объяснение не кешируется | cache_key не совпадает | Ключ = sha256(question\|answer\|is_correct\|level\|user_level\|lang)[:48] — все поля должны быть идентичны |
| order_words заканчивается предлогом | Мистраль генерит "Idę / do / szkoły" где ответ кончается "do" | `_fix_order_words_exercise` отбрасывает если последнее слово в `_PL_CLAUSE_ENDS`; также требует ≥ 3 слов |
| vocab сессия только из повторений | Нет баланса new/review | Ограничение: max 60% review-слов, min 30% новых слов в vocab сессии |
| judge_sentence без перевода | Пользователь не понимает предложение без контекста | `translation` — обязательное поле в JUDGE_EXERCISES_PROMPT; показывается как хинт до ответа (-1 XP) |
| Таймер сессии считает время в другой вкладке или приложении | `visibilitychange` не срабатывает при переключении приложений на десктопе (браузер остаётся открытым) | `visibilitychange` + `window.blur`/`window.focus` — оба события вызывают одну `pause()`/`resume()` функцию |
| Мистраль пишет translation по-английски | Игнорирует `{native_language}` в промте | `_sanitize_native_fields(item, native_language)` — зануляет translation/explanation/hint без кириллицы у ru-пользователей; вызывается при сохранении new/bonus/topic |
| word_definition раскрывает ответ через производное | "apteka" → вопрос содержит "aptekarz" | `_fix_word_definition_exercise`: stem check — если `c_norm[:-1]` (все кроме последней буквы) есть в вопросе → None; плюс правило Alias в промте |
| TrainingPage: бонус исчезает | `dailyDone=false` когда today_total=0 | Бонус всегда виден, disabled (div вместо Link) пока дневная не выполнена |
| TrainingPage статистика показывает нули | `Promise.all` — один упавший запрос обнуляет всё | Заменить на `Promise.allSettled` с индивидуальными проверками `status === 'fulfilled'` |
| explain не объясняет конкретную ошибку judge_sentence | AI говорит про тему вообще | В system prompt level=1: инструкция "для типа «верно/неверно» укажи КОНКРЕТНОЕ слово/форму" |
| explain без перевода предложения | Пользователь не понимает о чём задание | `ExplainRequest` принимает `translation`; system prompt инструктирует начинать с перевода (*курсив*) |
| letter_tiles translation показывает ___ | Пользователь не понимает что за слово | В LETTER_TILES_PROMPT: translation — ПОЛНОЕ предложение без пропуска, само слово вместо ___; пример обновлён |
| Topic mini-test не помнит ответы | exerciseResults — только local state, сбрасывается при навигации | `get_lesson` теперь возвращает `last_result` для каждого упражнения из UserExerciseHistory; TopicDetailPage предзаполняет exerciseResults при загрузке |
| judge_sentence некорректно помечено false | Mistral изобретает «ошибку» ради квоты 50/50 когда не может найти реальную; примеры: "Ja jestem zmęczony" (верно для муж. рода), "zapomniał swojego biletu" (верный род. падеж после zapomnieć) | JUDGE_EXERCISES_PROMPT содержит: САМОПРОВЕРКА (назвать конкретное неверное слово → иначе true), АБСОЛЮТНЫЕ ЗАПРЕТЫ (список конструкций которые ВСЕГДА верны), ФИНАЛЬНАЯ ПРОВЕРКА (объяснение обязано называть ошибку). При обнаружении — деактивировать в пуле: `UPDATE exercise_pool SET is_active=0 WHERE id=X` |
| Статистика не обновляется | total/correct считали только UserExerciseHistory (curriculum), AI упражнения не включались | В stats endpoint добавлены ai_total + ai_correct из DailyExercise (кроме vocab и practice) |
| Bonus генерирует задания текущего уровня | Бонус должен быть challenge | `_next_level(user.level)` → передаётся в `_generate_exercises(level=challenge_level)` |
| Дневная сессия короткая при сбое Mistral | session_length по умолчанию 15 | Изменено: short=10, standard=20, long=25; дефолт=20 |
| multiple_choice пользователь запоминает позицию ответа | options хранятся в фиксированном порядке | `random.shuffle(ex["options"])` при каждой отдаче сессии (перед return) |
| multiple_choice answer виден в вопросе | Мистраль генерит мета-вопрос "Что происходит с X в контексте Y kolegę?" | В GRAMMAR_EXERCISES_PROMPT: запрет мета-вопросов; вопрос должен быть польским предложением с ___ |
| vocabulary синоним не принимается | translation_ru содержит только один вариант | Обновить `vocabulary.translation_ru` через " / " разделитель; `_check_answer` уже поддерживает split по ' / ' |
| UserTopicProgress не создаётся для new/bonus | Запись создавалась только при явном открытии темы | Ответ на new/bonus с topic_id создаёт запись автоматически через db.add + db.flush |
| Тема выбирается случайно каждый раз | _select_topics_for_generation без приоритета уровня | Сортировка по (level_idx, score_asc): сначала A0, потом A1...; B1 только когда ≥60% A0-current done |
| Пул не заполняется при жалобе | daily_exercise_id не передаётся с фронтенда | Убедиться что `report` payload содержит `daily_exercise_id` (из `currentEx.id`); бэкенд ищет pool через DE.pool_exercise_id |
| Vocab сессия возвращает all_vocab_done | Пользователь выучил все слова уровня, _ensure_vocab_pool не вызывался в vocab-режиме | Vocab сессия сама проверяет: unseen < 10 → await _ensure_vocab_pool() перед сборкой |
| Пул раздаёт уже виденные упражнения | pool_exercise_id NULL для старых DE | NOT IN subquery игнорирует NULL; старые DE с NULL не блокируют раздачу — OK |
| mistral_call_logs.created_at = NULL | SQLAlchemy `default=func.now()` не работает для raw sqlite3 INSERT | Явно передавать `datetime('now')` в INSERT в `_log_call()` |
| AdminPage не рендерит новую вкладку | ternary chain `): (` нельзя расширить добавив ещё одну ветку | Исп. `tab === 'X' ? ... : tab === 'Y' ? ... : tab === 'Z' ? ...` — явные условия для каждой вкладки |
| topic_title не видно в badge бонуса | Старые упражнения в БД без topic_title | Удалить uncompleted bonus: `DELETE FROM daily_exercises WHERE source='bonus' AND is_completed=0 AND date=date('now')` |
| `get_game_level` возвращает 4 значения | Возвращает `(rank_num, name, xp_to_next, rank_start)` — 4-tuple | Распаковывать как `level, name, xp_to_next, rank_start = get_game_level(xp)` |
| Лидерборд пуст если никто не занимался | Запрос фильтрует `xp_earned > 0`, текущий пользователь всегда включается | Если xp=0 у всех — entries=[current_user], total_users=1 |
| vocab source XP | source='vocab' (know/don't know) → 0 XP; flashcard с vocab_id → XP_VOCAB=5; обычные упражнения → XP_CORRECT=10 | `_vocab_mode` устанавливается в answer handler до XP-блока |
| Тема не соответствует упражнению | Round-robin topic assignment → flashcard про garnitur помечен "Алфавит" | _batch_for_topic_lexical() — отдельный батч per-topic для flashcard/translate/order_words; judge/tiles/word_def глобальны без тем |
| topic_d без названия темы в бейдже | topic_title не добавлялся в content JSON | _gen_for_topic() добавляет item["topic_title"] перед сохранением |
| Пул не пополняется при малом дефиците | Цикл в _generate_bonus/daily_pool прерывался после deficit упражнений — остальные выбрасывались | Двухпроходный цикл: сначала сохранить ВСЕ в пул, затем взять первые deficit в DailyExercise |
| Упражнения без темы в пуле | Старые записи сгенерированы без topic_id (до _batch_for_topic_lexical и round-robin для global) | Деактивировать через is_active=0; пул заполнится заново с правильными темами |
| AI объяснение остаётся от прошлого задания | handleSkip/handleReportSubmit не сбрасывали aiTexts/aiOpen; плюс race condition если fetchAiLevel отвечал после навигации | resetAiState() в handleSkip/handleReportSubmit + nonce ref в fetchAiLevel для discard stale responses |
| Нет темы у judge/tiles/word_def | Убрали round-robin когда добавили per-topic лексические батчи | Восстановили round-robin для global батчей (judge/tiles/word_def); badge показывается для всех типов где есть topic_title |
