# Politrain — CLAUDE.md

AI-тренажёр польского языка. FastAPI + SQLite бэкенд, React + Vite фронтенд, Mistral AI для генерации упражнений.

> **ПРАВИЛО:** При добавлении любой новой фичи или изменении логики — сразу дописывай тест в раздел «Тестовые сценарии» и обновляй архитектурные комментарии. Не откладывай.

> **ЗАМОРОЖЕНО (не реализовывать без явного запроса):**
> - **Level-up exam** — автопредложение теста на повышение уровня (раз в неделю, условия: завершил темы + высокая точность). Требует: модель ExamSession, endpoint генерации, фронтенд-баннер. Слишком большая задача, отложена.

---

## Стек

- **Backend**: FastAPI, SQLAlchemy, SQLite (`backend/politrain.db`), Pydantic v2
- **Frontend**: React 18, Vite, Tailwind CSS, Zustand, Axios (`baseURL: '/api/v1'`)
- **AI**: Mistral API — `mistral-large-latest` для генерации упражнений (до 7 батчей через asyncio.gather, НО ограничены `_API_SEMAPHORE=3` одновременными вызовами во избежание rate limit; timeout=60с, fallback → small), `mistral-small-latest` только для словаря; каждый вызов логируется в `mistral_call_logs` с токенами, duration и `error_message`
- **PWA**: `vite-plugin-pwa` + Workbox service worker; иконки из `public/icon.svg` через `@vite-pwa/assets-generator`; HTTPS на `politrain.metallcorn.online` (Let's Encrypt); autoUpdate режим
- **Деплой**: nginx reverse proxy (`proxy_read_timeout 90s` — обязательно!), uvicorn под **systemd user-сервисом** `politrain` (Restart=always, переживает ребут — Linger=yes); юниты в `deploy/`, установлены в `~/.config/systemd/user/`; лог по-прежнему `/tmp/uvicorn.log`
- **Бэкапы БД**: `politrain-backup.timer` ежедневно в 03:30 → `backend/scripts/backup_db.py` (online backup API + integrity_check + gzip) → `~/backups/`, хранится 14 копий

---

## Секреты и конфигурация

Все секреты в `/home/politrain/politrain_code/.env`. Никогда не хардкодить.
Ключевые переменные: `SECRET_KEY`, `MISTRAL_API_KEY`, `ADMIN_USERNAME`, `DATABASE_URL`.

---

## Типовые команды

### Перезапуск бэкенда (ОДНА команда — одно подтверждение)
```bash
XDG_RUNTIME_DIR=/run/user/$(id -u) systemctl --user restart politrain ; sleep 3 ; curl -s http://localhost:8000/health
```
Бэкенд — systemd user-сервис `politrain` (env из `.env` через EnvironmentFile, Restart=always).
`XDG_RUNTIME_DIR` обязателен — без него `systemctl --user` из неинтерактивного шелла не работает.
При ошибке смотреть: `cat /tmp/uvicorn.log` или `XDG_RUNTIME_DIR=/run/user/$(id -u) journalctl --user -u politrain -n 50 --no-pager`
НЕ запускать uvicorn вручную — порт займётся и systemd-сервис не сможет подняться.

### Сборка фронтенда
```bash
cd /home/politrain/politrain_code/frontend && npm run build
```
Dist отдаётся nginx из `frontend/dist/`.
**ВАЖНО**: всегда явный `cd frontend` в той же команде — если CWD = backend/, build запустится из неправильной директории и dist не обновится (nginx продолжит раздавать старый файл без ошибок).

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

**Сначала pytest** (валидаторы, 109 тестов, <1с) — запускать ПЕРЕД рестартом при любой правке validators.py/generation.py/training.py:
```bash
cd /home/politrain/politrain_code/backend && venv/bin/pytest -q
```
При добавлении валидатора или фикса бага в валидаторе — СРАЗУ дописать тест в `tests/test_validators.py` (регрессии из реальных жалоб — указывать номер репорта в комментарии).

Затем — API-тест после рестарта. Покрывает всё основное — health, stats, сессии, словарь, жалобы.

```bash
SECRET=$(grep SECRET_KEY /home/politrain/politrain_code/.env | cut -d= -f2) ; TOKEN=$(python3 -c "import jwt,datetime; print(jwt.encode({'sub':'2','exp':datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=1)},'$SECRET',algorithm='HS256'))") ; echo "=health=" && curl -s http://localhost:8000/health && echo && echo "=stats=" && curl -s "http://localhost:8000/api/v1/training/stats" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json;d=json.load(sys.stdin);print('total:',d.get('total_exercises'),'today:',d.get('today_done'),'/',d.get('today_total'),'errors:',d.get('errors'))" && echo "=sessions=" && curl -s "http://localhost:8000/api/v1/training/session?mode=errors" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json;d=json.load(sys.stdin);exs=d.get('exercises',[]);src={};[src.update({e.get('source'):src.get(e.get('source'),0)+1}) for e in exs];print('errors:',len(exs),src)" && curl -s "http://localhost:8000/api/v1/vocabulary/stats" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json;d=json.load(sys.stdin);print('vocab:',d)" && echo "=reports=" && curl -s "http://localhost:8000/api/v1/admin/reports?resolved=false" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json;r=json.load(sys.stdin);print('open reports:',len(r));[print(' #'+str(x['id']),x.get('comment','')[:50]) for x in r]"
```

**Правило**: максимум ОДИН рестарт и ОДИН прогон теста за задачу. Все правки делать ДО рестарта.
Если тест прошёл успешно — сразу делать git коммит:
```bash
git -C /home/politrain/politrain_code add -A && git -C /home/politrain/politrain_code commit -m "описание изменений"
```
После коммита — сразу делать push самостоятельно: `git -C /home/politrain/politrain_code push origin main`

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
# Проверяем: > 0 карточек, поля question/correct_answer/vocab_id присутствуют
# Тип карточки зависит от correct_streak: <3 → letter_tiles (сборка из букв), ≥3 → flashcard (ввод целиком)
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

### 8б. Градуированное изучение слов (буквы → полный ввод)
```bash
# Проверить что слова с низким streak идут letter_tiles, с высоким — flashcard
SECRET=$(grep SECRET_KEY /home/politrain/politrain_code/.env | cut -d= -f2) ; TOKEN=$(python3 -c "import jwt,datetime; print(jwt.encode({'sub':'2','exp':datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=1)},'$SECRET',algorithm='HS256'))")
python3 -c "
import sys; sys.path.insert(0,'/home/politrain/politrain_code/backend')
from routers.training import _vocab_card_content
class V:
    def __init__(s,p,r): s.polish=p;s.translation_ru=r;s.translation_en=r;s.example_sentence='';s.id=1
for streak in [0,2,3]:
    print(streak, '→', _vocab_card_content(V('marchewka','морковь'),'review','ru',streak)['type'])
print('короткое kot →', _vocab_card_content(V('kot','кот'),'new','ru',0)['type'])
"
# Ожидаем: streak 0,2 → letter_tiles; streak 3 → flashcard; kot (3 буквы) → flashcard
# Ответ на letter_tiles vocab правильно → correct_streak+1; неверно → 0 (назад на буквы)
```

### 9. Статистика словаря
```bash
curl -s "http://localhost:8000/api/v1/vocabulary/stats" -H "Authorization: Bearer $TOKEN" | \
  python3 -m json.tool
# Проверяем: known_count, new_count, wrong_count, due_count, pending — все числа >= 0
```

### 9б. Сохранение слова из подсказки (learn-word)
```bash
# Первый вызов — создаёт запись
curl -s -X POST "http://localhost:8000/api/v1/vocabulary/learn-word" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"word": "marchewka", "translation": "морковь"}' | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print('ok:', d['ok'], '| is_new:', d['is_new'], '| vocab_id:', d['vocab_id'])"
# Ожидаем: ok: True, vocab_id > 0; is_new=True если слово новое для пользователя, False если уже было

# Повторный вызов — idempotent (не дублирует запись)
curl -s -X POST "http://localhost:8000/api/v1/vocabulary/learn-word" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"word": "marchewka", "translation": "морковь"}' | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print('is_new on repeat:', d['is_new'])"
# Ожидаем: is_new: False (запись уже существует, не создаётся дубль)

# Проверить в БД: слово появилось в user_vocabulary с next_review=today
python3 -c "
import sqlite3
from datetime import date
conn = sqlite3.connect('/home/politrain/politrain_code/backend/politrain.db')
c = conn.cursor()
c.execute('''SELECT v.polish, uv.next_review, uv.correct_streak
             FROM user_vocabulary uv JOIN vocabulary v ON v.id=uv.vocab_id
             WHERE uv.user_id=2 AND v.polish='marchewka' ''')
print('marchewka in user vocab:', c.fetchone())
"
# Ожидаем: ('marchewka', '<сегодня>', 0) — correct_streak=0 значит пойдёт в очередь на изучение
```

### 9в. Перевод любого слова по клику (word-translation)
```bash
curl -s -X POST "http://localhost:8000/api/v1/vocabulary/word-translation" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"word": "zamiast", "context": "Pojechałbym rowerem zamiast stać w korkach."}' | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print('tr:', d['translation'], '| lemma:', d['lemma'], '| cached:', d['cached'])"
# Ожидаем: перевод на языке юзера, lemma — словарная форма; повторный вызов → cached: True
# В mistral_call_logs: purpose='word_translate' (small) только на первый вызов
# UI: клик по ЛЮБОМУ слову в FillBlank/MC/Judge/LetterTiles/WordDefinition/Reading — тултип с переводом;
# TranslatePhrase — фетча нет (родной язык)
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
# ПРАВИЛО разбора отчётов (строго соблюдать, не нарушать даже если кажется очевидным):
# 1. Читать ПОЛНЫЙ снапшот через SQL: SELECT comment, exercise_snapshot, daily_exercise_id FROM generated_exercise_reports WHERE id=X
# 2. Никогда не интерпретировать по комментарию пользователя без просмотра самого задания
# 3. После анализа — объяснить проблему и предложить ВАРИАНТЫ (включая системные правки промта)
# 4. Дождаться явного согласия пользователя — только потом реализовывать
# 5. НЕ ДЕЛАТЬ ничего между шагами 3 и 4, даже если решение кажется очевидным
```

### 14б. Оценка сессии
```bash
curl -s -X POST "http://localhost:8000/api/v1/training/session-rating" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"mode":"daily","rating":4,"comment":"тест","exercise_ids":[1,2,3]}' | \
  python3 -c "import sys,json; print(json.load(sys.stdin))"
# Проверяем: {"ok": true, "rating_id": N}
# Повторный вызов с {"rating_id": N, "rating": 5, "comment": "upd"} — апдейтит ту же запись (не дубль)
# UI: звезда шлёт сразу (без кнопки), комментарий доотправляется с rating_id
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

# Проверка ошибок Mistral (rate limit, timeout, etc.)
python3 -c "
import sqlite3
conn = sqlite3.connect('/home/politrain/politrain_code/backend/politrain.db')
c = conn.cursor()
c.execute('SELECT COUNT(*) FROM mistral_call_logs WHERE success=0')
print('failed calls:', c.fetchone()[0])
c.execute('SELECT model, error_message, COUNT(*) FROM mistral_call_logs WHERE success=0 AND error_message IS NOT NULL GROUP BY error_message ORDER BY COUNT(*) DESC LIMIT 5')
for r in c.fetchall(): print(f'  {r[0]}: {r[1][:60]} ({r[2]}x)')
"
# Ожидаем: error_message показывает конкретные причины (HTTP 429, timeout, ConnectionError)
# Если много 429 — rate limit; если timeout — Mistral медленный; если Connection — сеть
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

### 19. Лояльная проверка order_words (свободный порядок слов)
```bash
cd /home/politrain/politrain_code/backend && env $(cat ../.env | grep -v '^#' | xargs) venv/bin/python3 -c "
import asyncio, sys; sys.path.insert(0, '.')
from routers.training import _check_word_order, _same_word_multiset
class U: id=2; level='A1'; native_language='ru'
print('multiset:', _same_word_multiset('po pracy wychodzę z domu', 'Wychodzę z domu po pracy.'))
async def main():
    for ua, expect in [('Po pracy wychodzę z domu', True), ('Wychodzę domu z po pracy', False)]:
        got = await _check_word_order(ua, 'Wychodzę z domu po pracy.', 'Я выхожу из дома после работы.', U())
        print('OK' if got == expect else 'FAIL', ua, '→', got)
asyncio.run(main())
"
# Ожидаем: multiset=True; валидная перестановка → True; оторванные предлоги → False
# Обращение/вокатив в конце ("Proszę o dokumenty Panie Kowalski") → True (#240)
# Срабатывает в submit_answer только если _same_word_multiset (те же слова) и строгая проверка не прошла
# В mistral_call_logs: purpose='order_check' (small; при вердикте false — эскалация на large, второй лог order_check)
# Проверка перевода: purpose='translation_check'
# Разбор жалоб «не засчитали»: SELECT user_answer FROM daily_exercises WHERE id=<daily_exercise_id>
```

### 20б. Чтение с пониманием (mode=reading)
```bash
SECRET=$(grep SECRET_KEY /home/politrain/politrain_code/.env | cut -d= -f2) ; TOKEN=$(python3 -c "import jwt,datetime; print(jwt.encode({'sub':'2','exp':datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=1)},'$SECRET',algorithm='HS256'))")
curl -s -m 85 "http://localhost:8000/api/v1/training/session?mode=reading" -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys,json; e=json.load(sys.stdin)['exercises'][0]
print('type:', e['type'], '| questions:', len(e['questions']), '| word_hints:', len(e.get('word_hints',{})))
for q in e['questions']: assert q['correct_answer'] in q['options'], 'ответ не в options!'
print('OK: все correct_answer ∈ options (буквы-метки срезаны)')
"
# Ответ: user_answer = JSON-список выбранных строк; xp = верных × 5; is_correct если все верно
# Если 0 exercises — Mistral вернул correct_answer буквой и валидатор не смапил (см. _strip_label/letter-map)
```

### 20. Кольцо дневной цели на экране завершения сессии
```bash
# Данные для кольца — из dashboard (бэкенд не менялся, проверяем что поля на месте):
curl -s "http://localhost:8000/api/v1/profile/dashboard" -H "Authorization: Bearer $TOKEN" | \
  python3 -c "import sys,json; t=json.load(sys.stdin)['today']; print('goal:', t['goal'], '| xp_today:', t['xp_today'])"
# Ожидаем: goal > 0, xp_today >= 0
# UI (вручную): завершить сессию → если xp_today < goal было до сессии — большое кольцо по центру,
# анимация заполнения; пересечение цели → конфетти; если цель уже была выполнена — маленькое кольцо
# внизу с бейджем «цель ×2»
```

### 21. Обязательные word_hints (letter_tiles формата A + идиомный дрилл)
```bash
cd /home/politrain/politrain_code/backend && venv/bin/python3 -c "
import sys; sys.path.insert(0, '.')
from routers.training import _require_word_hints
# формат A (___) без хинтов → отброшено
print(_require_word_hints({'type':'letter_tiles','question':'Lubię pić ___.','word_hints':None}) is None)
# формат B (spelling, без ___) без хинтов → ОК
print(_require_word_hints({'type':'letter_tiles','question':'Напиши по-польски: счастье','word_hints':None}) is not None)
# с хинтами → ОК
print(_require_word_hints({'type':'letter_tiles','question':'Lubię pić ___.','word_hints':{'lubię':'люблю'}}) is not None)
"
# Ожидаем: True / True / True
# Дрилл идиом: word_hints обязательны для fill_blank И letter_tiles, topic_title='Идиомы',
# в mistral_call_logs purpose='idiom_drill'
```

### 22. systemd-сервис и бэкапы БД
```bash
export XDG_RUNTIME_DIR=/run/user/$(id -u)
systemctl --user is-active politrain politrain-backup.timer
# Ожидаем: active / active
systemctl --user list-timers politrain-backup.timer --no-pager
# Ожидаем: NEXT = ближайшие 03:30
ls -la ~/backups/ | tail -3
# Ожидаем: свежие politrain-YYYYMMDD-HHMMSS.db.gz (хранится 14)
# Ручной бэкап + проверка восстановления:
python3 /home/politrain/politrain_code/backend/scripts/backup_db.py
# Ожидаем: "backup ok: ... KB"; скрипт сам делает PRAGMA integrity_check, при сбое exit 1
# Восстановление: gunzip -k ~/backups/politrain-XXX.db.gz; затем подменить backend/politrain.db (при остановленном сервисе)
```

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
  prompts.py       — ВСЕ промты для Mistral. ЯЗЫКОВАЯ ПОЛИТИКА (не нарушать): мета-язык промтов —
                     АНГЛИЙСКИЙ; все user-facing поля — через {native_language}, куда подставляется
                     ПОЛНОЕ имя языка через services/i18n.py lang_name() ("Russian", не "ru" — иначе
                     Mistral отвечает по-английски); примеры в JSON: польские литералы можно,
                     русские/др. литералы НЕЛЬЗЯ (Mistral их копирует любому юзеру) — значения
                     нативных полей в примерах по-английски + строка "write them in {native_language}":
                     _EXERCISE_COMMON_RULES — общий блок правил (без format-переменных, конкатенируется в каждый промт)
                     GRAMMAR_EXERCISES_PROMPT — fill_blank + multiple_choice
                     LEXICAL_EXERCISES_PROMPT — translate + order_words (БЕЗ flashcard — идиомы вынесены)
                     JUDGE_EXERCISES_PROMPT — judge_sentence отдельно (50/50 true/false)
                     LETTER_TILES_PROMPT — letter_tiles отдельно (одно слово, дедуплицированные буквы-карточки)
                     WORD_DEFINITION_PROMPT — word_definition отдельно (загадка по-польски → пользователь пишет слово)
                     IDIOM_FLASHCARD_PROMPT — flashcard-идиомы отдельным ТОПИК-FREE батчем (_batch_idiom): реальные польские идиомы из знаний Мистраля, НЕ привязаны к грамматической теме (привязка порождала выдуманный мусор); глагол обязателен; пул+дедуп как у всех; идиомы НЕ получают topic badge
                     IDIOM_DRILL_PROMPT — fill_blank/letter_tiles из УЖЕ известных пользователю идиом (UserKnownExpression);
                       translation и word_hints ОБЯЗАТЕЛЬНЫ (без них отбраковка); упражнения получают topic_title="Идиомы"
                     VOCAB_GENERATION_PROMPT, TRANSLATION_CHECK_PROMPT,
                     WORD_ORDER_CHECK_PROMPT — лояльная проверка order_words (те же слова, другой порядок): пошаговый алгоритм + примеры,
                     CHAT_SYSTEM_PROMPT и др.
  routers/
    training.py    — ТОЛЬКО роутер (~1240 строк после распила): сессии (daily/errors/new/bonus/vocab/topic/practice),
                     submit_answer (включая _check_translation и _check_word_order — async Mistral-проверки ответов),
                     статистика, жалобы, _vocab_card_content/_mastered_exercise_ids — импортируются из services.generation,
                     POST /training/explain — AI-объяснение ответа (кешируется в AIExplanationCache); принимает translation для перевода предложения,
                     POST /training/session-complete — накопление total_training_seconds + ачивки,
                     POST /training/session-rating — оценка сессии 1-5 + комментарий + список exercise_ids;
                     ВАЖНО: все имена из validators/generation РЕэкспортируются через import в training.py —
                     `from routers.training import X` продолжает работать (тестовые сниппеты не ломать)
    topics.py      — темы, уроки, упражнения по темам
    vocabulary.py  — статистика словаря (/vocabulary/stats);
                     POST /vocabulary/word-translation — словарь по клику на ЛЮБОЕ слово упражнения:
                       body {word, context}; кеш WordTranslationCache (UNIQUE word+lang, общий между юзерами),
                       miss → mistral-small (WORD_TRANSLATE_PROMPT, purpose='word_translate') → {translation, lemma, cached};
                     POST /vocabulary/learn-word — добавляет слово в словарь пользователя из подсказки:
                       body: {word: str, translation: str}; находит или создаёт Vocabulary (polish, translation_ru, level=user.level, translation_en=''),
                       создаёт UserVocabulary если не существует (next_review=today → доступно для повторения сразу);
                       возвращает {ok, vocab_id, is_new}
                       ВАЖНО: слово сохраняется в той форме как было в предложении (часто инфлектированной: bieli, przeciwieństwem);
                       translation_en='' помечает такие записи. Периодически чистить:
                       `env $(cat ../.env|grep -v '^#'|xargs) venv/bin/python3 scripts/normalize_vocab.py [--dry-run]`
                       — Mistral приводит к словарной форме (лемме), дедуплицирует против канонических (мигрирует UserVocabulary)
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
    chat.py        — чат с AI собеседником; свободные темы (CHAT_SYSTEM_PROMPT, инлайн-правки) +
                     РОЛЕВЫЕ диалоги: GET /chat/scenarios (cafe/doctor/airport/shop/hotel/directions),
                     POST /chat/session со scenario → AI держит роль (CHAT_ROLEPLAY_PROMPT, без правок по ходу),
                     открывающая реплика сидируется при создании; POST /chat/session/{id}/debrief →
                     разбор реплик пользователя в конце (DIALOGUE_DEBRIEF_PROMPT, мягкие правки markdown);
                     ChatSession.scenario (NULL=свободный чат)
  services/
    validators.py  — ЧИСТЫЕ функции валидации (без БД и API), покрыты pytest (`backend/tests/test_validators.py`, 109 тестов, `venv/bin/pytest -q`):
                     _norm/_strip/_check_answer, _validate_type, _sanitize_native_fields,
                     вся цепочка _fix_* (mc, fill_blank, letter_tiles, translate, judge, order_words,
                     word_definition, flashcard), _stem_match/_clean_word_hints/_require_word_hints,
                     _same_word_multiset; ПРАВИЛО: новые валидаторы добавлять СЮДА, не в training.py
    generation.py  — генерация Mistral + пул + выбор тем (НЕ импортирует из routers.* — circular import):
                     _generate_exercises(topics=None) — параллельные батчи через asyncio.gather:
                     когда topics передан — N grammar батчей (fill_blank+mc per-topic) + N lexical батчей (translate+order_words per-topic) + глобальные (judge/tiles/word_def/idiom);
                     grammar и lexical упражнения тегируются topic_slug+topic_title из своего батча — тема ВСЕГДА соответствует содержимому;
                     judge_sentence/letter_tiles/word_definition генерируются глобально, тема через round-robin;
                     без topics — глобальные батчи без тегов тем,
                     _select_topics_for_generation(user, db, n=2) — выбирает темы для генерации:
                       приоритет: (level_idx, score_asc) — нижний уровень + низкий прогресс первыми;
                       когда ≥60% A0..current_level done → подмешивает 1 тему следующего уровня (стретч вверх);
                       7-дневная ротация: исключает темы недавно покрытые в new/bonus, fallback на recent;
                       done-темы ВОЗВРАЩАЮТСЯ на интервальное повторение (3-й пул done_review, не в последние 7 дней) — иначе освоенная тема (напр. negation) исчезала навсегда;
                       _TOPIC_FOCUS — точечный доп.фокус для prepositions (предлог нужен/нет, контраст с рус.) и negation (nie+dopełniacz),
                     _select_interest_themes(prefs, n=2) — ротация тем интересов через курсор prefs.recent_themes,
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
                     _verify_judge_false — post-валидация judge_sentence (вариант Б): после генерации второй дешёвый вызов Mistral (JUDGE_VERIFY_PROMPT, small, temp 0) перепроверяет КАЖДОЕ false-предложение; не подтвердил реальную ошибку → выбрасываем; при сбое верификатора выбрасываем ВСЕ false-judge (не отдаём непроверенное); вызывается в конце _generate_exercises — единый chokepoint для daily/bonus,
                     _verify_word_definitions — post-валидация word_definition (WORD_DEFINITION_VERIFY_PROMPT, small): отсекает фактически ложные («кислое яблоко») и неоднозначные загадки; тот же chokepoint,
                     _seen_skeletons/_question_skeleton — шаблон-дедуп: «скелет» = первые 3 значимых слова зачина (без ___/скобок/чисел); не более 2 одинаковых конструкций («Na stole leży ___», «Nie mam czasu na ___») в генерации; `_pool_draw(seen_skeletons=...)` исключает виденные скелеты И при раздаче из пула (жалобы #213/214/220/224/225, фидбек #102/108),
                     _pool_draw(seen_norms=...) — исключает не только по pool_exercise_id, но и по question_norm против недавно виденных вопросов (иначе фраза, виденная через не-пуловое задание, всплывала как «новое» — #194/#99),
                     _generate_idiom_drill_exercises — drill из UserKnownExpression (word_hints+translation обязательны, topic_title="Идиомы"),
                     _vocab_card_content/_VOCAB_TILES_GRADUATE, _mastered_exercise_ids, _eligible_vocab_levels/_LEVEL_ORDER
    i18n.py        — lang_name(code)→"Russian"/"English" (ОБЯЗАТЕЛЕН в каждом .format() промта с
                     native_language) + ui(key, lang, **kw) — серверные user-facing строки
                     (вопрос vocab-карточки, бейдж «Идиомы», chat_topics, заголовки сценариев,
                     fallback-сообщения) с en-фолбэком; новые языки — добавлять в _LANG_NAMES/_UI
    mistral.py     — обёртка над Mistral API;
                     `_API_SEMAPHORE = asyncio.Semaphore(3)` — максимум 3 параллельных вызова (защита от rate limit при 7 батчах);
                     `_pace_request()` — глобальный интервал 1с между стартами запросов (лимит Mistral — req/sec, code 1300; семафор сам по себе не спасает от одновременного старта);
                     `_log_call()` пишет model/purpose/tokens/duration/success/**error_message** в mistral_call_logs через raw sqlite3
    gamification.py — XP, стрики, достижения;
                       XP_RANKS — 25 рангов (Новичок I→Эксперт V, 0→128000 XP);
                       XP_CORRECT=10, XP_INCORRECT=2, XP_VOCAB=5 (SRS-карточки в daily/bonus);
                       vocab-сессия (source="vocab"): XP_VOCAB_NEW=2 (новое/ошибочное), XP_VOCAB_REVIEW=1 (повторение), 0 за неверный;
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
  - `topic` — тренировка по выбранной теме (#101): СМЕШАННАЯ сессия = ошибки по теме (source badge "error") + повторение освоенного по теме (review, capped ~1/3) + новые задания (генерируются _generate_topic_pool). Нет ошибок → больше нового. Вход: TrainingPage «Тренировка по теме» → /topics → тема → кнопка; mode=topic&topic=slug; не входит в daily_done
  - `topic_d` — AI-задания по слабым темам, встроенные в дневной пул (2 темы × 2 упражнения, входят в today_done, обновляют UserTopicProgress)
  - `practice` — режим Повторение = SRS-ОЧЕРЕДЬ (решение юзера 2026-07-12): отдаёт ТОЛЬКО due-задания (next_review<=today, is_correct=True, source new/bonus/review_ai/topic_d), старейшие первыми; проходишь → SM2 двигает интервал (1д→6д→эксп.) → очередь ВИДИМО уменьшается, как список ошибок; stats.practice_due — счётчик на TrainingPage; пусто → «Всё повторено ✅». Больше НЕ случайный микс и НЕ включает curriculum
  - `reading` — чтение с пониманием: ОДИН связный текст + 3 MC-вопроса как единое целое (type="reading", content={title,text,translation,word_hints,questions:[{question,options,correct_answer,explanation}]}); генерит `_generate_reading` (READING_PROMPT); валидатор срезает буквы-метки («B.») и маппит ответ-букву на вариант; ответ: user_answer=JSON-список выбранных строк, XP = верных × (XP_CORRECT//2), is_correct только если все верно; компонент ReadingExercise рендерит текст (WordHintText) + вопросы; таймаут сессии 85с
  - SRS поля: `next_review DATE`, `srs_interval_days INT`, `srs_repetitions INT` — SM2 для AI-заданий
- `UserExerciseHistory` — история ответов на curriculum упражнения (exercise_id)
- `Exercise` — статические упражнения по темам (curriculum)
- `UserTopicProgress` — прогресс по темам; обновляется при ответе на topic/topic_d/new/bonus если topic_id заполнен;
  статус "done" при score≥0.75 И attempts ≥ порога: new/bonus=9 (incidental, много повторов), topic/topic_d=5, lesson(exercise_id)=6;
  score<0.6 → "needs_review"; запись создаётся автоматически если не существует
- `ExercisePool` — общий пул AI-упражнений для всех пользователей: exercise_type, level, topic_id, content (JSON), question_norm (UNIQUE), is_active, report_count, use_count
  - Источник: `_save_to_pool()` вызывается для ВСЕХ валидированных упражнений (не только тех что пошли в DailyExercise)
  - Раздача: `_pool_draw(user_id, level, count)` — берёт несмотренные пользователем упражнения (NOT IN по pool_exercise_id из daily_exercises)
  - Жалоба → деактивация СРАЗУ (порог 1): `is_active=False` + `report_count += 1`. Деактивируются ВСЕ записи пула с тем же `question_norm`, даже если у DE `pool_exercise_id=NULL` (раньше при NULL-связи жалоба не трогала пул и фраза возвращалась — главная причина «одно и то же снова попадает»)
  - Регенерация запиленного: `_pool_active(db, pool_id)` в циклах daily/bonus — если свежесгенерированное задание совпало с деактивированной записью пула, в DailyExercise НЕ добавляется (UNIQUE question_norm → `_save_to_pool` возвращает id деактивированной записи)
  - `DailyExercise.pool_exercise_id` — FK на ExercisePool; ставится при раздаче ИЗ пула и при сохранении В пул
  - topic_d упражнения в пул НЕ сохраняются (per-user, по конкретным слабым темам)
- `GeneratedExerciseReport` — жалобы пользователей на AI-задания; `daily_exercise_id` → `pool_exercise_id` для деактивации в пуле
- `Vocabulary` — словарь польских слов (пополняется Мистралем)
- `UserVocabulary` — прогресс пользователя по словарю: ease_factor, interval_days, correct_streak, next_review
- `AIExplanationCache` — кеш AI-объяснений: cache_key=sha256(question|answer|is_correct|level|user_level|lang), level 1/2
- `UserKnownExpression` — идиомы/фразы которые пользователь знает (из flashcard quality≥4 без vocab_id), drilled_at
- `SessionRating` — оценка сессии пользователем: rating (1-5, nullable), comment, mode, exercise_ids (JSON), created_at
  - Сохраняется через `POST /training/session-rating`; rating необязателен — если не выставил, запись не создаётся
- `MistralCallLog` — лог каждого вызова Mistral API: model, purpose, user_id, input_tokens, output_tokens, success, duration_ms, **error_message**, created_at
  - Пишется через прямой sqlite3 (не ORM) в `services/mistral.py → _log_call()`; INSERT явно передаёт `datetime('now')` (ORM default не работает для raw sqlite)
  - `error_message` содержит текст ошибки: `"HTTP 429: ..."`, `"timeout after Xms"`, `"ConnectionError: ..."` — для диагностики причин fallback

### Логика словаря
- `correct_streak >= 1` → слово "знакомо", считается в vocab_count
- `correct_streak == 0` разводится по `last_reviewed`:
  - `last_reviewed IS NOT NULL` → реально ответили неверно → бейдж "⚠️ Ошибка", попадает в errors mode (error_vocab) и stats.wrong_count
  - `last_reviewed IS NULL` → свежедобавлено (learn-word/auto-add), ни разу не отвечали → бейдж "✨ Новое слово", в errors НЕ попадает, считается в stats.new_count
  - ВАЖНО: `last_reviewed` ставится при КАЖДОМ ответе на словарную карточку (оба пути answer handler) — без него отличить два состояния нельзя (SM2 при неверном тоже сбрасывает repetitions=0)
- Ответил неверно в любом режиме → `correct_streak = 0`, `last_reviewed = now` (слово возвращается как ошибка)
- **Градуированное изучение (word bank → free typing)**: `_vocab_card_content(v, status, lang, streak)` решает форму карточки:
  - `correct_streak < 3` (`_VOCAB_TILES_GRADUATE`) → `letter_tiles` — собрать слово из перемешанных букв (буквы = подсказка-леса); question="Собери слово по-польски: {перевод}", correct_answer=польское слово
  - `correct_streak >= 3` → `flashcard` — ввод/припоминание целиком
  - короткие (<4 букв) и составные (с пробелом) → всегда flashcard (плитки тривиальны/сломаны)
  - правильно собрал → streak+1 → ближе к полному вводу; ошибся → streak=0 → назад на буквы (автоматически)
  - применяется в 3 местах: vocab-сессия, daily review (source=review), daily новые слова
  - answer handler: vocab SRS и _vocab_mode срабатывают для `ex_type in ("flashcard","letter_tiles")` с vocab_id; letter_tiles проверяется реально (`_check_answer`), не self-graded
- Дневная сессия автоматически добавляет 2 новых слова (source="review")
- Когда незнакомых слов < 40 → `_ensure_vocab_pool(threshold=40, batch=50)` генерирует ещё 50 через Мистраля (timeout=45с — батч 50 не укладывался в 20с)
- **Leveling вверх**: `_eligible_vocab_levels(user_level)` = текущий уровень + растяжка на 2 ступени, потолок B2 (A2 → A2/B1/B2). Приложение ПОДТЯГИВАЕТ вверх, не кэпит на текущем уровне (раньше `[:idx+1]` оставлял пользователя без нового). `_clamp_vocab_level` сохраняет реальный уровень слова из генерации (B1/B2), а не всегда user.level
- VOCAB_GENERATION_PROMPT требует ВАРИАТИВНОСТЬ: разные части речи (наречия, союзы, связки), коллокации, «интересные» неочевидные слова, ротация доменов; уровень {level}..B2
- Во избежание повторов: Мистралю передаются последние 60 слов; бэкенд дополнительно дедуплицирует (точный + нечёткий `_too_similar`)

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
    training/      — FillBlank, MultipleChoice, Flashcard, WordOrder, JudgeSentence, TranslatePhrase, LetterTilesBlank, WordDefinition;
                     WordHintText — универсальный компонент: КЛИКАБЕЛЬНО ЛЮБОЕ слово — pre-hint из
                       `exercise.word_hints` (пунктирное подчёркивание) или on-demand фетч
                       POST /vocabulary/word-translation (кеш на сервере + в state); проп `fetchMissing`
                       (default true) — false у TranslatePhrase (текст на родном языке, фетчить нечего);
                       кириллические слова не фетчатся (клиентский guard);
                       проп `saveToVocab` (boolean) — автоматически сохраняет кликнутое слово через POST /vocabulary/learn-word (fire-and-forget), показывает 📚 в тултипе;
                       проп `onHintUsed` — вызывается при первом клике для -1 XP отслеживания;
                       saveToVocab=true у: FillBlank, MultipleChoice, JudgeSentence, LetterTilesBlank, WordDefinition;
                       TranslatePhrase — без saveToVocab (word_hints там русские→польские, инвертировано для vocab модели);
                       WordOrder — без WordHintText (UI чипов, не текст);
                     ExerciseResult — общий блок результата (зелёная/красная карточка ✓/✗, diacritic_hint, correct_answer, translation, explanation, +XP);
                       пропы: result, hintUsed, showCorrectAnswer (false у JudgeSentence — выбор true/false уже подсвечен), variants (массив для WordOrder), translation;
                       используют ВСЕ кроме TranslatePhrase (особая 3-цветная логика нечёткой оценки) и Flashcard (самооценка карточек);
                     HintButton — общий тоггл «💡 Показать подсказку (-1 XP)»; пропы: hint, onReveal, label; используют FillBlank/MultipleChoice/LetterTilesBlank/WordDefinition
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
- Экран загрузки bonus/daily/new/topic: `GEN_STEPS` — массив из 5 шагов ("Выбираем темы..." → "Генерируем грамматику..." → ...) с progress bar; `loadStep` индекс обновляется по таймеру вместе с `loadProgress`
- При ошибке загрузки сессии — экран с кнопкой "Попробовать снова" (loadError state), не SessionResult 0/0
- IdiomCard (flashcard без vocab_id): autoAdvance=true — переход сразу после выбора "Знал/Не знал" без кнопки "Далее"
- Анимации в `index.css`: animate-shake (неверный ответ), animate-slide-in (новое задание), animate-float-up (XP float), animate-bounce-in (результат), animate-fade-in (страница/хинт), animate-scale-in
- Skeleton-экраны вместо спиннеров: `<Skeleton className="h-X w-X rounded-Y" />` — animate-pulse, используется во всех страницах загрузки
- Markdown рендерится через `react-markdown` (`Markdown.jsx`): используется в AI-объяснениях, hints, explanation во всех компонентах заданий
- Markdown в TopicDetailPage рендерится кастомным `parseTable` — таблицы ОБЯЗАТЕЛЬНО должны иметь непустую строку заголовков; таблица с `| | | |` в хедере не рендерится
- AI-объяснение: кнопка "Объяснить подробнее" → `POST /training/explain` (level=1), кнопка "Расскажи подробнее" → level=2; оба кешируются в AIExplanationCache
- Таймер сессии: `startTimeRef` запускается когда упражнения загружены (не во время ожидания Мистраля); по завершении → `POST /training/session-complete`
- Активное время в таймере: `visibilitychange` API — пауза при скрытии вкладки, возобновление при возврате; `activeTimeRef` + `lastVisibleRef`
- SessionResult кнопка "продолжить": mode-aware — vocab → "Ещё слова", topic → "Повторить тему", errors → "Ещё ошибки", else → "Ещё задания"
- LetterTilesBlank перемешивание: Fisher-Yates (не `sort(() => Math.random() - 0.5)` — тот даёт неравномерный результат)
- LetterTilesBlank показывает `exercise.translation` под вопросом (серый курсив)
- LetterTilesBlank + WordOrder: анимация сборки через framer-motion `layout`/`layoutId` (FLIP) — плитка «летит» из зоны в зону, остальные плавно перестраиваются. Каждая плитка `motion.button` с `layoutId={tile-${id}}` (общий layout = полёт) + `layout` (reflow) + spring + `whileTap`. WordOrder использует `{id, word}` объекты (слова могут повторяться → нельзя key по строке/индексу). НЕ ставить `transition-all`/`active:scale-95` на motion-кнопки — конфликт с transform framer; press через `whileTap`
- SessionResult: звёздный рейтинг 1-5 + опциональный комментарий → `POST /training/session-rating`; exerciseIds передаются из TrainingSessionPage
- SessionResult: кольцо дневной XP-цели (`DailyGoalRing`) — фетчит `profileApi.dashboard()`, `before = xp_today - xpEarned` (XP начисляется по ходу сессии, бэкенд не нужен); цель не выполнена → большое кольцо по центру (вместо галочки), анимация заполнения before→after; пересёк цель этой сессией → конфетти (framer-motion, без зависимостей); цель была выполнена ДО сессии → компактное кольцо внизу, заполняется «второй круг» (lap = floor(before/goal), бейдж «цель ×N»)
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
- PWA SW НИКОГДА не должен трогать `/api`: `workbox.navigateFallbackDenylist: [/^\/api/]` в vite.config.js — иначе застрявший SW глотает POST /auth/login → пользователь не может войти при верном пароле
- Обработка ошибок запросов: `errorMessage(err, fallback)` из `api/index.js` — различает ответ сервера (показывает `detail`) и сетевой сбой/SW (показывает «Сервер не отвечает, обнови страницу / очисти данные сайта»). Использовать в catch вместо `err.response?.data?.detail || '...'` — иначе сетевой сбой выглядит как «неверный пароль»
- Axios 401-интерсептор: редиректит на /login ТОЛЬКО для не-auth запросов (истёкший токен на фоновом вызове) и НЕ на auth-страницах; 401 на самом /auth/login = неверный пароль, обрабатывает страница (без `window.location.href` — он давал мигание/петлю)

---

## Типичные ловушки

| Проблема | Причина | Решение |
|---|---|---|
| 404 на API | Добавлен `/api/v1` в путь при baseURL уже `/api/v1` | Убрать префикс |
| `NameError: func` | `from sqlalchemy import func` только внутри функции | Импорт на уровне модуля |
| Счётчик ошибок завышен | Старые DailyExercise с `completed_at=NULL` | Фильтр `IS NOT NULL` + 14 дней |
| Mobile overflow | flex item без `min-w-0` | Добавить `min-w-0` на flex child |
| Освоенные повторяются | topic exercises не фильтровали mastered | `_mastered_exercise_ids()` в topics.py |
| Импорт между роутерами | `from routers.training import X` → ModuleNotFoundError | Выносить общий код в `services/` (validators.py, generation.py); services НЕ импортируют из routers.* |
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
| Мега-промт = плохое качество | Один промт на много типов — Мистраль путается | До 7 батчей через asyncio.gather (N grammar per-topic + N lexical per-topic + judge + letter_tiles + word_definition), но не более 3 одновременно (`_API_SEMAPHORE`) |
| daily_pool таймаут | mistral-large не укладывается в 25с для генерации упражнений | Батчи по 2-3 упражнения, каждый timeout=60с, fallback на mistral-small; параллелизм ограничен семафором=3 |
| nginx обрывает соединение | proxy_read_timeout по умолчанию 60с, Mistral генерирует до 63с | proxy_read_timeout 90s в /etc/nginx/sites-available/default (требует root) |
| Таблица в статье не рендерится | Кастомный parseTable требует непустой заголовок | Всегда писать осмысленные названия колонок в первой строке таблицы |
| Бэкенд не видит изменения | Не перезапущен после правки | `XDG_RUNTIME_DIR=/run/user/$(id -u) systemctl --user restart politrain` |
| Порт 8000 занят, сервис не стартует | uvicorn запущен вручную параллельно с systemd-сервисом | Никогда не запускать uvicorn руками; убить ручной процесс, `systemctl --user restart politrain` |
| systemctl --user: Failed to connect to bus | Нет XDG_RUNTIME_DIR в неинтерактивном шелле | Всегда префикс `XDG_RUNTIME_DIR=/run/user/$(id -u)` |
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
| word_hints не кликаются в упражнении | Тип упражнения не использует WordHintText | FillBlank, MultipleChoice, JudgeSentence, LetterTilesBlank, WordDefinition — WordHintText с saveToVocab; TranslatePhrase — WordHintText без saveToVocab; WordOrder — без WordHintText (чипы) |
| learn-word дублирует слова | Повторные клики → несколько UserVocabulary записей | Endpoint идемпотентен: проверяет существующую запись перед созданием, возвращает is_new=False |
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
| word_hints есть, но слово НЕ подчёркивается | Ключ — лемма (zupa), в тексте склонённая форма (zupę); `WordHintText` матчил точно | Stem-matching в WordHintText: общий префикс, различие только в суффиксе (≤3 симв), оба ≥4 букв — `resolveHint()` |
| multiple_choice: дубль вариантов / варианты в скобках вопроса | `_fix_mc_exercise` ловил только подстроки | Дополнен: точные дубли options → None; список вариантов в скобках вопроса (совпадает с ≥2 options) → None |
| word_hints с опечаткой/мусором (zubierasz) | Mistral путает форму ключа | `_clean_word_hints`: ключ должен матчить слово вопроса по stem (многословные — все части); translate → word_hints=None (вариант C: хинт выдал бы ответ) |
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
| vocab source XP | vocab-сессия: XP_VOCAB_NEW=2 (новое/ошибочное), XP_VOCAB_REVIEW=1 (повторение), 0 за неверный; flashcard с vocab_id (daily/bonus) → XP_VOCAB=5; обычные упражнения → XP_CORRECT=10 | `_vocab_mode="vocab_session"` устанавливается в answer handler до XP-блока |
| Тема не соответствует упражнению | Round-robin topic assignment → flashcard про garnitur помечен "Алфавит" | _batch_for_topic_lexical() — отдельный батч per-topic для flashcard/translate/order_words; judge/tiles/word_def глобальны без тем |
| topic_d без названия темы в бейдже | topic_title не добавлялся в content JSON | _gen_for_topic() добавляет item["topic_title"] перед сохранением |
| Пул не пополняется при малом дефиците | Цикл в _generate_bonus/daily_pool прерывался после deficit упражнений — остальные выбрасывались | Двухпроходный цикл: сначала сохранить ВСЕ в пул, затем взять первые deficit в DailyExercise |
| Упражнения без темы в пуле | Старые записи сгенерированы без topic_id (до _batch_for_topic_lexical и round-robin для global) | Деактивировать через is_active=0; пул заполнится заново с правильными темами |
| AI объяснение остаётся от прошлого задания | handleSkip/handleReportSubmit не сбрасывали aiTexts/aiOpen; плюс race condition если fetchAiLevel отвечал после навигации | resetAiState() в handleSkip/handleReportSubmit + nonce ref в fetchAiLevel для discard stale responses |
| Нет темы у judge/tiles/word_def | Убрали round-robin когда добавили per-topic лексические батчи | Восстановили round-robin для global батчей (judge/tiles/word_def); badge показывается для всех типов где есть topic_title |
| Mistral rate limit при 7 параллельных батчах | Все вызовы large-latest падают одновременно (200-400ms, tokens=0) → fallback small генерирует хуже | `_API_SEMAPHORE=asyncio.Semaphore(3)` в mistral.py — максимум 3 одновременных вызова |
| Причина fallback неизвестна | mistral_call_logs.success=0 без деталей | `error_message` колонка: `"HTTP 429: ..."`, `"timeout after Xms"` — смотреть через admin/mistral-usage |
| flashcard с одиночным словом/буквой | Mistral генерит flashcard для "ą", "żółty" вместо идиом | `_fix_flashcard_exercise`: len(question.split()) < 2 → None |
| Идиомы — выдуманный мусор / не идиомы | Корень: у flashcard НЕ было своего промта, генерились внутри lexical-батча привязанными к грамм. теме → Mistral придумывал «идиому про цвета» | IDIOM_FLASHCARD_PROMPT + `_batch_idiom` — отдельный ТОПИК-FREE батч; flashcard убран из LEXICAL_EXERCISES_PROMPT и _batch_for_topic_lexical |
| Генерация: правил/тем слишком много | Если в промт закинуть весь пул правил+тем — Mistral путается, перекосы | `_select_topics_for_generation(n=2)` (7-дневная ротация) + `_select_interest_themes(prefs, n=2)` — максимум 2 правила + 2 темы за генерацию |
| Темы интересов выпадают неравномерно | `random.sample` без памяти → одна тема часто, другая редко | `_select_interest_themes`: курсор `prefs.recent_themes` (JSON) — fresh-first, окно `len-n` форсит цикл по всем темам; мутирует prefs, сохраняется финальным db.commit() генерации |
| judge_sentence false без explanation | Пользователь не понимает почему неверно | `_fix_judge_sentence_exercise`: correct_answer=="false" AND not explanation → None |
| explanation — dict вместо строки | Старые упражнения с `{"literal":..., "real":...}` → Pydantic 500 при ответе | `_sanitize_native_fields` нулит нестроковые поля; answer handler: `isinstance(raw_expl, str)` guard |
| completed_at=NULL у старых ошибок | Колонка добавлена позже → ошибки невидимы в errors mode (фильтр IS NOT NULL) | Бэкфилл: `UPDATE daily_exercises SET completed_at=datetime(date\|\|' 12:00:00') WHERE is_completed=1 AND completed_at IS NULL` |
| Flashcard VocabCard не принимает ответ с дефисом | normalize() не убирает дефисы → "интернет-магазин" ≠ "интернет магазин" | В Flashcard.jsx normalize добавлен `.replace(/-/g, ' ')` |
| Валидатор не срабатывает хотя написан | Две функции с одинаковым именем — вторая (def ниже) перекрывает первую в Python; строгий `_fix_flashcard_exercise` был мёртв | ОДНО определение на функцию; pytest `test_no_duplicate_toplevel_defs` ловит автоматически по всем модулям |
| Сравнение с множеством слов не срабатывает | `_strip()` убирает диакритики, а в множестве слова С диакритиками — "muszę" никогда не матчился с `_MODAL_VERBS_PL` (мёртвый код, нашёл pytest) | Нормализовать множество той же функцией: `_MODAL_VERBS_NORM = {_strip(m) for m in _MODAL_VERBS_PL}` |
| flashcard не идиома (zielone drzewo, czerwony) | Слабый валидатор перекрывал строгий (дубль) | Слитый `_fix_flashcard_exercise`: <2 слов или ≤3 слов без глагола (`_PL_VERB_ENDINGS`) → None |
| learn-word слово показывается как "⚠️ Ошибка" / в работе над ошибками | `correct_streak=0` одинаков и у «ответили неверно», и у «только что добавили»; SM2 при неверном сбрасывает repetitions=0 → не различить по repetitions | `last_reviewed` ставится при каждом ответе; errors/vocab/stats разводят: NULL→new, NOT NULL→error |
| Блок результата задания отличается между типами | Копипаст result-блока в 8 компонентах | Общий `ExerciseResult` (+`HintButton`); TranslatePhrase/Flashcard свои (обоснованно) |
| «Неверный логин/пароль» при верном пароле | Застрявший старый service worker глотает POST /auth/login → запрос не доходит до сервера → `err.response` пуст → показывалась запасная фраза «неверный пароль» | На сервере проверить: вход через `curl https://.../api/v1/auth/login` отдаёт токен, в логах бэкенда НЕТ попыток с устройства юзера → это клиентский SW. Фикс кода: `navigateFallbackDenylist: [/^\/api/]` + `errorMessage()` различает сетевой сбой. Юзеру: инкогнито (нет SW) или DevTools→Application→Service Workers→Unregister (чистка кэша SW НЕ убивает) |
| judge_sentence помечен false, но предложение верное / объяснение бессвязно | Mistral выдумывает несуществующую ошибку ради квоты false (даже с ужесточённым промтом) | Post-валидация `_verify_judge_false` (вариант Б): второй строгий вызов Mistral подтверждает реальность ошибки, иначе выбрасывает. Старый пул судится не задним числом → деактивировать: `UPDATE exercise_pool SET is_active=0 WHERE exercise_type='judge_sentence'` |
| Пул раздаёт старый брак после фикса промтов/валидаторов | Правки влияют только на НОВУЮ генерацию; пул хранит до-фиксенные записи и раздаёт их | Чистить пул при системном фиксе: деактивировать по типу/теме/дате (`is_active=0`). Жалобы часто из пула — смотреть `daily_exercises.pool_exercise_id` |
| Запиленное задание снова и снова попадает пользователю | (1) порог деактивации был 2 жалобы; (2) при `pool_exercise_id=NULL` жалоба не находила запись пула; (3) регенерация заново добавляла ту же фразу в обход is_active | (1) деактивация с ПЕРВОЙ жалобы; (2) деактивировать по `question_norm` (находит запись даже без FK-связи); (3) `_pool_active()` фильтрует регенерированные копии в циклах daily/bonus |
| «Мало нового / нет интересных слов» | `_eligible_vocab_levels` кэпил на текущем уровне (`[:idx+1]`) → A2-юзер не видел B1/B2; словарь генерился весь как user.level; темы done исчезали навсегда | Leveling текущий→B2 (+2 ступени, потолок B2); `_clamp_vocab_level` хранит реальный уровень; done-темы возвращаются на повторение; VOCAB_GENERATION_PROMPT — вариативность по частям речи |
| «Не новое / уже было» (близнецы) | Точный дедуп не ловит «для мамы» vs «для моей мамы»; Мистраль не помнит что генерил, а раздувать промт нельзя (теряется) | `_too_similar` (Jaccard по словам ≥0.7) в циклах daily/bonus — режет near-дубли против недавних И внутри батча. Промт НЕ растёт |
| errors-счётчик > заданий в сессии (#100) | stats считал vocab_errors без `last_reviewed IS NOT NULL` → свежедобавленные слова шли в ошибки, а сессия их исключает | Добавить `last_reviewed.isnot(None)` в stats vocab_errors (как в сессии) |
| vocab-карточка с инфлектированным/неверным словом (szpilkach→ботинках) | learn-word сохраняет слово как в предложении | `scripts/normalize_vocab.py` лемматизирует через Mistral (szpilkach→szpilka «шпилька») + дедуп |
| Виденная фраза всплывает как «новое» | `_pool_draw` исключал только по pool_exercise_id; фраза, виденная через не-пуловое задание, не отсекалась | `_pool_draw(seen_norms=_seen_questions(...))` — доп. фильтр по question_norm |
| word_definition: фактически ложная загадка (красный лимон) | Mistral пишет признаки, не соответствующие ответу | WORD_DEFINITION_PROMPT: каждый признак (цвет/вкус/размер) обязан быть ПРАВДОЙ и однозначно указывать на слово |
| multiple_choice без определимого ответа (любой месяц подходит) | Лексический выбор (месяцы/города) без контекста в предложении | GRAMMAR_EXERCISES_PROMPT: ответ обязан однозначно следовать из польского предложения, не из перевода; лексический выбор требует контекста в предложении |
| word_definition ответ с `_` или из двух слов (mycie_się) | Возвратные/составные просочились | `_fix_word_definition_exercise`: reject если в correct_answer есть `_` или пробел |
| fill_blank: двухсловный ответ, одно слово показано в скобках (bardziej interesujący) | Пропуск реально на 2 слова, одно выдано в `(...)` | `_fix_fill_blank_exercise`: reject если ответ ≥2 слов и слово ответа (≥4 букв, stem) уже есть в вопросе |
| fill_blank-мета: ответ = вопросительное слово (czego/co), нет реального пропуска, кириллица в ответе | Mistral строит «nie ma ___ chleba»→«czego»; «Ona ma___ samochód» (склеено); «litera Ł ... jak ___»→«в» | `_fix_fill_blank_exercise`: reject если ответ ∈ `_PL_INTERROGATIVES`, если в ответе кириллица, если `\S___` без скобок |
| Постоянно одна конструкция («на столе лежит», «nie mam czasu») | Mistral любит дефолтные шаблоны; точный/нечёткий дедуп не ловит разные слова в одном зачине | `_question_skeleton` (первые 3 слова зачина) + `_seen_skeletons`: не более 2 на скелет в генерации; чистка пула: деактивировать дубли-шаблоны (>1 на скелет). Анти-клише строка в `_EXERCISE_COMMON_RULES` |
| Повтор конструкции ИЗ ПУЛА несмотря на skeleton-дедуп в генерации | `_pool_draw` раздавал по question_norm — варианты одного скелета («prezent dla mamy/brata») формально разные → всплывали как новые (#224/#225) | `_pool_draw(seen_skeletons=...)` — исключает записи, чей скелет пользователь уже видел, + дедуп скелетов в пределах выборки |
| Одно и то же слово-загадка (drogeria опять) | Для word_definition/flashcard важен ОТВЕТ, а не скелет вопроса; разные описания одного слова проходили дедуп; плюс хардкод примера в промте | `_seen_answers`/`_ANSWER_DEDUP_TYPES` — дедуп по correct_answer в генерации и `_pool_draw`; убраны конкретные примеры (drogeria/piętro) из WORD_DEFINITION_PROMPT (Mistral их повторял) |
| mc: ответ уже стоит словом в вопросе (двойное się) | «Czy ___ się boisz» + ответ «się» → się дважды | `_fix_mc_exercise`: reject если `_strip(correct_answer)` совпадает с любым словом вопроса (#229) |
| order_words: точка отдельным чипом | Mistral сплитит «.» в отдельный токен через " / " | `_fix_order_words_exercise`: отбрасывать токены без `\w` (#232) |
| «pracować jako lekarzem» помечено верным | Mistral путает być+narzędnik и pracować jako+mianownik | `_TOPIC_FOCUS["instrumental"]`: после jako — mianownik (#226) |
| Ошибку в ответе трудно найти (#95) | Блок результата показывал весь правильный ответ одинаковым жирным | `ExerciseResult` проп `userAnswer` → `HighlightedAnswer` подсвечивает красным расходящийся хвост слова (окончание); FillBlank/WordDefinition передают value |
| order_words: нет перевода слов (#110) | WordOrder рендерит чипы без WordHintText | Тогл «Показать переводы слов» в WordOrder — подписывает перевод под доступными чипами (word_hints + stem-match, уже есть в данных) |
| word_definition фактически ложная/неоднозначная (кислое яблоко) — рецидив после правок промта | Mistral игнорирует правило точности в промте | `_verify_word_definitions` — post-валидация (как judge): второй вызов подтверждает что признаки верны и однозначны, иначе выбрасывает |
| 429 при генерации даже с семафором=3 | Семафор пускает 3 вызова ОДНОВРЕМЕННО, а лимит Mistral — запросы/сек (code 1300) → мгновенный 429 → fallback small → хуже качество | `_pace_request()` в mistral.py — глобальный интервал 1с между СТАРТАМИ запросов (in-flight перекрываются) |
| translate: верный ответ помечен ошибкой | `_check_translation` ловил 429 во время генерации → `except → return False` | Цепочка: large → small → деградация (мультимножество слов); purpose="translation_check" в логах |
| order_words: валидный другой порядок не принят | Строгое сравнение строк, а порядок слов в польском свободный | `_check_word_order` (mistral-small, WORD_ORDER_CHECK_PROMPT) — вызывается если слова совпадают (`_same_word_multiset`), но порядок другой; промт с пошаговым алгоритмом (предлог+сущ, nie+глагол) и примерами |
| Польское предложение без переводов слов (кликом) | IDIOM_DRILL_PROMPT явно ставил word_hints/translation=null; дрилл-путь шёл мимо _clean_word_hints; letter_tiles формата A иногда без хинтов | `_require_word_hints` — отбраковка letter_tiles с ___ без word_hints (формат B «Напиши по-польски» легитимно без них); дрилл: word_hints обязательны для ОБОИХ типов + полная цепочка валидации + topic_title="Идиомы" |
| fill_blank с числительным неотвечаем («zjadłem ___ jajek»→dwa) или режет составное число («dwudziestego ___ maja (5)») | Без цифры-подсказки подходит любое число; пропуск внутри составного числительного нечитаем (#236/#239) | `_is_numeral_word` (стемы без диакритик; piątek/czwartek — исключения) в `_fix_fill_blank_exercise`: числительное-ответ без `\d` в вопросе → reject; слово перед ___ тоже числительное → reject. Правило «цифра в скобках» — в `_EXERCISE_COMMON_RULES` |
| Загадка вернулась 10-й раз (cytryna, #237) | `_seen_answers(limit=120)` — за 5 активных дней ответ выпадал из окна, а юзер помнит загадку неделями | Окно 1500 (дефолт `_seen_answers`) |
| Шаблон-близнец проскочил skeleton-дедуп («Это подарок…» vs «Этот подарок…», #238) | Скелет сравнивал точные слова — одна буква различия = другой скелет | `_question_skeleton` стеммит каждое слово до 3 символов; окно `_seen_skeletons` в `_pool_draw` = 300 |
| Загадки не закрепляют изученное (фидбэк #68) | word_definition выбирал произвольные слова, не связанные со словарём юзера | `_worddef_candidates_block(user_id, db)` — 6 слов из UserVocabulary (streak≥1, минус недавние ответы) → `{candidate_words}` в WORD_DEFINITION_PROMPT («половину загадок — про эти слова»); db прокинут в `_generate_exercises(db=db)` |
| Хардкод русского в промтах/проверках — сломано для не-ru юзеров | Промты писались по-русски, валидаторы проверяли «есть кириллица?», UI-строки бэкенда захардкожены | Мета-язык промтов — английский; `lang_name()` в каждом format; `_NATIVE_SCRIPT_RES` (ru/uk/be) вместо кириллица-only; ответ = только польский алфавит (`_has_non_polish_letters` ловит любой чужой скрипт); серверные строки через `ui()` |
| word_hints по-английски у ru-юзера (идиомный дрилл) | `_sanitize_native_fields` чистил translation/hint/explanation, но НЕ word_hints; английские примеры промта копируются | Санитайзер дропает wrong-script значения word_hints; всё выпало → word_hints=None → `_require_word_hints` бракует задание |
| Однокоренное слово ответа в вопросе («na ___ rowerem» → rowerze) | Проверка утечки — только точное совпадение; инфлектированная форма проходила | `_stem_leak(question, c_norm)` в fill_blank (одно-словный ответ) и letter_tiles; скобочная базовая форма «(herbata)» исключена — это легитимный формат |
| «(mówi kobieta)» внутри correct_answer у translate | Маркер пола попадал в эталон → exact-match никогда не сходился | `_fix_translate_exercise` вырезает `\(mówi …\)` из correct_answer |
| Одна фраза дважды в одной сессии (pool + свежая генерация) | `seen_qs` = только completed; свежесгенерированный близнец только что выданного из пула проходил дедуп | Оба цикла (daily/bonus) сидируют seen_qs/skeletons/answers элементами `pool_drawn` ДО валидации генерации |
| Пул хранит нативные поля на языке генератора | translation/word_hints в content записаны на языке юзера-генератора (сейчас ru); не-ru юзер вытянет русские подсказки | ИЗВЕСТНОЕ ОГРАНИЧЕНИЕ: перед запуском для не-ru юзеров добавить колонку native_lang в exercise_pool и фильтр в `_pool_draw`. UI-данные (ранги, day_names, exam-тексты, achievements, фронтенд) — тоже отложены до фазы i18n UI |
| order_words: валидный вариант с обращением отклонён («Proszę o dokumenty Panie Kowalski», #240) | small-модель браковала перенос вокатива в конец; отказ уходил юзеру без перепроверки | WORD_ORDER_CHECK_PROMPT: шаг 4 — обращение/вокатив может стоять в начале ИЛИ в конце, запятые игнорировать + пример; `_check_word_order`: вердикт false от small эскалируется на large (доп. вызов только на редком reject-пути) |
| «Не засчитали, а что я ввёл — неизвестно» | DailyExercise не хранил ответ юзера — жалобы «всё правильно но не засчитали» неразбираемы | Колонка `daily_exercises.user_answer` (миграция в main.py), пишется в submit_answer; при разборе таких жалоб СНАЧАЛА смотреть `SELECT user_answer FROM daily_exercises WHERE id=<daily_exercise_id>` |
| AI-объяснения неточные (фидбэк 2026-07-06) | explain endpoint работал на mistral-small; плюс повторял ошибочное explanation самого задания | explain: large-first → fallback small (объяснения кешируются — качество важнее цены); инструкция «машинное explanation задания может врать — проверь и исправь»; при таком фиксе чистить кеш: `DELETE FROM ai_explanation_cache` |
| Не все слова предложения переводятся кликом (фидбэк 2026-07-06) | word_hints покрывают часть слов; юзер хочет переводить ЛЮБОЕ | POST /vocabulary/word-translation + WordTranslationCache (общий кеш word+lang) + WordHintText фетчит недостающее; TranslatePhrase — fetchMissing=false |
| letter_tiles формат B с падежной формой («Напиши по-польски: морковь» → marchewką, #241) | Тема сессии (Narzędnik) протекала в бесконтекстный spelling-формат | Промт: формат B — СТРОГО словарная форма; валидатор: нет ___ и ответ кончается на -ą (леммы так не кончаются) → reject |
| letter_tiles с перечислением букв в вопросе «(ułóż z liter: a, d, y…)» (#242) | Mistral дублирует плиточный UI текстом — заодно сливает ответ; вокруг этого же задания — галлюцинация значения (narodowa ≠ занавеска) | Валидатор: `z liter` или ≥3 букв через запятую в скобках → reject; промт — явный запрет |
| order_words: чип «(3)» среди слов (#243) | Правило цифровой подсказки для числительных (fill_blank) протекло в order_words — multiset-проверка вырезала скобки и совпала, а в чипы «(3)» попадал | Чип обязан содержать БУКВУ (`[^\W\d_]`, не `\w` — тот пропускал цифры); правило про цифру в скобках ограничено fill_blank/letter_tiles явной оговоркой в `_EXERCISE_COMMON_RULES`. ВЫВОД: новое правило в общий блок → проверить как оно ЧИТАЕТСЯ каждым типом заданий |
| ОДНИ И ТЕ ЖЕ pool-записи выданы дважды за день (фидбэки #112/#122/#124-127: pool 780-784 с разницей 30с) | Два конкурентных запроса генерации (ретрай фронта после медленного Мистраля / дабл-тап): второй стартовал до коммита первого → `_pool_draw` не видел выданное | Пер-юзерный `asyncio.Lock` в обёртках `_generate_daily_pool/_generate_bonus_pool/_generate_reading`: второй запрос ждёт, внутри лока `db.commit()` (сброс снапшота) + re-check «набор уже есть» → return. При разборе жалоб «повтор» СНАЧАЛА смотреть generated_at дубликатов |
| letter_tiles: слово выбирал Мистраль → рассинхрон предложения/ответа/перевода (#114, #121, #131) | Мистраль вырезал слово сам: перевод без слова, буквы в тексте, утечки | `_tilesify` (validators.py): формат A промта = ПОЛНОЕ предложение + перевод + word_hints, correct_answer=null; Python сам выбирает слово (5+ букв, приоритет диакритикам, не первое), режет его в ___, убирает его хинт. Вызывается ДО `_fix_letter_tiles_exercise` во всех циклах |
| fill_blank с русским кью в скобках «(интереснее)» (#133) | Перевод-подсказка неоднозначен: bardziej interesujący И ciekawszy оба «интереснее» | `_fix_fill_blank_exercise`: кириллица внутри скобок вопроса (кроме «mówi …») → reject; кью должен быть польской леммой |
| Одно и то же слово-ответ в letter_tiles («опять pracy», #134) | `_ANSWER_DEDUP_TYPES` не включал letter_tiles | Добавлен letter_tiles — дедуп по ответному слову в генерации и `_pool_draw` |
| Оценки сессий терялись (#117) | Юзеры не замечали кнопку «Отправить» | Звезда шлёт POST сразу; бэкенд возвращает `rating_id`, комментарий/смена звезды апдейтит ту же запись (`SessionRatingRequest.rating_id`) |
| Старые односложные flashcard возвращаются по SRS («biegać — это не фраза», #118) | Записи созданы до валидатора «≥2 слов» и крутятся в review_ai | Разовая чистка: `next_review=NULL` для flashcard без vocab_id с односложным question |
| «Кликнутые слова не попадают в словарь» (#134) | НЕ баг: learn-word пишет (проверено в БД), но vocab_count в профиле = correct_streak≥1 — свежий клик виден в new_count, в «выучено» после первого верного повторения | Разбор таких жалоб: `SELECT ... FROM user_vocabulary WHERE correct_streak=0 AND last_reviewed IS NULL ORDER BY id DESC` |
| SRS-очередь review_ai затоплена: 724 просроченных, повторы «каждый раз» одни и те же (#138) | SM2 планировал повтор на КАЖДЫЙ верный ответ (~30/день), а выдача — 3/день; очередь росла бесконечно, до свежих руки не доходили | СНАЧАЛА был signal-only фикс; ЗАТЕМ (2026-07-12, решение юзера) вернулись к полному планированию, но очередь разгребает mode=practice целыми сессиями (не 3/день) — пропускная способность сходится |
| «Повторения — одни и те же, счётчики не падают» (#141-144) | Блок «Fallback to DB» в бонусе добивал каждый ресюм хвоста curriculum-таблицей (50 строк на уровень): фильтр виденного = 200 строк истории БЕЗ order_by (старейшие), ветка allow-repeats крутила одни и те же первые задания («буква ц» отвечена 20 раз); source='db' неизвестен фронту → ложный бейдж «Повторение»; ответы шли в UserExerciseHistory мимо DE | Фолбэк УДАЛЁН (реальный дефицит добивается пулом в генераторе; короткая сессия лучше вечных рерунов); фронт: неизвестный source → «📝 Задание», не «Повторение». Урок: сессия «14/20» при полных генерациях = что-то подмешивает добивка |
| Тема «Алфавит» выбиралась месяцами (score 0.67 при 96 попытках, colors 0.71 при 302) | score = среднее за всю жизнь: при 300 попытках один ответ двигает на 1/301 — тема замерзала ниже порога done=0.75 навсегда и вечно шла как «слабая» | EMA: `alpha = max(1/(n+1), 1/20)` — последние ~20 ответов доминируют (3 места в training.py). Разовый пересчёт: score = среднее последних 20 ответов по topic_id; alphabet 0.67→0.90 done |
| topic_d повторяет вопрос раз в ~10 дней («буква ц» 4 раза, #138) | Окно `_seen_questions` по умолчанию 60 (~2 дня) — прошлые прогоны темы забывались | В topic_d-генерации окно limit=500 |
| Неверный review_ai испаряется из всех очередей | errors mode фильтровал source in (bonus,new,topic,topic_d) — review_ai там не было; проваленное повторение никуда не попадало (25 невидимых ошибок) | 'review_ai' добавлен в оба errors-фильтра (сессия + stats) |
| Окна дедупа меньше суток реального темпа | Юзер делает 50-110 заданий/день; окна 60/80 в генерационных циклах и 150/300 в pool_draw забывали вчерашнее | Циклы: seen_qs/skeletons = 400; `_pool_draw`: norms 400, skeletons 600 |
| Перечисление букв с русской меткой «(буквы: o, d…)» проходило валидатор | Паттерн якорился на '(' сразу перед буквами; «(буквы: …», «шарф из букв» — метка между скобкой и буквами | Матч по самой последовательности одиночных букв БЕЗ префикса + метки 'z liter/liter[ya]:/букв*:/из букв' (не голое 'liter' — ловило literatura) |
| ОСТОРОЖНО с LIKE-диагностикой повторов | `content LIKE '%слово%'` матчит explanation/word_hints, не только question — «6 показов одного вопроса» оказались разными заданиями со словом oznacza в объяснении | При разборе повторов сравнивать `json_extract(content,'$.question')`, не весь content |
