"""Mistral exercise generation, shared exercise pool, topic/theme selection.

Extracted from routers/training.py. Session endpoints call into this module;
it must NOT import from routers.* (circular import — see CLAUDE.md pitfalls).
"""
import asyncio
import json
import random
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
import prompts
from services import mistral
from services.validators import (
    _norm,
    _validate_type,
    _sanitize_native_fields,
    _clean_word_hints,
    _require_word_hints,
    _fix_flashcard_exercise,
    _fix_mc_exercise,
    _fix_fill_blank_exercise,
    _fix_letter_tiles_exercise,
    _fix_translate_exercise,
    _fix_judge_sentence_exercise,
    _fix_order_words_exercise,
    _fix_word_definition_exercise,
)

_LEVEL_ORDER = ["A0", "A1", "A2", "B1", "B2", "C1", "C2"]

def _eligible_vocab_levels(user_level: str) -> list:
    idx = _LEVEL_ORDER.index(user_level) if user_level in _LEVEL_ORDER else 2
    return _LEVEL_ORDER[:idx + 1]


# Vocab learning scaffold: words still being learned are assembled from letter tiles
# (the letters act as a visible hint); once the user assembles/answers them correctly
# this many times in a row (correct_streak), they graduate to full free-typing.
# A wrong answer resets correct_streak to 0 → the word drops back to letter tiles.
_VOCAB_TILES_GRADUATE = 3

def _vocab_card_content(v, status: str, native_language: str, correct_streak: int) -> dict:
    """Build a vocab exercise dict — letter_tiles (scaffold) while learning, flashcard once mastered.
    Short (<4 chars) or multi-word entries always stay a flashcard (tiles would be trivial/broken)."""
    translation = getattr(v, f"translation_{native_language}", v.translation_en)
    word = (v.polish or "").strip()
    use_tiles = (correct_streak or 0) < _VOCAB_TILES_GRADUATE and " " not in word and len(word) >= 4
    if use_tiles:
        return {
            "type": "letter_tiles",
            "question": f"Собери слово по-польски: {translation}",
            "correct_answer": v.polish,
            "translation": None,
            "vocab_id": v.id,
            "vocab_status": status,
        }
    return {
        "type": "flashcard",
        "question": v.polish,
        "correct_answer": translation,
        "translation": translation,
        "example_sentence": v.example_sentence,
        "vocab_id": v.id,
        "vocab_status": status,
    }

def _next_level(level: str) -> str:
    try:
        idx = _LEVEL_ORDER.index(level)
        return _LEVEL_ORDER[min(idx + 1, len(_LEVEL_ORDER) - 1)]
    except ValueError:
        return level


def _build_avoid_block(user_id: int, level: str, db: Session) -> str:
    result = ""

    # Reported/broken exercises
    reports = db.query(models.GeneratedExerciseReport).filter(
        models.GeneratedExerciseReport.user_id == user_id,
    ).order_by(models.GeneratedExerciseReport.created_at.desc()).limit(30).all()
    report_lines = []
    for r in reports:
        try:
            snap = json.loads(r.exercise_snapshot)
            desc = f'- [{snap.get("type","?")}] "{snap.get("question","")}" → "{snap.get("correct_answer","")}"'
            if r.comment:
                desc += f' (ошибка: {r.comment})'
            report_lines.append(desc)
        except Exception:
            pass
    if report_lines:
        result += "\n\nНИКОГДА не повторяй эти упражнения — пользователь отметил их как ошибочные:\n" + "\n".join(report_lines)

    return result


def _save_to_pool(item: dict, level: str, topic_id, db: Session):
    """Save a validated exercise item to the shared pool. Returns pool_exercise_id or None."""
    q_norm = _norm(item.get("question", ""))
    if not q_norm:
        return None
    existing = db.query(models.ExercisePool).filter(
        models.ExercisePool.question_norm == q_norm
    ).first()
    if existing:
        # If the new exercise has a topic but the pool entry doesn't, update the pool entry
        if topic_id and not existing.topic_id:
            existing_content = json.loads(existing.content)
            existing_content["topic_slug"] = item.get("topic_slug", "")
            existing_content["topic_title"] = item.get("topic_title", "")
            existing.content = json.dumps(existing_content, ensure_ascii=False)
            existing.topic_id = topic_id
            db.add(existing)
            db.flush()
        return existing.id
    pool_ex = models.ExercisePool(
        exercise_type=item.get("type", "fill_blank"),
        level=level,
        topic_id=topic_id,
        content=json.dumps(item, ensure_ascii=False),
        question_norm=q_norm,
        content_type=item.get("content_type"),
    )
    db.add(pool_ex)
    db.flush()
    return pool_ex.id


def _pool_draw(db: Session, user_id: int, level: str, count: int, seen_norms: set | None = None) -> list:
    """Draw up to count unseen active exercises from the shared pool for this user at this level.

    Excludes by pool_exercise_id (entries already served from the pool) AND by question_norm
    against `seen_norms` — a question the user met via a NON-pool DailyExercise (deficit
    generation, older entries) isn't caught by id exclusion and would resurface as "new"
    (reports #194, feedback #99)."""
    seen_sq = db.query(models.DailyExercise.pool_exercise_id).filter(
        models.DailyExercise.user_id == user_id,
        models.DailyExercise.pool_exercise_id.isnot(None),
    ).subquery()
    q = db.query(models.ExercisePool).filter(
        models.ExercisePool.level == level,
        models.ExercisePool.is_active == True,
        models.ExercisePool.id.notin_(seen_sq),
    )
    if seen_norms:
        # over-fetch then filter in Python by normalized question text
        candidates = q.order_by(func.random()).limit(count * 4).all()
        out = [p for p in candidates if (p.question_norm or "") not in seen_norms]
        return out[:count]
    return q.order_by(func.random()).limit(count).all()


def _seen_questions(user_id: int, db: Session, limit: int = 60) -> set:
    """Return normalized question strings from recently completed AI exercises."""
    rows = db.query(models.DailyExercise).filter(
        models.DailyExercise.user_id == user_id,
        models.DailyExercise.source.in_(["new", "bonus"]),
        models.DailyExercise.is_completed == True,
    ).order_by(models.DailyExercise.completed_at.desc()).limit(limit).all()
    result = set()
    for de in rows:
        try:
            q = json.loads(de.content).get("question", "")
            if q:
                result.add(_norm(q))
        except Exception:
            pass
    return result


def _build_known_vocab_block(user_id: int, db: Session) -> str:
    rows = db.query(models.Vocabulary.polish).join(
        models.UserVocabulary,
        models.UserVocabulary.vocab_id == models.Vocabulary.id,
    ).filter(
        models.UserVocabulary.user_id == user_id,
        models.UserVocabulary.correct_streak >= 1,
    ).all()
    if not rows:
        return ""
    words = [r[0] for r in rows]
    sample = random.sample(words, min(10, len(words)))
    return (
        "\n\nПользователь уже знает эти слова — используй некоторые из них"
        " в упражнениях (fill_blank, translate, judge_sentence) для закрепления: "
        + ", ".join(sample)
    )


def _difficulty_hint(user_id: int, db: Session) -> str:
    recent = db.query(models.UserExerciseHistory).filter(
        models.UserExerciseHistory.user_id == user_id,
        models.UserExerciseHistory.is_correct.isnot(None),
    ).order_by(models.UserExerciseHistory.created_at.desc()).limit(30).all()
    # Also count recent daily exercises
    recent_daily = db.query(models.DailyExercise).filter(
        models.DailyExercise.user_id == user_id,
        models.DailyExercise.is_completed == True,
        models.DailyExercise.is_correct.isnot(None),
    ).order_by(models.DailyExercise.completed_at.desc()).limit(30).all()

    total = len(recent) + len(recent_daily)
    if total < 5:
        return ""
    correct = sum(1 for h in recent if h.is_correct) + sum(1 for d in recent_daily if d.is_correct)
    pct = correct / total * 100

    if pct >= 80:
        return f"\n\nАДАПТАЦИЯ: последние {total} ответов — {pct:.0f}% правильных. Пользователь уверенно справляется — немного усложни лексику и грамматику."
    elif pct <= 45:
        return f"\n\nАДАПТАЦИЯ: последние {total} ответов — {pct:.0f}% правильных. Пользователь делает много ошибок — упрости задания, больше базовых конструкций и коротких фраз."
    else:
        return f"\n\nАДАПТАЦИЯ: последние {total} ответов — {pct:.0f}% правильных. Сохрани текущую сложность."


def _mastered_exercise_ids(user_id: int, db: Session, threshold: int = 3) -> set:
    """Return IDs of exercises where the last `threshold` attempts are all correct."""
    from itertools import groupby as _groupby
    rows = (
        db.query(
            models.UserExerciseHistory.exercise_id,
            models.UserExerciseHistory.is_correct,
        )
        .filter(
            models.UserExerciseHistory.user_id == user_id,
            models.UserExerciseHistory.exercise_id.isnot(None),
        )
        .order_by(
            models.UserExerciseHistory.exercise_id,
            models.UserExerciseHistory.created_at.desc(),
        )
        .all()
    )
    mastered = set()
    for ex_id, group in _groupby(rows, key=lambda r: r.exercise_id):
        recent = [r.is_correct for r in list(group)[:threshold]]
        if len(recent) >= threshold and all(recent):
            mastered.add(ex_id)
    return mastered


async def _generate_idiom_drill_exercises(user, db: Session, today, max_count: int = 2, source: str = "new"):
    """Turn known idioms/expressions into fill_blank or letter_tiles exercises."""
    undrilled = db.query(models.UserKnownExpression).filter(
        models.UserKnownExpression.user_id == user.id,
        models.UserKnownExpression.drilled_at.is_(None),
    ).order_by(models.UserKnownExpression.created_at).limit(max_count).all()

    if not undrilled:
        return

    expressions_json = json.dumps(
        [{"expression": e.expression, "meaning": e.meaning or ""} for e in undrilled],
        ensure_ascii=False,
    )
    prompt = prompts.IDIOM_DRILL_PROMPT.format(
        level=user.level,
        native_language=user.native_language,
        expressions=expressions_json,
    )

    try:
        raw = await mistral.simple_prompt(
            system="You are a Polish language exercise generator. Respond only with valid JSON array.",
            user=prompt,
            temperature=0.7,
            max_tokens=1500,
            timeout=30.0,
            retries=1,
            model="mistral-small-latest",
            purpose="idiom_drill",
            user_id=user.id,
        )
        generated = await mistral.parse_json_response(raw)
    except Exception as e:
        print(f"[idiom_drill] Mistral failed for user {user.id}: {e}")
        generated = []

    seen_qs = _seen_questions(user.id, db)
    added = 0
    for item in generated:
        item = _validate_type(item)
        item = _fix_fill_blank_exercise(item) if item else None
        item = _fix_letter_tiles_exercise(item) if item else None
        if item is None:
            continue
        item = _sanitize_native_fields(item, user.native_language)
        item = _clean_word_hints(item)
        # Drill sentences are pure Polish with no other aid — word_hints are mandatory
        # for BOTH types here, otherwise the user can't understand the sentence (feedback #93)
        if not item.get("word_hints"):
            continue
        if _norm(item.get("question", "")) in seen_qs:
            continue
        item["topic_title"] = "Идиомы"  # session header badge
        db.add(models.DailyExercise(
            user_id=user.id, date=today,
            exercise_type=item.get("type"),
            content=json.dumps(item, ensure_ascii=False),
            source=source,
        ))
        added += 1

    for e_obj in undrilled:
        e_obj.drilled_at = datetime.utcnow()
    db.commit()
    if added:
        print(f"[idiom_drill] {added} exercises from {len(undrilled)} expressions for user {user.id}")


async def _ensure_vocab_pool(user, db: Session, threshold: int = 20, batch: int = 30):
    """Generate new vocabulary words via Mistral when pool runs low."""
    eligible_levels = _eligible_vocab_levels(user.level)
    seen_ids = {uv.vocab_id for uv in db.query(models.UserVocabulary).filter(
        models.UserVocabulary.user_id == user.id
    ).all()}
    new_count = db.query(models.Vocabulary).filter(
        models.Vocabulary.level.in_(eligible_levels),
        models.Vocabulary.id.notin_(seen_ids) if seen_ids else True,
    ).count()

    if new_count >= threshold:
        return  # pool is fine

    # Build avoid list from the 60 most recently added vocab words (scalable even with thousands)
    recent_words = db.query(models.Vocabulary.polish).order_by(
        models.Vocabulary.id.desc()
    ).limit(60).all()
    avoid_list = ", ".join(w[0] for w in recent_words) if recent_words else "none"

    try:
        raw = await mistral.simple_prompt(
            system="You are a Polish vocabulary generator. Respond only with valid JSON array.",
            user=prompts.VOCAB_GENERATION_PROMPT.format(
                level=user.level,
                native_language=user.native_language,
                count=batch,
                avoid_words=avoid_list,
            ),
            temperature=0.85,
            max_tokens=3000,
            timeout=20.0,
            retries=1,
            model="mistral-small-latest",
        )
        generated = await mistral.parse_json_response(raw)
    except Exception as e:
        print(f"[vocab_gen] Mistral failed for user {user.id}: {e}")
        return

    # Deduplicate: skip words that already exist (exact match after lowercase strip)
    existing_polish = {
        row[0].strip().lower()
        for row in db.query(models.Vocabulary.polish).all()
    }
    topic_id = None  # generated vocab has no specific topic
    added = 0
    for item in generated:
        polish = (item.get("polish") or "").strip()
        if not polish or polish.lower() in existing_polish:
            continue
        db.add(models.Vocabulary(
            polish=polish,
            translation_ru=item.get("translation_ru", ""),
            translation_en=item.get("translation_en", ""),
            example_sentence=item.get("example_sentence", ""),
            topic_id=topic_id,
            level=user.level,
        ))
        existing_polish.add(polish.lower())
        added += 1

    if added:
        db.commit()
        print(f"[vocab_gen] Added {added} new vocabulary words for user {user.id}")


def _select_interest_themes(prefs, n: int = 2) -> str:
    """Pick up to n interest themes with even rotation (mirrors the topic 7-day rotation idea,
    but via a stored cursor since themes aren't tracked on DailyExercise).

    Prefers themes not used recently (fresh) over recently-used (stale); records the choice in
    prefs.recent_themes so over time every theme is covered evenly with no skew. The caller's
    later db.commit() persists the updated cursor. Mutates prefs in place.
    """
    fallback = "не заданы (используй разнообразные темы)"
    if not prefs or not prefs.interest_themes:
        return fallback
    try:
        themes = [t for t in json.loads(prefs.interest_themes) if t]
    except Exception:
        return fallback
    if not themes:
        return fallback
    if len(themes) <= n:
        return ", ".join(themes)

    try:
        recent = [t for t in json.loads(prefs.recent_themes or "[]") if t]
    except Exception:
        recent = []

    fresh = [t for t in themes if t not in recent]
    stale = [t for t in themes if t in recent]
    random.shuffle(fresh)
    random.shuffle(stale)
    chosen = (fresh + stale)[:n]

    # Keep a rolling window so at least n themes stay "fresh" → forces cycling through all
    new_recent = recent + chosen
    window = max(0, len(themes) - n)
    prefs.recent_themes = json.dumps(new_recent[-window:], ensure_ascii=False)
    return ", ".join(chosen)


def _select_topics_for_generation(user, db: Session, n: int = 2) -> list:
    """Pick n grammar topics for generation.

    Priority order:
    1. Topics at A0..current_level sorted by progress score ascending (weakest first, lower level first).
    2. When >=60% of A0..current_level topics are done, also include one topic from next level.
    7-day rotation: prefer topics not recently covered, but never let recency override level priority.
    """
    level_idx = _LEVEL_ORDER.index(user.level) if user.level in _LEVEL_ORDER else 2
    current_and_below = _LEVEL_ORDER[:level_idx + 1]
    next_level = _LEVEL_ORDER[level_idx + 1] if level_idx + 1 < len(_LEVEL_ORDER) else None

    progress_by_topic = {
        p.topic_id: p for p in db.query(models.UserTopicProgress).filter(
            models.UserTopicProgress.user_id == user.id
        ).all()
    }
    done_ids = {tid for tid, p in progress_by_topic.items() if p.status == "done"}

    def _topic_score(t):
        p = progress_by_topic.get(t.id)
        return p.score if p and p.score is not None else 0.0

    # Topics that produce nonsensical exercises (phonetics/alphabet can't be translated/filled-in)
    _SKIP_GENERATION_SLUGS = {"alphabet", "letters", "pronunciation"}

    # Candidate pool: current+below levels, non-done, has explanation
    all_eligible = db.query(models.Topic).filter(
        models.Topic.explanation_ru.isnot(None),
        models.Topic.explanation_ru != "",
        models.Topic.level_required.in_(current_and_below),
    ).all()
    candidates = [t for t in all_eligible
                  if t.id not in done_ids and t.slug not in _SKIP_GENERATION_SLUGS]

    # Sort: lower level first, then lower score first (weakest topics get priority)
    candidates.sort(key=lambda t: (_LEVEL_ORDER.index(t.level_required) if t.level_required in _LEVEL_ORDER else 99, _topic_score(t)))

    # If >=80% of current+below topics are done, inject one next-level topic
    if next_level and all_eligible:
        coverage = 1 - len(candidates) / len(all_eligible)
        if coverage >= 0.8:
            next_topics = db.query(models.Topic).filter(
                models.Topic.explanation_ru.isnot(None),
                models.Topic.explanation_ru != "",
                models.Topic.level_required == next_level,
                models.Topic.id.notin_(done_ids) if done_ids else True,
            ).all()
            if next_topics:
                next_topics.sort(key=_topic_score)
                candidates.append(next_topics[0])

    if not candidates:
        return []

    # 7-day rotation: mark recently covered topics
    cutoff = (datetime.utcnow() - timedelta(days=7)).date()
    recent_ids = {
        row[0] for row in db.query(models.DailyExercise.topic_id).filter(
            models.DailyExercise.user_id == user.id,
            models.DailyExercise.topic_id.isnot(None),
            models.DailyExercise.source.in_(["new", "bonus"]),
            models.DailyExercise.date >= cutoff,
        ).all()
        if row[0]
    }

    # Pick n topics: prefer fresh ones but never skip a whole level for freshness.
    # Strategy: for each slot, pick the highest-priority fresh topic; if none, pick highest-priority recent.
    chosen = []
    used_ids = set()
    fresh = [t for t in candidates if t.id not in recent_ids]
    stale = [t for t in candidates if t.id in recent_ids]

    for pool in (fresh, stale):
        for t in pool:
            if t.id not in used_ids:
                chosen.append(t)
                used_ids.add(t.id)
            if len(chosen) >= n:
                break
        if len(chosen) >= n:
            break

    return chosen


async def _generate_exercises(user, count: int, interest_themes_str: str, level: str = None, topics: list = None) -> list:
    """Generate exercises in five parallel batches: grammar, lexical, judge_sentence, letter_tiles, word_definition.

    When topics is provided, the grammar batch is replaced with per-topic batches so exercises
    are tied to specific grammar rules. Each grammar exercise gets topic_slug + topic_title in content.
    """
    gen_level = level or user.level
    word_def_count = max(1, count // 10)        # ~1-2 из 15
    letter_tiles_count = max(1, count // 8)     # ~2 из 15
    judge_count = max(2, count // 5)            # ~3 из 15
    idiom_count = max(1, count // 8)            # ~2 из 15 — отдельный топик-free батч реальных идиом
    remaining = count - judge_count - letter_tiles_count - word_def_count - idiom_count
    grammar_count = (remaining + 1) // 2
    lexical_count = remaining - grammar_count

    _SYSTEM = "You are a Polish language exercise generator. Respond only with valid JSON array."

    async def _batch_idiom(batch_count):
        """Topic-free idiom flashcards from Mistral's real idiom knowledge (not forced into a grammar topic)."""
        prompt = prompts.IDIOM_FLASHCARD_PROMPT.format(
            level=gen_level, native_language=user.native_language, count=batch_count,
        )
        for model_name, timeout_sec in [("mistral-large-latest", 60.0), ("mistral-small-latest", 40.0)]:
            try:
                raw = await mistral.simple_prompt(
                    system=_SYSTEM, user=prompt,
                    temperature=0.9, max_tokens=2000,  # higher temp → more idiom variety
                    timeout=timeout_sec, retries=1, model=model_name,
                    purpose="idiom", user_id=user.id,
                )
                result = await mistral.parse_json_response(raw)
                print(f"[idiom] {model_name} → {len(result)} items for user {user.id}")
                return result
            except Exception as e:
                print(f"[idiom] {model_name} failed for user {user.id}: {type(e).__name__}: {e}")
        return []

    async def _batch(prompt_template, batch_count, label):
        prompt = prompt_template.format(
            level=gen_level,
            native_language=user.native_language,
            interest_themes=interest_themes_str,
            count=batch_count,
        )
        if topics:
            rule_names = ", ".join(t.title_ru or t.slug for t in topics)
            prompt = f"Правила грамматики этой сессии: {rule_names}. Используй примеры в контексте этих правил.\n\n" + prompt
        for model_name, timeout_sec in [("mistral-large-latest", 60.0), ("mistral-small-latest", 40.0)]:
            try:
                raw = await mistral.simple_prompt(
                    system=_SYSTEM, user=prompt,
                    temperature=0.85, max_tokens=3000,
                    timeout=timeout_sec, retries=1, model=model_name,
                    purpose=label, user_id=user.id,
                )
                result = await mistral.parse_json_response(raw)
                print(f"[{label}] {model_name} → {len(result)} items for user {user.id}")
                return result
            except Exception as e:
                print(f"[{label}] {model_name} failed for user {user.id}: {type(e).__name__}: {e}")
        return []

    async def _batch_for_topic(topic_obj, batch_count):
        title = topic_obj.title_ru or topic_obj.slug
        summary = (topic_obj.explanation_ru or "")[:900]
        prompt = (
            "Ты генератор упражнений по польскому языку.\n"
            f"Уровень: {gen_level}. Родной язык: {user.native_language}.\n"
            f"Тема правила: {title}\n\n"
            f"Описание правила:\n{summary}\n\n"
            + prompts._EXERCISE_COMMON_RULES + "\n\n"
            f"Сгенерируй {batch_count} упражнений. Типы: fill_blank, multiple_choice. Миксуй равномерно.\n"
            "ВСЕ упражнения должны явно проверять это правило.\n"
            "ЗАПРЕЩЕНО: задания о произношении или 'как читается' — только грамматика.\n\n"
            "FILL_BLANK:\n"
            "- РОВНО ОДИН ___ в question\n"
            "- Ответ НЕ присутствует в question\n"
            "- hint: грамматическая категория, НЕ сам ответ\n\n"
            "MULTIPLE_CHOICE — 4 варианта:\n"
            "- correct_answer ДОСЛОВНО совпадает с одним из options\n"
            "- ЗАПРЕЩЕНО: мета-вопросы где ответ виден в тексте вопроса\n\n"
            "Ответь ТОЛЬКО валидным JSON без markdown:\n"
            '[{"type": "fill_blank", "question": "Poproszę ___ kawy.", "correct_answer": "filiżankę", '
            '"options": null, "hint": "biernik od filiżanka", "explanation": "После poproszę — biernik", '
            '"translation": "Прошу чашечку кофе.", "word_hints": {"poproszę": "прошу", "kawy": "кофе"}}]'
        )
        for model_name, timeout_sec in [("mistral-large-latest", 60.0), ("mistral-small-latest", 40.0)]:
            try:
                raw = await mistral.simple_prompt(
                    system=_SYSTEM, user=prompt,
                    temperature=0.8, max_tokens=2500,
                    timeout=timeout_sec, retries=1, model=model_name,
                    purpose="grammar_topic", user_id=user.id,
                )
                result = await mistral.parse_json_response(raw)
                for item in result:
                    item["topic_slug"] = topic_obj.slug
                    item["topic_title"] = topic_obj.title_ru or topic_obj.slug
                print(f"[grammar:topic:{topic_obj.slug}] {model_name} → {len(result)} for user {user.id}")
                return result
            except Exception as e:
                print(f"[grammar:topic:{topic_obj.slug}] {model_name} failed: {e}")
        return []

    async def _batch_for_topic_lexical(topic_obj, batch_count):
        """Generate flashcard/translate/order_words exercises about the topic's vocabulary."""
        title = topic_obj.title_ru or topic_obj.slug
        summary = (topic_obj.explanation_ru or "")[:600]
        prompt = (
            "Ты генератор упражнений по польскому языку.\n"
            f"Уровень: {gen_level}. Родной язык: {user.native_language}.\n"
            f"Тема: {title}\n\n"
            f"Контекст правила:\n{summary}\n\n"
            + prompts._EXERCISE_COMMON_RULES + "\n\n"
            f"Сгенерируй {batch_count} упражнений с лексикой и фразами, связанными с этой темой.\n"
            "Типы (смешай равномерно): translate, order_words. (Идиомы/flashcard здесь НЕ генерируй.)\n"
            "TRANSLATE: русская фраза ≤ 10 слов → польский перевод, используя грамматику темы.\n"
            "ORDER_WORDS: слова польского предложения перемешаны через ' / ', correct_answer = правильный порядок, translation = перевод.\n"
            "Ответь ТОЛЬКО валидным JSON массивом без markdown:\n"
            "[\n"
            '  {"type": "translate", "question": "Это моя книга.", "correct_answer": "To jest moja książka.", "hint": null, "translation": null},\n'
            '  {"type": "order_words", "question": "jest / moja / To / książka", "correct_answer": "To jest moja książka.", "hint": null, "translation": "Это моя книга."}\n'
            "]"
        )
        for model_name, timeout_sec in [("mistral-large-latest", 60.0), ("mistral-small-latest", 40.0)]:
            try:
                raw = await mistral.simple_prompt(
                    system="You are a Polish language exercise generator. Respond only with valid JSON array.",
                    user=prompt,
                    temperature=0.8, max_tokens=2000,
                    timeout=timeout_sec, retries=1, model=model_name,
                    purpose="lexical_topic", user_id=user.id,
                )
                result = await mistral.parse_json_response(raw)
                for item in result:
                    item["topic_slug"] = topic_obj.slug
                    item["topic_title"] = topic_obj.title_ru or topic_obj.slug
                print(f"[lexical:topic:{topic_obj.slug}] {model_name} → {len(result)} for user {user.id}")
                return result
            except Exception as e:
                print(f"[lexical:topic:{topic_obj.slug}] {model_name} failed: {e}")
        return []

    if topics:
        n_t = len(topics)
        per_topic_grammar = max(2, grammar_count // n_t)
        per_topic_lexical = max(1, lexical_count // n_t)
        all_tasks = (
            [_batch_for_topic(t, per_topic_grammar) for t in topics] +
            [_batch_for_topic_lexical(t, per_topic_lexical) for t in topics] +
            [
                _batch(prompts.JUDGE_EXERCISES_PROMPT, judge_count, "judge"),
                _batch(prompts.LETTER_TILES_PROMPT, letter_tiles_count, "letter_tiles"),
                _batch(prompts.WORD_DEFINITION_PROMPT, word_def_count, "word_def"),
                _batch_idiom(idiom_count),
            ]
        )
        results = await asyncio.gather(*all_tasks)
        grammar_gen = [item for sub in results[:n_t] for item in sub]
        lexical_gen = [item for sub in results[n_t:2*n_t] for item in sub]
        judge_gen, tiles_gen, word_def_gen, idiom_gen = results[2*n_t], results[2*n_t+1], results[2*n_t+2], results[2*n_t+3]
        # Assign topics to global batches via round-robin so every exercise has a badge.
        # Idioms stay topic-FREE (they're not about a grammar rule) → no topic badge.
        global_gen = judge_gen + tiles_gen + word_def_gen
        for i, item in enumerate(global_gen):
            t = topics[i % n_t]
            item["topic_slug"] = t.slug
            item["topic_title"] = t.title_ru or t.slug
    else:
        grammar_gen, lexical_gen, judge_gen, tiles_gen, word_def_gen, idiom_gen = await asyncio.gather(
            _batch(prompts.GRAMMAR_EXERCISES_PROMPT, grammar_count, "grammar"),
            _batch(prompts.LEXICAL_EXERCISES_PROMPT, lexical_count, "lexical"),
            _batch(prompts.JUDGE_EXERCISES_PROMPT, judge_count, "judge"),
            _batch(prompts.LETTER_TILES_PROMPT, letter_tiles_count, "letter_tiles"),
            _batch(prompts.WORD_DEFINITION_PROMPT, word_def_count, "word_def"),
            _batch_idiom(idiom_count),
        )
    all_items = grammar_gen + lexical_gen + judge_gen + tiles_gen + word_def_gen + idiom_gen
    return await _verify_judge_false(all_items, user)


async def _verify_judge_false(items: list, user) -> list:
    """Variant B post-validation: drop judge_sentence 'false' items whose claimed error
    a strict second pass can't confirm. Mistral routinely marks correct sentences false
    with incoherent explanations (reports #185/186/190/191/193). One batched cheap call."""
    suspects = [
        it for it in items
        if it.get("type") == "judge_sentence"
        and str(it.get("correct_answer", "")).lower() == "false"
    ]
    if not suspects:
        return items
    payload = [
        {"id": i, "sentence": it.get("question", ""), "claimed_error": it.get("explanation", "")}
        for i, it in enumerate(suspects)
    ]
    try:
        raw = await mistral.simple_prompt(
            system="You are a strict Polish grammar checker. Respond only with JSON.",
            user=prompts.JUDGE_VERIFY_PROMPT.format(items=json.dumps(payload, ensure_ascii=False)),
            temperature=0.0,
            max_tokens=800,
            timeout=30.0,
            retries=1,
            model="mistral-small-latest",
            purpose="judge_verify",
            user_id=user.id,
        )
        verdicts = await mistral.parse_json_response(raw)
        confirmed = {v["id"] for v in verdicts if isinstance(v, dict) and v.get("verdict") == "error"}
    except Exception as e:
        print(f"[judge_verify] failed for user {user.id}: {type(e).__name__}: {e}")
        # On verifier failure, drop ALL false-judge items rather than ship unverified garbage
        confirmed = set()
    rejected = {id(suspects[i]) for i in range(len(suspects)) if i not in confirmed}
    kept = [it for it in items if id(it) not in rejected]
    dropped = len(items) - len(kept)
    if dropped:
        print(f"[judge_verify] dropped {dropped}/{len(suspects)} false-judge items for user {user.id}")
    return kept


async def _generate_topic_pool(user, topic_obj, db: Session, today, count: int):
    """Generate exercises for a specific grammar rule topic and save with source='topic'."""
    title = topic_obj.title_ru or topic_obj.slug
    summary = (topic_obj.explanation_ru or "")[:1000]

    prompt = (
        "Ты генератор упражнений по польскому языку.\n"
        "Тема правила: " + title + " (уровень " + user.level + ", родной язык: " + user.native_language + ")\n\n"
        "Описание правила (используй как основу для заданий):\n" + summary + "\n\n"
        + prompts._EXERCISE_COMMON_RULES + "\n\n"
        "Сгенерируй ровно " + str(count) + " упражнений СТРОГО по этой теме.\n"
        "Типы: fill_blank и multiple_choice (миксуй примерно пополам).\n"
        "ВСЕ упражнения должны явно проверять понимание именно этого правила.\n"
        "ЗАПРЕЩЕНО: задания о произношении, фонетической транскрипции или 'как читается' — только грамматика и лексика.\n\n"
        "FILL_BLANK:\n"
        "- РОВНО ОДИН ___ в question\n"
        "- Ответ НЕ присутствует в question (не в скобках, не рядом с ___)\n"
        "- ЗАПРЕЩЁН мужской неодушевлённый в biernik (не меняется → тривиальный)\n"
        "- correct_answer: одно слово или устойчивая фраза без /\n"
        "- hint: грамматическая категория, НЕ сам ответ\n"
        "- word_hints: польские слова question → " + user.native_language + "\n\n"
        "MULTIPLE_CHOICE — 4 варианта:\n"
        "- correct_answer ДОСЛОВНО совпадает с одним из options\n"
        "- Варианты принципиально разные (разные падежи/формы)\n"
        "- Если вопрос о значении — все варианты на " + user.native_language + "\n"
        "- word_hints: польские слова question → " + user.native_language + " (1-3 ключевых, кроме вариантов)\n\n"
        "Ответь ТОЛЬКО валидным JSON массивом без markdown:\n"
        "[\n"
        '  {"type": "fill_blank", "question": "Poproszę ___ kawy.", "correct_answer": "filiżankę", "options": null, "hint": "biernik od filiżanka", "explanation": "После poproszę — biernik", "translation": null, "word_hints": {"poproszę": "прошу"}},\n'
        '  {"type": "multiple_choice", "question": "Lubię ___ (herbata).", "options": ["herbatę", "herbaty", "herbacie", "herbata"], "correct_answer": "herbatę", "hint": null, "explanation": "После lubię — biernik", "translation": null, "word_hints": {"lubię": "люблю"}}\n'
        "]"
    )

    _SYSTEM = "You are a Polish language exercise generator. Respond only with valid JSON array."
    raw = None
    for model_name, timeout_sec in [("mistral-large-latest", 60.0), ("mistral-small-latest", 40.0)]:
        try:
            raw = await mistral.simple_prompt(
                system=_SYSTEM, user=prompt,
                temperature=0.8, max_tokens=3000,
                timeout=timeout_sec, retries=1, model=model_name,
            )
            break
        except Exception as e:
            print(f"[topic] {model_name} failed: {type(e).__name__}: {e}")
    if not raw:
        return

    generated = await mistral.parse_json_response(raw)
    seen_qs = _seen_questions(user.id, db)
    added = 0
    for item in generated:
        item = _validate_type(item)
        if item is None:
            continue
        item = _fix_mc_exercise(item)
        if item is None:
            continue
        item = _fix_fill_blank_exercise(item) if item and item.get("type") == "fill_blank" else item
        if item is None:
            continue
        item = _fix_flashcard_exercise(item) if item else None
        if item is None:
            continue
        item = _fix_judge_sentence_exercise(item) if item else None
        if item is None:
            continue
        item = _sanitize_native_fields(item, user.native_language)
        item = _clean_word_hints(item)
        item = _require_word_hints(item)
        if item is None:
            continue
        if _norm(item.get("question", "")) in seen_qs:
            continue
        content = json.dumps(item)
        db.add(models.DailyExercise(
            user_id=user.id, date=today,
            exercise_type=item.get("type", "fill_blank"),
            content=content, source="topic",
            topic_id=topic_obj.id,
        ))
        added += 1
    db.commit()
    print(f"[topic:{topic_obj.slug}] added {added} exercises for user {user.id}")


async def _generate_topic_exercises_for_daily(user, db: Session, today) -> list:
    """Pick 2 random non-done topics with explanation and generate 2 exercises each."""
    already_today = {
        row.topic_id for row in db.query(models.DailyExercise.topic_id).filter(
            models.DailyExercise.user_id == user.id,
            models.DailyExercise.source == "topic_d",
            models.DailyExercise.date == today,
            models.DailyExercise.topic_id.isnot(None),
        ).all()
    }
    done_topic_ids = {
        p.topic_id for p in db.query(models.UserTopicProgress).filter(
            models.UserTopicProgress.user_id == user.id,
            models.UserTopicProgress.status == "done",
        ).all()
    }
    exclude_topic_ids = done_topic_ids | already_today

    eligible_levels = _LEVEL_ORDER[:(_LEVEL_ORDER.index(user.level) + 1 if user.level in _LEVEL_ORDER else 3)]
    q = db.query(models.Topic).filter(
        models.Topic.explanation_ru.isnot(None),
        models.Topic.explanation_ru != "",
        models.Topic.level_required.in_(eligible_levels),
    )
    if exclude_topic_ids:
        q = q.filter(models.Topic.id.notin_(exclude_topic_ids))
    candidates = q.all()
    if not candidates:
        return []

    weak_topic_ids = {
        p.topic_id for p in db.query(models.UserTopicProgress).filter(
            models.UserTopicProgress.user_id == user.id,
            models.UserTopicProgress.status.in_(["needs_review", "in_progress"]),
        ).all()
    }
    weak_cands = [t for t in candidates if t.id in weak_topic_ids]
    other_cands = [t for t in candidates if t.id not in weak_topic_ids]

    chosen: list = []
    if weak_cands:
        chosen += random.sample(weak_cands, min(2, len(weak_cands)))
    if len(chosen) < 2 and other_cands:
        chosen += random.sample(other_cands, min(2 - len(chosen), len(other_cands)))
    if not chosen:
        return []

    _SYSTEM = "You are a Polish language exercise generator. Respond only with valid JSON array."

    async def _gen_for_topic(topic_obj):
        title = topic_obj.title_ru or topic_obj.slug
        summary = (topic_obj.explanation_ru or "")[:1000]
        prompt = (
            "Ты генератор упражнений по польскому языку.\n"
            "Тема правила: " + title + " (уровень " + user.level + ", родной язык: " + user.native_language + ")\n\n"
            "Описание правила (используй как основу для заданий):\n" + summary + "\n\n"
            + prompts._EXERCISE_COMMON_RULES + "\n\n"
            "Сгенерируй ровно 2 упражнения СТРОГО по этой теме.\n"
            "Типы: fill_blank и multiple_choice (одно каждого).\n"
            "ВСЕ упражнения должны явно проверять понимание именно этого правила.\n"
            "ЗАПРЕЩЕНО: задания о произношении, фонетической транскрипции или 'как читается' — только грамматика и лексика.\n\n"
            "FILL_BLANK:\n"
            "- РОВНО ОДИН ___ в question\n"
            "- Ответ НЕ присутствует в question\n"
            "- correct_answer: одно слово или устойчивая фраза без /\n"
            "- hint: грамматическая категория, НЕ сам ответ\n\n"
            "MULTIPLE_CHOICE — 4 варианта:\n"
            "- correct_answer ДОСЛОВНО совпадает с одним из options\n"
            "- Варианты принципиально разные (разные падежи/формы)\n"
            "- word_hints: польские слова question → " + user.native_language + " (1-3 ключевых)\n\n"
            "Ответь ТОЛЬКО валидным JSON массивом без markdown:\n"
            "[\n"
            '  {"type": "fill_blank", "question": "Poproszę ___ kawy.", "correct_answer": "filiżankę", "options": null, "hint": "biernik od filiżanka", "explanation": "После poproszę — biernik", "translation": null, "word_hints": {"poproszę": "прошу"}},\n'
            '  {"type": "multiple_choice", "question": "Lubię ___ (herbata).", "options": ["herbatę", "herbaty", "herbacie", "herbata"], "correct_answer": "herbatę", "hint": null, "explanation": "После lubię — biernik", "translation": null, "word_hints": {"lubię": "люблю"}}\n'
            "]"
        )
        raw = None
        for model_name, timeout_sec in [("mistral-large-latest", 60.0), ("mistral-small-latest", 40.0)]:
            try:
                raw = await mistral.simple_prompt(
                    system=_SYSTEM, user=prompt,
                    temperature=0.8, max_tokens=1500,
                    timeout=timeout_sec, retries=1, model=model_name,
                )
                break
            except Exception as e:
                print(f"[topic_d:{topic_obj.slug}] {model_name} failed: {type(e).__name__}: {e}")
        if not raw:
            return []

        generated = await mistral.parse_json_response(raw)
        seen_qs = _seen_questions(user.id, db)
        results = []
        for item in generated:
            item = _validate_type(item)
            if item is None:
                continue
            item = _fix_mc_exercise(item)
            if item is None:
                continue
            if item.get("type") == "fill_blank":
                item = _fix_fill_blank_exercise(item)
            if item is None:
                continue
            if _norm(item.get("question", "")) in seen_qs:
                continue
            # Add topic info to content JSON so the badge can display the topic name
            item["topic_slug"] = topic_obj.slug
            item["topic_title"] = topic_obj.title_ru or topic_obj.slug
            results.append((item, topic_obj.id))
        print(f"[topic_d:{topic_obj.slug}] {len(results)} exercises for user {user.id}")
        return results

    all_results = await asyncio.gather(*[_gen_for_topic(t) for t in chosen])

    entries = []
    for topic_results in all_results:
        for item, topic_id in topic_results:
            entries.append(models.DailyExercise(
                user_id=user.id, date=today,
                exercise_type=item.get("type", "fill_blank"),
                content=json.dumps(item, ensure_ascii=False),
                source="topic_d",
                topic_id=topic_id,
            ))
    print(f"[topic_d] total {len(entries)} exercises from {len(chosen)} topics for user {user.id}")
    return entries


async def _generate_daily_pool(user, db: Session, today, count: int):
    prefs = user.content_preferences
    completed_topics = db.query(models.Topic).join(models.UserTopicProgress).filter(
        models.UserTopicProgress.user_id == user.id,
        models.UserTopicProgress.status == "done",
    ).all()
    weak_topics = db.query(models.Topic).join(models.UserTopicProgress).filter(
        models.UserTopicProgress.user_id == user.id,
        models.UserTopicProgress.score < 0.6,
    ).all()

    completed_names = [t.title_ru for t in completed_topics]
    weak_names = [t.title_ru for t in weak_topics]

    # Fetch DB-based exercises first to know how many AI slots we need
    max_weak = max(1, int(count * 0.3))
    max_review = max(1, int(count * 0.2))

    # 3-day cooldown: don't show the same weak exercise that already appeared recently
    recent_weak_daily = db.query(models.DailyExercise).filter(
        models.DailyExercise.user_id == user.id,
        models.DailyExercise.source == "weak",
        models.DailyExercise.date >= today - timedelta(days=3),
        models.DailyExercise.date < today,
    ).all()
    cooldown_ids = set()
    for de in recent_weak_daily:
        try:
            c = json.loads(de.content)
            if c.get("id"):
                cooldown_ids.add(int(c["id"]))
        except Exception:
            pass

    # Ensure vocab pool has enough words; trigger AI generation if running low
    await _ensure_vocab_pool(user, db)

    # Generate drill exercises for known idioms (runs silently if nothing to drill)
    await _generate_idiom_drill_exercises(user, db, today)

    mastered_ids = _mastered_exercise_ids(user.id, db, threshold=3)
    exclude_ids = cooldown_ids | mastered_ids

    weak_q = db.query(models.Exercise).join(models.Topic).join(models.UserTopicProgress).filter(
        models.UserTopicProgress.user_id == user.id,
        models.UserTopicProgress.score < 0.6,
    )
    if exclude_ids:
        weak_q = weak_q.filter(models.Exercise.id.notin_(exclude_ids))
    weak_exs = weak_q.limit(max_weak).all()

    due_vocab = db.query(models.UserVocabulary).filter(
        models.UserVocabulary.user_id == user.id,
        models.UserVocabulary.next_review <= today,
    ).limit(max_review).all()

    # AI exercises due for SRS review (up to 3 per day)
    ai_due = db.query(models.DailyExercise).filter(
        models.DailyExercise.user_id == user.id,
        models.DailyExercise.next_review <= today,
        models.DailyExercise.is_correct == True,
        models.DailyExercise.source.in_(["new", "bonus", "review_ai"]),
    ).order_by(models.DailyExercise.next_review).limit(3).all()

    # AI fills whatever is left; reserve ~6 slots for new_vocab(2) and topic_d(~4)
    ai_target = max(count - len(weak_exs) - len(due_vocab) - len(ai_due) - 6, count // 4)

    interest_themes_str = _select_interest_themes(prefs)  # max 2 themes, even rotation

    gen_topics = _select_topics_for_generation(user, db)
    topic_id_by_slug = {t.slug: t.id for t in gen_topics}

    entries = []

    for ex in weak_exs:
        opts = None
        if ex.options:
            try:
                opts = json.loads(ex.options)
            except Exception:
                pass
        content = json.dumps({
            "id": ex.id, "type": ex.type, "question": ex.question,
            "correct_answer": ex.correct_answer, "options": opts,
            "hint": ex.hint, "explanation": ex.explanation,
        })
        entries.append(models.DailyExercise(
            user_id=user.id, date=today, exercise_type=ex.type,
            content=content, source="weak", topic_id=ex.topic_id,
        ))

    for de in ai_due:
        entries.append(models.DailyExercise(
            user_id=user.id, date=today,
            exercise_type=de.exercise_type,
            content=de.content,
            source="review_ai",
            srs_interval_days=de.srs_interval_days,
            srs_repetitions=de.srs_repetitions,
        ))
        de.next_review = None  # cleared — new record will carry the SRS forward

    for uv in due_vocab:
        v = uv.vocab
        card = _vocab_card_content(v, "review", user.native_language, uv.correct_streak or 0)
        entries.append(models.DailyExercise(
            user_id=user.id, date=today, exercise_type=card["type"],
            content=json.dumps(card, ensure_ascii=False), source="review",
        ))

    # Add 2 brand-new vocabulary words to daily pool (words user has never encountered)
    seen_vocab_ids = {uv.vocab_id for uv in db.query(models.UserVocabulary).filter(
        models.UserVocabulary.user_id == user.id
    ).all()}
    new_vocab_words = db.query(models.Vocabulary).filter(
        models.Vocabulary.level.in_(_eligible_vocab_levels(user.level)),
        models.Vocabulary.id.notin_(seen_vocab_ids) if seen_vocab_ids else True,
    ).limit(2).all()
    for v in new_vocab_words:
        card = _vocab_card_content(v, "new", user.native_language, 0)  # brand-new → streak 0 → tiles
        entries.append(models.DailyExercise(
            user_id=user.id, date=today, exercise_type=card["type"],
            content=json.dumps(card, ensure_ascii=False), source="vocab",
        ))

    # Pool-first: serve unseen exercises from shared pool, generate only the deficit
    pool_drawn = _pool_draw(db, user.id, user.level, ai_target, seen_norms=_seen_questions(user.id, db, limit=150))
    pool_ai_added = 0
    for pool_ex in pool_drawn:
        if pool_ai_added >= ai_target:
            break
        try:
            item = json.loads(pool_ex.content)
        except Exception:
            continue
        pool_ex.use_count = (pool_ex.use_count or 0) + 1
        entries.append(models.DailyExercise(
            user_id=user.id, date=today,
            exercise_type=pool_ex.exercise_type,
            content=pool_ex.content,
            source="new",
            content_type=pool_ex.content_type,
            topic_id=pool_ex.topic_id,
            pool_exercise_id=pool_ex.id,
        ))
        pool_ai_added += 1

    deficit = ai_target - pool_ai_added
    print(f"[daily_pool] user={user.id} level={user.level} ai_target={ai_target} pool={pool_ai_added} deficit={deficit} weak={len(weak_exs)} vocab={len(due_vocab)} topics={[t.slug for t in gen_topics]}")

    # Generate only the deficit via Mistral + topic_d in parallel
    topic_d_entries = []
    if deficit > 0:
        generated, topic_d_entries = await asyncio.gather(
            _generate_exercises(user, deficit, interest_themes_str, topics=gen_topics or None),
            _generate_topic_exercises_for_daily(user, db, today),
        )
        seen_qs = _seen_questions(user.id, db)
        validated = []
        for item in generated:
            item = _validate_type(item)
            item = _fix_mc_exercise(item) if item else None
            item = _fix_fill_blank_exercise(item) if item else None
            item = _fix_letter_tiles_exercise(item) if item else None
            item = _fix_order_words_exercise(item) if item else None
            item = _fix_flashcard_exercise(item) if item else None
            item = _fix_translate_exercise(item) if item else None
            item = _fix_judge_sentence_exercise(item) if item else None
            item = _fix_word_definition_exercise(item) if item else None
            if item is None:
                continue
            item = _sanitize_native_fields(item, user.native_language)
            item = _clean_word_hints(item)
            item = _require_word_hints(item)
            if item is None:
                continue
            if _norm(item.get("question", "")) in seen_qs:
                continue
            validated.append(item)
        # Save ALL valid exercises to pool (populates shared pool regardless of deficit)
        for item in validated:
            topic_id = topic_id_by_slug.get(item.get("topic_slug"))
            _save_to_pool(item, user.level, topic_id, db)
        # Add only up to deficit exercises to today's DailyExercise
        ai_added = 0
        for item in validated:
            if ai_added >= deficit:
                break
            topic_id = topic_id_by_slug.get(item.get("topic_slug"))
            pool_id = _save_to_pool(item, user.level, topic_id, db)
            entries.append(models.DailyExercise(
                user_id=user.id, date=today,
                exercise_type=item.get("type", "fill_blank"),
                content=json.dumps(item, ensure_ascii=False),
                source="new",
                content_type=item.get("content_type"),
                topic_id=topic_id,
                pool_exercise_id=pool_id,
            ))
            ai_added += 1
    else:
        # Still generate topic_d exercises even if pool was sufficient
        topic_d_entries = await _generate_topic_exercises_for_daily(user, db, today)

    entries.extend(topic_d_entries)

    for entry in entries:
        db.add(entry)
    db.commit()


async def _generate_bonus_pool(user, db: Session, today, count: int):
    prefs = user.content_preferences

    # Drill known idioms before generating the main bonus batch
    await _generate_idiom_drill_exercises(user, db, today, source="bonus")

    interest_themes_str = _select_interest_themes(prefs)  # max 2 themes, even rotation

    challenge_level = _next_level(user.level)
    gen_topics = _select_topics_for_generation(user, db)
    topic_id_by_slug = {t.slug: t.id for t in gen_topics}

    # Pool-first: serve unseen bonus exercises from shared pool at challenge level
    pool_drawn = _pool_draw(db, user.id, challenge_level, count, seen_norms=_seen_questions(user.id, db, limit=150))
    pool_added = 0
    for pool_ex in pool_drawn:
        if pool_added >= count:
            break
        try:
            json.loads(pool_ex.content)  # validate JSON
        except Exception:
            continue
        pool_ex.use_count = (pool_ex.use_count or 0) + 1
        db.add(models.DailyExercise(
            user_id=user.id, date=today,
            exercise_type=pool_ex.exercise_type,
            content=pool_ex.content,
            source="bonus",
            content_type=pool_ex.content_type,
            topic_id=pool_ex.topic_id,
            pool_exercise_id=pool_ex.id,
        ))
        pool_added += 1

    deficit = count - pool_added
    print(f"[bonus_pool] user={user.id} level={challenge_level} count={count} pool={pool_added} deficit={deficit}")

    if deficit > 0:
        generated = await _generate_exercises(user, deficit, interest_themes_str, level=challenge_level, topics=gen_topics or None)
        seen_qs = _seen_questions(user.id, db)
        validated = []
        for item in generated:
            item = _validate_type(item)
            item = _fix_mc_exercise(item) if item else None
            item = _fix_fill_blank_exercise(item) if item else None
            item = _fix_letter_tiles_exercise(item) if item else None
            item = _fix_order_words_exercise(item) if item else None
            item = _fix_flashcard_exercise(item) if item else None
            item = _fix_translate_exercise(item) if item else None
            item = _fix_judge_sentence_exercise(item) if item else None
            item = _fix_word_definition_exercise(item) if item else None
            if item is None:
                continue
            item = _sanitize_native_fields(item, user.native_language)
            item = _clean_word_hints(item)
            item = _require_word_hints(item)
            if item is None:
                continue
            if _norm(item.get("question", "")) in seen_qs:
                continue
            validated.append(item)
        # Save ALL valid exercises to pool (populates shared pool regardless of deficit)
        for item in validated:
            topic_id = topic_id_by_slug.get(item.get("topic_slug"))
            _save_to_pool(item, challenge_level, topic_id, db)
        # Add only up to deficit exercises to today's DailyExercise
        added = 0
        for item in validated:
            if added >= deficit:
                break
            topic_id = topic_id_by_slug.get(item.get("topic_slug"))
            pool_id = _save_to_pool(item, challenge_level, topic_id, db)
            db.add(models.DailyExercise(
                user_id=user.id, date=today,
                exercise_type=item.get("type", "fill_blank"),
                content=json.dumps(item, ensure_ascii=False),
                source="bonus",
                content_type=item.get("content_type"),
                topic_id=topic_id,
                pool_exercise_id=pool_id,
            ))
            added += 1

    db.commit()
