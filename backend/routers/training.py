import asyncio
import json
import re
import random
import hashlib
from collections import Counter
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from auth import get_current_user
import models
import schemas
import prompts
from services import mistral
from services.i18n import lang_name
from services.sm2 import calculate_next_review
from services.gamification import (
    add_xp, XP_CORRECT, XP_INCORRECT, XP_VOCAB, XP_VOCAB_NEW, XP_VOCAB_REVIEW, XP_COMPLETE_SESSION,
    check_achievements, update_daily_activity, update_streak
)


# Pure validators and generation helpers were extracted to services/ (the 2700-line
# monolith hid a shadowed-duplicate-function bug once). Names are re-imported here so
# call sites, CLAUDE.md test snippets and `from routers.training import X` keep working.
from services.validators import (
    _strip, _norm, _validate_type, _sanitize_native_fields, _stem_match,
    _clean_word_hints, _require_word_hints, _check_modal_has_infinitive,
    _fix_flashcard_exercise, _fix_mc_exercise, _fix_fill_blank_exercise,
    _fix_letter_tiles_exercise, _fix_translate_exercise, _fix_judge_sentence_exercise,
    _fix_order_words_exercise, _fix_word_definition_exercise,
    _check_answer, _same_word_multiset, _VALID_EXERCISE_TYPES,
)
from services.generation import (
    _LEVEL_ORDER, _eligible_vocab_levels, _VOCAB_TILES_GRADUATE, _vocab_card_content,
    _next_level, _build_avoid_block, _save_to_pool, _pool_draw, _seen_questions,
    _build_known_vocab_block, _difficulty_hint, _mastered_exercise_ids,
    _generate_idiom_drill_exercises, _ensure_vocab_pool, _select_interest_themes,
    _select_topics_for_generation, _generate_exercises, _generate_topic_pool,
    _generate_topic_exercises_for_daily, _generate_daily_pool, _generate_bonus_pool,
    _generate_reading,
)

router = APIRouter(prefix="/training", tags=["training"])


def _session_length_count(prefs) -> int:
    if not prefs:
        return 20
    mapping = {"short": 10, "standard": 20, "long": 25}
    return mapping.get(prefs.session_length, 20)


@router.get("/session")
async def get_training_session(
    mode: str = "daily",
    topic: str = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    prefs = current_user.content_preferences
    count = _session_length_count(prefs)
    today = date.today()

    # Preload topics for enriching exercises that lack topic_title
    _topics_by_id = {t.id: t for t in db.query(models.Topic).all()}

    def _enrich(content: dict, de) -> dict:
        """Add topic_title/topic_slug from DE.topic_id if not already in content."""
        if not content.get("topic_title") and getattr(de, "topic_id", None):
            t = _topics_by_id.get(de.topic_id)
            if t:
                content["topic_title"] = t.title_ru
                content["topic_slug"] = t.slug
        return content

    exercises = []

    if mode == "errors":
        # Subquery: timestamp of the most recent attempt per exercise
        latest_sq = (
            db.query(
                models.UserExerciseHistory.exercise_id,
                func.max(models.UserExerciseHistory.created_at).label("last_at"),
            )
            .filter(
                models.UserExerciseHistory.user_id == current_user.id,
                models.UserExerciseHistory.exercise_id.isnot(None),
            )
            .group_by(models.UserExerciseHistory.exercise_id)
            .subquery()
        )
        # Only exercises where the most recent attempt was wrong, excluding flagged ones
        history = (
            db.query(models.UserExerciseHistory)
            .join(
                latest_sq,
                (models.UserExerciseHistory.exercise_id == latest_sq.c.exercise_id)
                & (models.UserExerciseHistory.created_at == latest_sq.c.last_at),
            )
            .join(models.Exercise, models.UserExerciseHistory.exercise_id == models.Exercise.id)
            .filter(
                models.UserExerciseHistory.user_id == current_user.id,
                models.UserExerciseHistory.is_correct == False,
                models.Exercise.is_flagged == False,
            )
            .order_by(func.random())
            .limit(count)
            .all()
        )

        for h in history:
            if h.exercise:
                ex = h.exercise
                opts = None
                if ex.options:
                    try:
                        opts = json.loads(ex.options)
                    except Exception:
                        pass
                exercises.append({
                    "id": ex.id,
                    "type": ex.type,
                    "question": ex.question,
                    "correct_answer": ex.correct_answer,
                    "options": opts,
                    "hint": ex.hint,
                    "explanation": ex.explanation,
                    "source": "error",
                })

        # Also include AI-generated exercises answered wrong (last 14 days only, skip NULL-dated legacy entries)
        remaining = count - len(exercises)
        if remaining > 0:
            cutoff = datetime.utcnow() - timedelta(days=14)
            ai_errors = (
                db.query(models.DailyExercise)
                .filter(
                    models.DailyExercise.user_id == current_user.id,
                    models.DailyExercise.is_completed == True,
                    models.DailyExercise.is_correct == False,
                    models.DailyExercise.source.in_(["bonus", "new", "topic", "topic_d", "review_ai"]),  # review_ai wrongs must not vanish
                    ~models.DailyExercise.content.contains('"is_error_retry"'),  # copies served in daily/bonus don't double the original
                    models.DailyExercise.completed_at.isnot(None),
                    models.DailyExercise.completed_at >= cutoff,
                )
                .order_by(func.random())
                .limit(remaining)
                .all()
            )
            for de in ai_errors:
                try:
                    content = json.loads(de.content)
                    content["daily_exercise_id"] = de.id
                    content["source"] = "error_ai"
                    _enrich(content, de)
                    exercises.append(content)
                except Exception:
                    pass

        # Vocab words answered wrong (correct_streak=0) — appear as flashcard errors
        vocab_remaining = max(0, count - len(exercises))
        vocab_errors = (
            db.query(models.UserVocabulary, models.Vocabulary)
            .join(models.Vocabulary, models.UserVocabulary.vocab_id == models.Vocabulary.id)
            .filter(
                models.UserVocabulary.user_id == current_user.id,
                models.UserVocabulary.correct_streak == 0,
                # Only genuinely-wrong words (practiced at least once), NOT freshly added
                # via learn-word/auto-add, which also have correct_streak=0 but were never answered.
                models.UserVocabulary.last_reviewed.isnot(None),
            )
            .limit(vocab_remaining)
            .all()
        )
        for uv, vocab in vocab_errors:
            exercises.append({
                "type": "flashcard",
                "question": vocab.polish,
                "correct_answer": getattr(vocab, f"translation_{current_user.native_language}", vocab.translation_en),
                "hint": vocab.example_sentence or "",
                "source": "error_vocab",
                "vocab_id": vocab.id,
                "id": None,
                "daily_exercise_id": None,
            })

    elif mode == "new":
        # First try uncompleted AI exercises from today's daily pool
        daily_new = db.query(models.DailyExercise).filter(
            models.DailyExercise.user_id == current_user.id,
            models.DailyExercise.date == today,
            models.DailyExercise.source == "new",
            models.DailyExercise.is_completed == False,
        ).limit(count).all()

        if not daily_new:
            # Daily pool exhausted — reuse existing uncompleted bonus exercises or generate new ones
            uncompleted_bonus = db.query(models.DailyExercise).filter(
                models.DailyExercise.user_id == current_user.id,
                models.DailyExercise.date == today,
                models.DailyExercise.source == "bonus",
                models.DailyExercise.is_completed == False,
            ).count()
            if uncompleted_bonus == 0:
                await _generate_bonus_pool(current_user, db, today, count)
            daily_new = db.query(models.DailyExercise).filter(
                models.DailyExercise.user_id == current_user.id,
                models.DailyExercise.date == today,
                models.DailyExercise.source == "bonus",
                models.DailyExercise.is_completed == False,
            ).limit(count).all()

        for de in daily_new:
            try:
                content = json.loads(de.content)
                content["daily_exercise_id"] = de.id
                content["source"] = "new"
                if content.get("is_error_retry"):
                    content["source"] = "error_ai"  # error-work badge inside the general mix
                _enrich(content, de)
                exercises.append(content)
            except Exception:
                pass

    elif mode == "bonus":
        # Resume existing uncompleted bonus exercises if they exist (e.g. after a page refresh).
        # Only generate a new batch when there's nothing left to do.
        uncompleted_count = db.query(models.DailyExercise).filter(
            models.DailyExercise.user_id == current_user.id,
            models.DailyExercise.date == today,
            models.DailyExercise.source == "bonus",
            models.DailyExercise.is_completed == False,
        ).count()

        if uncompleted_count == 0:
            await _generate_bonus_pool(current_user, db, today, count)

        daily = db.query(models.DailyExercise).filter(
            models.DailyExercise.user_id == current_user.id,
            models.DailyExercise.date == today,
            models.DailyExercise.source == "bonus",
            models.DailyExercise.is_completed == False,
        ).limit(count).all()

        for de in daily:
            try:
                content = json.loads(de.content)
                content["daily_exercise_id"] = de.id
                content["source"] = "bonus"
                if content.get("is_error_retry"):
                    content["source"] = "error_ai"  # error-work badge inside the general mix
                _enrich(content, de)
                exercises.append(content)
            except Exception:
                pass

        # NO curriculum top-up here. The old "Fallback to DB" block padded every resumed
        # bonus tail with exercises from the ~50-row curriculum table: its seen-filter read
        # 200 UNORDERED history rows (= the oldest), everything counted as unseen was not,
        # and the "allow repeats" branch then cycled the SAME first-N exercises of the level
        # forever — 'буква ц' was answered 20 times, 'Widzę ten pies' 15 (feedback #141-144).
        # A shorter session is strictly better than eternal reruns; real deficits are already
        # topped up from the shared pool inside _generate_bonus_pool.

    elif mode == "vocab":
        # Resume today's uncompleted vocab session if it exists
        uncompleted_today = db.query(models.DailyExercise).filter(
            models.DailyExercise.user_id == current_user.id,
            models.DailyExercise.date == today,
            models.DailyExercise.source == "vocab",
            models.DailyExercise.is_completed == False,
        ).all()

        if uncompleted_today:
            for de in uncompleted_today:
                try:
                    content = json.loads(de.content)
                    content["daily_exercise_id"] = de.id
                    content["source"] = "vocab"
                    _enrich(content, de)
                    exercises.append(content)
                except Exception:
                    pass
        else:
            # Build new vocab session: wrong → review → new
            eligible_levels = _eligible_vocab_levels(current_user.level)
            all_uvs = {
                uv.vocab_id: uv
                for uv in db.query(models.UserVocabulary).filter(
                    models.UserVocabulary.user_id == current_user.id
                ).all()
            }
            seen_ids = set(all_uvs.keys())

            # Exclude words correctly answered in today's vocab sessions (avoid same-day repeats)
            correctly_done_today = set()
            for de in db.query(models.DailyExercise).filter(
                models.DailyExercise.user_id == current_user.id,
                models.DailyExercise.date == today,
                models.DailyExercise.source == "vocab",
                models.DailyExercise.is_correct == True,
            ).all():
                try:
                    c = json.loads(de.content)
                    if c.get("vocab_id"):
                        correctly_done_today.add(c["vocab_id"])
                except Exception:
                    pass

            # correct_streak==0 splits two ways by whether the word was ever practiced:
            #   last_reviewed set    → genuinely answered wrong → "error" bucket
            #   last_reviewed null   → freshly added (learn-word/auto-add), never answered → "new" bucket
            wrong_ids = {vid for vid, uv in all_uvs.items()
                         if uv.correct_streak == 0 and uv.last_reviewed is not None
                         and vid not in correctly_done_today}
            learn_ids = {vid for vid, uv in all_uvs.items()
                         if uv.correct_streak == 0 and uv.last_reviewed is None
                         and vid not in correctly_done_today}
            due_ids = {
                vid for vid, uv in all_uvs.items()
                if uv.correct_streak >= 1 and uv.next_review and uv.next_review <= today
                and vid not in correctly_done_today
            }

            # If new words at eligible levels are running low, generate more before building session
            new_available = db.query(models.Vocabulary).filter(
                models.Vocabulary.level.in_(eligible_levels),
                models.Vocabulary.id.notin_(seen_ids) if seen_ids else True,
            ).count()
            if new_available < 10:
                await _ensure_vocab_pool(current_user, db)

            vocab_to_show = []
            vocab_status = {}  # vocab_id → "error" | "review" | "new"

            # Cap reviews at 60% of session, always leave at least 30% for new words
            max_review_slots = int(count * 0.6)
            min_new_slots = max(1, int(count * 0.3))

            if wrong_ids:
                wrong_words = db.query(models.Vocabulary).filter(
                    models.Vocabulary.id.in_(wrong_ids),
                    models.Vocabulary.level.in_(eligible_levels),
                ).limit(min(len(wrong_ids), max_review_slots // 2 + 1)).all()
                for w in wrong_words:
                    vocab_status[w.id] = "error"
                vocab_to_show += wrong_words

            review_slots_left = max_review_slots - len(vocab_to_show)
            if review_slots_left > 0 and due_ids:
                review_words = db.query(models.Vocabulary).filter(
                    models.Vocabulary.id.in_(due_ids),
                    models.Vocabulary.level.in_(eligible_levels),
                ).limit(review_slots_left).all()
                for w in review_words:
                    vocab_status[w.id] = "review"
                vocab_to_show += review_words

            new_slots = max(min_new_slots, count - len(vocab_to_show))
            new_words = []
            # Words the user explicitly clicked to learn (correct_streak=0, never practiced) come first
            if learn_ids:
                learn_words = db.query(models.Vocabulary).filter(
                    models.Vocabulary.id.in_(learn_ids),
                    models.Vocabulary.level.in_(eligible_levels),
                ).limit(new_slots).all()
                new_words += learn_words
            # Fill remaining slots with genuinely-unseen dictionary words
            if len(new_words) < new_slots:
                fresh = db.query(models.Vocabulary).filter(
                    models.Vocabulary.level.in_(eligible_levels),
                    models.Vocabulary.id.notin_(seen_ids) if seen_ids else True,
                ).limit(new_slots - len(new_words)).all()
                new_words += fresh
            for w in new_words:
                vocab_status[w.id] = "new"
            vocab_to_show += new_words

            if not vocab_to_show:
                return {"exercises": [], "mode": "vocab", "total": 0, "all_vocab_done": True, "daily_done": False}

            for v in vocab_to_show:
                uv = all_uvs.get(v.id)
                streak = uv.correct_streak if uv else 0
                status = vocab_status.get(v.id, "new")
                content_dict = _vocab_card_content(v, status, current_user.native_language, streak)
                de = models.DailyExercise(
                    user_id=current_user.id,
                    date=today,
                    exercise_type=content_dict["type"],
                    content=json.dumps(content_dict, ensure_ascii=False),
                    source="vocab",
                )
                db.add(de)
                db.flush()
                content_dict["daily_exercise_id"] = de.id
                content_dict["source"] = "vocab"
                exercises.append(content_dict)

            db.commit()

    elif mode == "topic":
        if not topic:
            raise HTTPException(status_code=400, detail="topic slug required for mode=topic")
        topic_obj = db.query(models.Topic).filter(models.Topic.slug == topic).first()
        if not topic_obj:
            raise HTTPException(status_code=404, detail="Topic not found")

        # Theme training (#101): a session for ONE topic mixing the learner's mistakes on
        # it, items to consolidate, and fresh exercises. No mistakes → more new material.
        used_de_ids = set()

        # 1) Mistakes on this topic — wrong and not yet fixed (highest priority)
        topic_errors = db.query(models.DailyExercise).filter(
            models.DailyExercise.user_id == current_user.id,
            models.DailyExercise.topic_id == topic_obj.id,
            models.DailyExercise.is_completed == True,
            models.DailyExercise.is_correct == False,
            models.DailyExercise.source.in_(["topic", "topic_d", "new", "bonus"]),
            models.DailyExercise.completed_at.isnot(None),
        ).order_by(func.random()).limit(count).all()
        for de in topic_errors:
            try:
                content = json.loads(de.content)
                content["daily_exercise_id"] = de.id
                content["source"] = "error"
                _enrich(content, de)
                exercises.append(content)
                used_de_ids.add(de.id)
            except Exception:
                pass

        # 2) Consolidation — correctly answered on this topic (capped so "new" dominates
        #    when there are few/no mistakes)
        review_cap = max(0, (count - len(exercises)) // 3)
        if review_cap > 0:
            topic_reviews = db.query(models.DailyExercise).filter(
                models.DailyExercise.user_id == current_user.id,
                models.DailyExercise.topic_id == topic_obj.id,
                models.DailyExercise.is_completed == True,
                models.DailyExercise.is_correct == True,
                models.DailyExercise.source.in_(["topic", "topic_d", "new", "bonus", "review_ai"]),
            ).order_by(func.random()).limit(review_cap).all()
            for de in topic_reviews:
                if de.id in used_de_ids:
                    continue
                try:
                    content = json.loads(de.content)
                    content["daily_exercise_id"] = de.id
                    content["source"] = "review"
                    _enrich(content, de)
                    exercises.append(content)
                    used_de_ids.add(de.id)
                except Exception:
                    pass

        # 3) New — generate fresh topic exercises to fill the rest of the session
        remaining = count - len(exercises)
        if remaining > 0:
            uncompleted = db.query(models.DailyExercise).filter(
                models.DailyExercise.user_id == current_user.id,
                models.DailyExercise.date == today,
                models.DailyExercise.source == "topic",
                models.DailyExercise.topic_id == topic_obj.id,
                models.DailyExercise.is_completed == False,
            ).count()
            if uncompleted < remaining:
                await _generate_topic_pool(current_user, topic_obj, db, today, remaining)
            topic_new = db.query(models.DailyExercise).filter(
                models.DailyExercise.user_id == current_user.id,
                models.DailyExercise.date == today,
                models.DailyExercise.source == "topic",
                models.DailyExercise.topic_id == topic_obj.id,
                models.DailyExercise.is_completed == False,
            ).limit(remaining).all()
            for de in topic_new:
                if de.id in used_de_ids:
                    continue
                try:
                    content = json.loads(de.content)
                    content["daily_exercise_id"] = de.id
                    content["source"] = de.source
                    if content.get("is_error_retry"):
                        content["source"] = "error_ai"
                    _enrich(content, de)
                    exercises.append(content)
                    used_de_ids.add(de.id)
                except Exception:
                    pass

        random.shuffle(exercises)

    elif mode == "reading":
        # Reading comprehension: one passage + questions, scored as a unit.
        uncompleted = db.query(models.DailyExercise).filter(
            models.DailyExercise.user_id == current_user.id,
            models.DailyExercise.date == today,
            models.DailyExercise.source == "reading",
            models.DailyExercise.is_completed == False,
        ).count()
        if uncompleted == 0:
            await _generate_reading(current_user, db, today)
        reading_de = db.query(models.DailyExercise).filter(
            models.DailyExercise.user_id == current_user.id,
            models.DailyExercise.date == today,
            models.DailyExercise.source == "reading",
            models.DailyExercise.is_completed == False,
        ).order_by(models.DailyExercise.id.desc()).first()
        if reading_de:
            try:
                content = json.loads(reading_de.content)
                content["daily_exercise_id"] = reading_de.id
                content["source"] = "reading"
                exercises.append(content)
            except Exception:
                pass

    elif mode == "practice":
        # SRS review queue (user decision 2026-07-12): serve ONLY exercises whose
        # next_review is due, oldest first — the queue visibly SHRINKS as you work it,
        # exactly like the errors list, and refills on schedule. The old mode was a
        # bottomless random mix of everything done in 60 days ("никогда не уменьшается").
        due = db.query(models.DailyExercise).filter(
            models.DailyExercise.user_id == current_user.id,
            models.DailyExercise.is_completed == True,
            models.DailyExercise.is_correct == True,
            models.DailyExercise.next_review.isnot(None),
            models.DailyExercise.next_review <= today,
            models.DailyExercise.source.in_(["new", "bonus", "review_ai", "topic_d"]),
        ).order_by(models.DailyExercise.next_review).limit(count).all()

        for de in due:
            try:
                content = json.loads(de.content)
                content["daily_exercise_id"] = de.id
                content["source"] = "practice"
                _enrich(content, de)
                exercises.append(content)
            except Exception:
                pass
        random.shuffle(exercises)

    else:
        # Daily mode: exclude bonus, vocab, topic, and practice DailyExercises
        _daily_sources_excl = ["bonus", "vocab", "topic", "practice"]
        existing = db.query(models.DailyExercise).filter(
            models.DailyExercise.user_id == current_user.id,
            models.DailyExercise.date == today,
            models.DailyExercise.source.notin_(_daily_sources_excl),
        ).count()

        if existing == 0:
            await _generate_daily_pool(current_user, db, today, count)

        done_count = db.query(models.DailyExercise).filter(
            models.DailyExercise.user_id == current_user.id,
            models.DailyExercise.date == today,
            models.DailyExercise.source.notin_(_daily_sources_excl),
            models.DailyExercise.is_completed == True,
        ).count()
        total_count = db.query(models.DailyExercise).filter(
            models.DailyExercise.user_id == current_user.id,
            models.DailyExercise.date == today,
            models.DailyExercise.source.notin_(_daily_sources_excl),
        ).count()

        if total_count > 0 and done_count >= total_count:
            return {"exercises": [], "mode": "daily", "total": 0, "daily_done": True}

        daily = db.query(models.DailyExercise).filter(
            models.DailyExercise.user_id == current_user.id,
            models.DailyExercise.date == today,
            models.DailyExercise.source.notin_(_daily_sources_excl),
            models.DailyExercise.is_completed == False,
        ).limit(count).all()

        for de in daily:
            try:
                content = json.loads(de.content)
                content["daily_exercise_id"] = de.id
                content["source"] = de.source
                if content.get("is_error_retry"):
                    content["source"] = "error_ai"
                _enrich(content, de)
                exercises.append(content)
            except Exception:
                pass

    random.shuffle(exercises)
    for ex in exercises:
        if ex.get("options") and isinstance(ex["options"], list):
            random.shuffle(ex["options"])
    return {"exercises": exercises, "mode": mode, "total": len(exercises), "daily_done": False}


@router.post("/answer", response_model=schemas.AnswerResponse)
async def submit_answer(
    body: schemas.AnswerRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    is_correct = False
    diacritic_hint = False
    correct_answer = ""
    explanation = None
    _vocab_mode = "normal"  # "zero" = no XP (know/don't know), "reduced" = XP_VOCAB
    _reading_mode = False   # reading comprehension: XP scaled by correct answers
    _reading_correct = 0

    if body.daily_exercise_id:
        de = db.query(models.DailyExercise).filter(
            models.DailyExercise.id == body.daily_exercise_id,
            models.DailyExercise.user_id == current_user.id,
        ).first()
        if de:
            try:
                content = json.loads(de.content)
                correct_answer = content.get("correct_answer", "")
                raw_expl = content.get("explanation")
                explanation = raw_expl if isinstance(raw_expl, str) else None
                ex_type = content.get("type", "")

                if ex_type == "reading":
                    _reading_mode = True
                    # user_answer is a JSON list of chosen option strings, one per question
                    try:
                        chosen = json.loads(body.user_answer)
                    except Exception:
                        chosen = []
                    questions = content.get("questions", []) or []
                    _reading_total = len(questions)
                    for i, q in enumerate(questions):
                        ans = str(q.get("correct_answer", "")).strip()
                        if i < len(chosen) and _norm(str(chosen[i])) == _norm(ans):
                            _reading_correct += 1
                    is_correct = _reading_total > 0 and _reading_correct == _reading_total
                    correct_answer = ""  # not a single-answer exercise
                elif ex_type == "translate":
                    is_correct, diacritic_hint = _check_answer(body.user_answer, correct_answer)
                    if not is_correct:
                        is_correct = await _check_translation(
                            body.user_answer, correct_answer,
                            content.get("question", ""),
                            current_user,
                            focus=content.get("topic_title") or content.get("hint") or "",
                        )
                else:
                    is_correct, diacritic_hint = _check_answer(body.user_answer, correct_answer)
                    # order_words: Polish word order is largely free — if the user used
                    # exactly the same words in a different order, let Mistral judge it
                    if not is_correct and ex_type == "order_words":
                        ref = correct_answer.split(' / ')[0].strip()
                        if _same_word_multiset(body.user_answer, ref):
                            is_correct = await _check_word_order(
                                body.user_answer, ref,
                                content.get("translation", ""), current_user
                            )

                de.is_completed = True
                de.is_correct = is_correct
                de.user_answer = body.user_answer
                de.completed_at = datetime.utcnow()

                # XP mode for vocab cards (flashcard OR letter_tiles tied to a vocab word)
                if de.source == "vocab":
                    _vocab_mode = "vocab_session"  # vocab session — small XP
                elif ex_type in ("flashcard", "letter_tiles") and content.get("vocab_id"):
                    _vocab_mode = "reduced"   # SRS vocab in daily review — easier than exercises

                # SRS scheduling for AI exercises (user decision 2026-07-12: «Повторение»
                # works like the errors list — a real SRS queue). Every correct answer is
                # scheduled; the queue is drained by mode=practice (full sessions of due
                # items, oldest first), not by a 3/day trickle, so it shrinks visibly.
                # A repeat pass through practice re-answers the SAME row → intervals grow
                # 1d → 6d → exponentially, so mature items leave the daily flow.
                if de.source in ("new", "bonus", "review_ai", "topic_d"):
                    if is_correct:
                        quality = 3 if diacritic_hint else 5
                        _, new_interval, new_reps, next_rev = calculate_next_review(
                            2.5,
                            max(1, de.srs_interval_days or 1),
                            de.srs_repetitions or 0,
                            quality,
                        )
                        de.srs_interval_days = new_interval
                        de.srs_repetitions = new_reps
                        de.next_review = next_rev
                    else:
                        de.srs_interval_days = 0
                        de.srs_repetitions = 0
                        de.next_review = None

                # When answered correctly, clear all duplicate entries with the same question
                if is_correct:
                    question_text = content.get("question", "")
                    if question_text:
                        dupes = db.query(models.DailyExercise).filter(
                            models.DailyExercise.user_id == current_user.id,
                            models.DailyExercise.id != de.id,
                            models.DailyExercise.is_correct == False,
                        ).all()
                        for dupe in dupes:
                            try:
                                dupe_content = json.loads(dupe.content)
                                if dupe_content.get("question", "") == question_text:
                                    dupe.is_correct = True
                                    dupe.is_completed = True
                            except Exception:
                                pass

                # For topic-tagged exercises, update UserTopicProgress
                if de.source in ("topic", "topic_d", "new", "bonus") and de.topic_id:
                    prog = db.query(models.UserTopicProgress).filter(
                        models.UserTopicProgress.user_id == current_user.id,
                        models.UserTopicProgress.topic_id == de.topic_id,
                    ).first()
                    if not prog:
                        prog = models.UserTopicProgress(
                            user_id=current_user.id,
                            topic_id=de.topic_id,
                            status="in_progress",
                            score=0.0,
                            attempts=0,
                        )
                        db.add(prog)
                        db.flush()
                    old_score = prog.score or 0.0
                    old_att = prog.attempts or 0
                    # EMA (~last 20 answers dominate) instead of a lifetime average: at 300
                    # attempts one answer moved the score by 1/301 — 'alphabet' froze at 0.67
                    # forever and kept being picked as weak (feedback #138)
                    alpha = max(1.0 / (old_att + 1), 1.0 / 20.0)
                    prog.score = old_score + alpha * ((1.0 if is_correct else 0.0) - old_score)
                    prog.attempts = old_att + 1
                    # Require meaningful practice before marking done:
                    # new/bonus = incidental exposure, needs many reps; topic/topic_d = dedicated practice
                    min_att = 9 if de.source in ("new", "bonus") else 5
                    if prog.score >= 0.75 and old_att >= min_att:
                        prog.status = "done"
                    elif prog.score < 0.6:
                        prog.status = "needs_review"

                # For curriculum exercises (source=weak), track history + topic progress
                curriculum_ex_id = content.get("id")
                if curriculum_ex_id and de.source == "weak":
                    cur_ex = db.query(models.Exercise).filter(
                        models.Exercise.id == curriculum_ex_id
                    ).first()
                    if cur_ex:
                        if cur_ex.topic_id:
                            prog = db.query(models.UserTopicProgress).filter(
                                models.UserTopicProgress.user_id == current_user.id,
                                models.UserTopicProgress.topic_id == cur_ex.topic_id,
                            ).first()
                            if prog:
                                old_score = prog.score or 0.0
                                old_att = prog.attempts or 0
                                alpha = max(1.0 / (old_att + 1), 1.0 / 20.0)  # EMA, see comment above
                                prog.score = old_score + alpha * ((1.0 if is_correct else 0.0) - old_score)
                                prog.attempts = old_att + 1
                                if prog.score >= 0.75 and prog.attempts >= 5:
                                    prog.status = "done"
                                elif prog.score < 0.6:
                                    prog.status = "needs_review"
                        c_hash = hashlib.md5(cur_ex.question.encode()).hexdigest()[:8]
                        db.add(models.UserExerciseHistory(
                            user_id=current_user.id,
                            exercise_id=curriculum_ex_id,
                            is_correct=is_correct,
                            user_answer=body.user_answer,
                            time_spent_sec=body.time_spent_sec,
                            content_hash=c_hash,
                        ))

                # Update SRS for vocabulary cards (flashcard OR letter_tiles tied to a vocab word)
                if ex_type in ("flashcard", "letter_tiles") and content.get("vocab_id"):
                    uv = db.query(models.UserVocabulary).filter(
                        models.UserVocabulary.user_id == current_user.id,
                        models.UserVocabulary.vocab_id == content["vocab_id"],
                    ).first()
                    if not uv:
                        uv = models.UserVocabulary(
                            user_id=current_user.id,
                            vocab_id=content["vocab_id"],
                        )
                        db.add(uv)
                        db.flush()
                    quality = body.quality if body.quality is not None else (5 if is_correct else 0)
                    new_ef, new_interval, new_reps, next_rev = calculate_next_review(
                        uv.ease_factor or 2.5, uv.interval_days or 1,
                        uv.repetitions or 0, quality,
                    )
                    uv.ease_factor = new_ef
                    uv.interval_days = new_interval
                    uv.repetitions = new_reps
                    uv.next_review = next_rev
                    uv.last_reviewed = datetime.utcnow()  # marks word as practiced (distinguishes wrong from never-seen)
                    # Use quality for streak — handles reverse-direction flashcards correctly
                    streak_correct = quality >= 3
                    uv.correct_streak = (uv.correct_streak or 0) + 1 if streak_correct else 0
                    is_correct = streak_correct

                # For ALL flashcards: trust client quality — client knows direction and
                # uses lenient isClose() matching; server _check_answer is too strict for idioms
                if ex_type == "flashcard" and body.quality is not None:
                    is_correct = body.quality >= 3
                    de.is_correct = is_correct

                # Track idioms/expressions the user knows for later drill exercises
                if ex_type == "flashcard" and not content.get("vocab_id") and (body.quality or 0) >= 4:
                    expr = content.get("question", "").strip()
                    if expr:
                        exists = db.query(models.UserKnownExpression).filter(
                            models.UserKnownExpression.user_id == current_user.id,
                            models.UserKnownExpression.expression == expr,
                        ).first()
                        if not exists:
                            db.add(models.UserKnownExpression(
                                user_id=current_user.id,
                                expression=expr,
                                meaning=(content.get("correct_answer") or content.get("translation") or "").strip(),
                            ))

                db.commit()
            except Exception:
                is_correct = False

    elif body.vocab_id:
        # Vocab flashcard with no daily_exercise_id — e.g. vocab errors in errors mode
        _vocab_mode = "reduced"
        vocab = db.query(models.Vocabulary).filter(models.Vocabulary.id == body.vocab_id).first()
        if vocab:
            lang = current_user.native_language
            correct_answer = getattr(vocab, f"translation_{lang}", vocab.translation_en)
            # Trust quality sent by client (client checks both forward/reverse directions)
            quality = body.quality if body.quality is not None else (5 if body.user_answer.strip() else 0)
            is_correct = quality >= 3
            uv = db.query(models.UserVocabulary).filter(
                models.UserVocabulary.user_id == current_user.id,
                models.UserVocabulary.vocab_id == body.vocab_id,
            ).first()
            if not uv:
                uv = models.UserVocabulary(user_id=current_user.id, vocab_id=body.vocab_id)
                db.add(uv)
                db.flush()
            new_ef, new_interval, new_reps, next_rev = calculate_next_review(
                uv.ease_factor or 2.5, uv.interval_days or 1,
                uv.repetitions or 0, quality,
            )
            uv.ease_factor = new_ef
            uv.interval_days = new_interval
            uv.repetitions = new_reps
            uv.next_review = next_rev
            uv.last_reviewed = datetime.utcnow()  # marks word as practiced
            uv.correct_streak = (uv.correct_streak or 0) + 1 if is_correct else 0
            db.commit()

    elif body.exercise_id:
        exercise = db.query(models.Exercise).filter(models.Exercise.id == body.exercise_id).first()
        if not exercise:
            raise HTTPException(status_code=404, detail="Exercise not found")

        correct_answer = exercise.correct_answer
        explanation = exercise.explanation

        if exercise.type == "translate":
            is_correct, diacritic_hint = _check_answer(body.user_answer, correct_answer)
            if not is_correct:
                is_correct = await _check_translation(
                    body.user_answer, correct_answer,
                    exercise.question, current_user,
                    focus=exercise.hint or "",
                )
        else:
            is_correct, diacritic_hint = _check_answer(body.user_answer, correct_answer)
            if not is_correct and exercise.type == "order_words":
                ref = correct_answer.split(' / ')[0].strip()
                if _same_word_multiset(body.user_answer, ref):
                    is_correct = await _check_word_order(
                        body.user_answer, ref, "", current_user
                    )

        if exercise.topic_id:
            progress = db.query(models.UserTopicProgress).filter(
                models.UserTopicProgress.user_id == current_user.id,
                models.UserTopicProgress.topic_id == exercise.topic_id,
            ).first()
            if progress:
                old_score = progress.score or 0.0
                old_attempts = progress.attempts or 0
                result = 1.0 if is_correct else 0.0
                alpha = max(1.0 / (old_attempts + 1), 1.0 / 20.0)  # EMA, see comment above
                progress.score = old_score + alpha * (result - old_score)
                progress.attempts = old_attempts + 1
                if progress.score >= 0.75 and progress.attempts >= 6:
                    progress.status = "done"
                elif progress.score < 0.6:
                    progress.status = "needs_review"
                db.commit()

        content_hash = hashlib.md5(exercise.question.encode()).hexdigest()[:8]
        history = models.UserExerciseHistory(
            user_id=current_user.id,
            exercise_id=exercise.id,
            is_correct=is_correct,
            user_answer=body.user_answer,
            time_spent_sec=body.time_spent_sec,
            content_hash=content_hash,
        )
        db.add(history)

    if _reading_mode:
        # reading comprehension: XP scaled by correct answers (each question ~= XP_CORRECT/2)
        xp = add_xp(current_user, db, _reading_correct * (XP_CORRECT // 2))
    elif diacritic_hint and _vocab_mode == "normal":
        xp = XP_CORRECT // 2
        add_xp(current_user, db, xp)
    elif _vocab_mode == "vocab_session":
        if is_correct:
            vocab_status = content.get("vocab_status", "new")
            xp = XP_VOCAB_REVIEW if vocab_status == "review" else XP_VOCAB_NEW
        else:
            xp = 0
        if xp:
            add_xp(current_user, db, xp)
    elif _vocab_mode == "reduced":
        xp = XP_VOCAB if is_correct else 0
        add_xp(current_user, db, xp)
    else:
        base_xp = XP_CORRECT if is_correct else XP_INCORRECT
        if body.hint_used and is_correct:
            base_xp = max(0, base_xp - 1)
        xp = add_xp(current_user, db, base_xp)
    update_streak(current_user, db)
    update_daily_activity(current_user.id, db, xp_earned=xp, exercises_done=1)
    check_achievements(current_user, db)
    db.commit()

    return schemas.AnswerResponse(
        is_correct=is_correct,
        correct_answer=correct_answer,
        explanation=explanation,
        xp_earned=xp,
        diacritic_hint=diacritic_hint,
    )


@router.post("/report")
def report_generated_exercise(
    body: schemas.GeneratedExerciseReportCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    snapshot = None
    if body.daily_exercise_id:
        de = db.query(models.DailyExercise).filter(
            models.DailyExercise.id == body.daily_exercise_id,
            models.DailyExercise.user_id == current_user.id,
        ).first()
        if de:
            snapshot = de.content
            # Mark as completed+correct so it's excluded from errors and daily pools
            de.is_completed = True
            de.is_correct = True
            de.completed_at = datetime.utcnow()
            # Deactivate the reported exercise immediately (review queue) — a single
            # report pulls it from circulation right away, no 2nd-report threshold.
            # Collect every affected pool row: the linked entry AND any pool entry with
            # the same normalized question (the DE often has no pool link, yet the same
            # phrase lives in the pool as a separate row → it kept resurfacing).
            affected = {}
            if de.pool_exercise_id:
                pe = db.query(models.ExercisePool).filter(
                    models.ExercisePool.id == de.pool_exercise_id
                ).first()
                if pe:
                    affected[pe.id] = pe
            try:
                q_norm = _norm(json.loads(de.content).get("question", ""))
            except Exception:
                q_norm = None
            if q_norm:
                for pe in db.query(models.ExercisePool).filter(
                    models.ExercisePool.question_norm == q_norm
                ).all():
                    affected[pe.id] = pe
            for pe in affected.values():
                pe.report_count = (pe.report_count or 0) + 1
                pe.is_active = False
    elif body.exercise_id:
        ex = db.query(models.Exercise).filter(models.Exercise.id == body.exercise_id).first()
        if ex:
            snapshot = json.dumps({
                "type": ex.type, "question": ex.question,
                "correct_answer": ex.correct_answer,
                "options": json.loads(ex.options) if ex.options else None,
            }, ensure_ascii=False)
            ex.is_flagged = True

    if not snapshot:
        return {"ok": False, "detail": "exercise not found"}

    report = models.GeneratedExerciseReport(
        user_id=current_user.id,
        daily_exercise_id=body.daily_exercise_id,
        level=current_user.level,
        exercise_snapshot=snapshot,
        comment=body.comment,
    )
    db.add(report)
    db.commit()
    return {"ok": True}


@router.get("/stats")
def training_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _excl_from_total = ["vocab", "practice"]
    curriculum_total = db.query(models.UserExerciseHistory).filter(
        models.UserExerciseHistory.user_id == current_user.id
    ).count()
    curriculum_correct = db.query(models.UserExerciseHistory).filter(
        models.UserExerciseHistory.user_id == current_user.id,
        models.UserExerciseHistory.is_correct == True,
    ).count()
    ai_total = db.query(models.DailyExercise).filter(
        models.DailyExercise.user_id == current_user.id,
        models.DailyExercise.is_completed == True,
        models.DailyExercise.source.notin_(_excl_from_total),
    ).count()
    ai_correct = db.query(models.DailyExercise).filter(
        models.DailyExercise.user_id == current_user.id,
        models.DailyExercise.is_completed == True,
        models.DailyExercise.is_correct == True,
        models.DailyExercise.source.notin_(_excl_from_total),
    ).count()
    total = curriculum_total + ai_total
    correct = curriculum_correct + ai_correct
    latest_sq = (
        db.query(
            models.UserExerciseHistory.exercise_id,
            func.max(models.UserExerciseHistory.created_at).label("last_at"),
        )
        .filter(
            models.UserExerciseHistory.user_id == current_user.id,
            models.UserExerciseHistory.exercise_id.isnot(None),
        )
        .group_by(models.UserExerciseHistory.exercise_id)
        .subquery()
    )
    errors = (
        db.query(models.UserExerciseHistory)
        .join(
            latest_sq,
            (models.UserExerciseHistory.exercise_id == latest_sq.c.exercise_id)
            & (models.UserExerciseHistory.created_at == latest_sq.c.last_at),
        )
        .join(models.Exercise, models.UserExerciseHistory.exercise_id == models.Exercise.id)
        .filter(
            models.UserExerciseHistory.user_id == current_user.id,
            models.UserExerciseHistory.is_correct == False,
            models.Exercise.is_flagged == False,
        )
        .count()
    )
    # Also count AI exercises answered wrong in the last 14 days (skip NULL-dated legacy entries)
    ai_cutoff = datetime.utcnow() - timedelta(days=14)
    ai_errors = db.query(models.DailyExercise).filter(
        models.DailyExercise.user_id == current_user.id,
        models.DailyExercise.is_completed == True,
        models.DailyExercise.is_correct == False,
        models.DailyExercise.source.in_(["bonus", "new", "topic", "topic_d", "review_ai"]),  # review_ai wrongs must not vanish
        ~models.DailyExercise.content.contains('"is_error_retry"'),
        models.DailyExercise.completed_at.isnot(None),
        models.DailyExercise.completed_at >= ai_cutoff,
    ).count()
    vocab_errors = db.query(models.UserVocabulary).filter(
        models.UserVocabulary.user_id == current_user.id,
        models.UserVocabulary.correct_streak == 0,
        # Only genuinely-wrong words, matching the errors session — freshly-added
        # learn-word entries (last_reviewed NULL) are "new", not errors (#100:
        # stats showed N but the errors session was empty)
        models.UserVocabulary.last_reviewed.isnot(None),
    ).count()
    total_errors = errors + ai_errors + vocab_errors

    today = date.today()
    _daily_excl = ["bonus", "vocab", "topic", "practice"]
    daily_done = db.query(models.DailyExercise).filter(
        models.DailyExercise.user_id == current_user.id,
        models.DailyExercise.date == today,
        models.DailyExercise.source.notin_(_daily_excl),
        models.DailyExercise.is_completed == True,
    ).count()
    daily_total = db.query(models.DailyExercise).filter(
        models.DailyExercise.user_id == current_user.id,
        models.DailyExercise.date == today,
        models.DailyExercise.source.notin_(_daily_excl),
    ).count()
    practice_due = db.query(models.DailyExercise).filter(
        models.DailyExercise.user_id == current_user.id,
        models.DailyExercise.is_completed == True,
        models.DailyExercise.is_correct == True,
        models.DailyExercise.next_review.isnot(None),
        models.DailyExercise.next_review <= today,
        models.DailyExercise.source.in_(["new", "bonus", "review_ai", "topic_d"]),
    ).count()
    return {
        "total_exercises": total,
        "correct": correct,
        "errors": total_errors,
        "accuracy": round(correct / total * 100, 1) if total > 0 else 0,
        "today_done": daily_done,
        "today_total": daily_total,
        "practice_due": practice_due,
    }



def _explain_cache_key(question: str, correct_answer: str, is_correct: bool, level: int,
                       user_level: str, native_language: str) -> str:
    raw = f"{question}|{correct_answer}|{is_correct}|{level}|{user_level}|{native_language}"
    return hashlib.sha256(raw.encode()).hexdigest()[:48]


@router.post("/explain")
async def explain_exercise(
    data: schemas.ExplainRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    level = max(1, min(2, data.level))
    cache_key = _explain_cache_key(
        data.question, data.correct_answer, data.is_correct,
        level, current_user.level, current_user.native_language,
    )

    cached = db.query(models.AIExplanationCache).filter(
        models.AIExplanationCache.cache_key == cache_key
    ).first()
    if cached:
        return {"text": cached.text, "cached": True}

    type_labels = {
        "fill_blank": "fill in the missing word",
        "multiple_choice": "pick the correct option",
        "translate": "translation",
        "order_words": "arrange the sentence",
        "judge_sentence": "true / false judgement",
        "letter_tiles": "assemble the word from letters",
        "flashcard": "flashcard",
        "word_definition": "guess the word from its description",
    }
    nl = lang_name(current_user.native_language)

    if level == 1:
        system = (
            f"You are a Polish language teacher. "
            f"Student: Polish level {current_user.level}, native language {nl}.\n\n"
            "Explain the result of one specific exercise — briefly, 3-5 sentences, no preamble.\n\n"
            "Answer structure:\n"
            f"0. If the exercise contains a Polish sentence — start with its translation into {nl} "
            "(one line, in *italics*).\n"
            "   If a translation is already given in the 'Exercise translation' field — use it.\n"
            "1. Why the answer is correct or wrong — referring to the specific Polish rule.\n"
            "   For the true/false type: name the EXACT word or form that makes the sentence\n"
            "   correct or wrong. Do not discuss the topic in general — only this error.\n"
            "2. How the rule works and how to remember it.\n"
            "3. Only if the student's answer is objectively also grammatically valid — say so honestly.\n"
            "   If the student's answer is wrong — do not bring up the notion of flawed exercises at all.\n"
            "4. The 'Exercise's own explanation' below was machine-generated and MAY contain errors —\n"
            "   verify it against actual Polish grammar and, if it is wrong, state the correct rule\n"
            "   instead of repeating the mistake.\n\n"
            f"Reply in {nl}. Keep Polish words and forms in Polish."
        )
        max_tokens = 500
    else:
        system = (
            f"You are a Polish language teacher. "
            f"Student: Polish level {current_user.level}, native language {nl}.\n\n"
            "The student has already received a short explanation and wants to go deeper. "
            "Give an extended explanation with examples — 8-12 sentences.\n\n"
            "Answer structure:\n"
            "1. The full formulation of the rule, including exceptions\n"
            "2. **2-3 living examples** with translations demonstrating the rule\n"
            "3. Typical mistakes learners make — and how to avoid them\n"
            f"4. A mnemonic or an analogy with {nl} if one exists\n\n"
            "Use markdown: **bold** for terms, lists for examples.\n"
            f"Reply in {nl}. Keep Polish words and forms in Polish."
        )
        max_tokens = 900

    result_label = "correct ✓" if data.is_correct else "wrong ✗"
    user_msg = (
        f"Exercise type: {type_labels.get(data.exercise_type, data.exercise_type)}\n"
        f"Question: {data.question}\n"
        f"Correct answer: {data.correct_answer}\n"
        f"Student's answer: {data.user_answer or '(nothing entered)'}\n"
        f"Graded as: {result_label}\n"
    )
    if data.translation:
        user_msg += f"Exercise translation: {data.translation}\n"
    if data.explanation:
        user_msg += f"Exercise's own explanation: {data.explanation}\n"

    # large first: explanations are cached, so quality beats the marginal cost —
    # small produced factually shaky explanations (user feedback 2026-07-06)
    text = None
    for model_name in ("mistral-large-latest", "mistral-small-latest"):
        try:
            text = await mistral.simple_prompt(
                system=system,
                user=user_msg,
                temperature=0.3,
                max_tokens=max_tokens,
                timeout=25.0,
                retries=1,
                model=model_name,
                purpose="explain",
                user_id=current_user.id,
            )
            text = text.strip()
            break
        except Exception:
            continue
    if not text:
        raise HTTPException(status_code=503, detail="AI temporarily unavailable")

    db.add(models.AIExplanationCache(cache_key=cache_key, level=level, text=text))
    try:
        db.commit()
    except Exception:
        db.rollback()

    return {"text": text, "cached": False}


@router.post("/session-complete")
def session_complete(
    data: schemas.SessionCompleteRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if data.duration_seconds > 0:
        current_user.total_training_seconds = (current_user.total_training_seconds or 0) + data.duration_seconds
        db.add(current_user)
        db.commit()
        new_achievements = check_achievements(current_user, db)
        return {
            "ok": True,
            "total_training_seconds": current_user.total_training_seconds,
            "new_achievements": [a.slug for a in new_achievements],
        }
    return {"ok": True}


@router.post("/session-rating")
def session_rating(
    data: schemas.SessionRatingRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    import json as _json
    # The star click submits immediately (feedback #117: users don't notice the send
    # button, ratings were lost); a follow-up with rating_id updates the same row
    # instead of creating a duplicate.
    if data.rating_id:
        row = db.query(models.SessionRating).filter(
            models.SessionRating.id == data.rating_id,
            models.SessionRating.user_id == current_user.id,
        ).first()
        if row:
            if data.rating is not None:
                row.rating = data.rating
            if data.comment:
                row.comment = data.comment
            db.commit()
            return {"ok": True, "rating_id": row.id}
    row = models.SessionRating(
        user_id=current_user.id,
        mode=data.mode,
        rating=data.rating,
        comment=data.comment or None,
        exercise_ids=_json.dumps(data.exercise_ids) if data.exercise_ids else None,
    )
    db.add(row)
    db.commit()
    return {"ok": True, "rating_id": row.id}


async def _check_translation(user_answer: str, correct_answer: str, question: str, user, focus: str = "") -> bool:
    if user_answer.strip().lower() == correct_answer.strip().lower():
        return True
    prompt = prompts.TRANSLATION_CHECK_PROMPT.format(
        level=user.level,
        native_language=lang_name(user.native_language),
        source_text=question,
        user_answer=user_answer,
        correct_answer=correct_answer,
        focus=focus or "general translation",
    )
    # large first; if it fails (429 during generation bursts is common) fall back to small —
    # never silently mark a possibly-correct answer wrong because of an API hiccup
    for model_name in ("mistral-large-latest", "mistral-small-latest"):
        try:
            raw = await mistral.simple_prompt(
                system="You are a Polish language checker. Respond only with JSON.",
                user=prompt,
                temperature=0.1,
                max_tokens=200,
                retries=2,
                model=model_name,
                purpose="translation_check",
                user_id=user.id,
            )
            result = await mistral.parse_json_response(raw)
            return result.get("correct", False)
        except Exception:
            continue
    # Both models unavailable: degraded check — same words in any order counts as correct
    # (word order is free in Polish; this at least doesn't punish reordering)
    return sorted(_strip(w) for w in user_answer.split()) == \
           sorted(_strip(w.rstrip('.?!,;')) for w in correct_answer.split())


async def _check_word_order(user_answer: str, correct_answer: str, translation: str, user) -> bool:
    """Lenient order_words check: same words, different order — ask Mistral if the
    user's order is also grammatical/natural Polish (word order is largely free).

    small is cheap but rejects valid variants (vocative moved to the end — report #240);
    a REJECTION is escalated to large before the user is marked wrong. Acceptances are
    trusted as-is, so the extra call happens only on the rare reject path."""
    prompt = prompts.WORD_ORDER_CHECK_PROMPT.format(
        correct_answer=correct_answer,
        user_answer=user_answer,
        translation=translation or "",
    )
    for model_name in ("mistral-small-latest", "mistral-large-latest"):
        try:
            raw = await mistral.simple_prompt(
                system="You are a Polish language checker. Respond only with JSON.",
                user=prompt,
                temperature=0.1,
                max_tokens=100,
                retries=2,
                model=model_name,
                purpose="order_check",
                user_id=user.id,
            )
            result = await mistral.parse_json_response(raw)
            if bool(result.get("correct", False)):
                return True
        except Exception:
            continue
    return False

