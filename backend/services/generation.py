"""Mistral exercise generation, shared exercise pool, topic/theme selection.

Extracted from routers/training.py. Session endpoints call into this module;
it must NOT import from routers.* (circular import — see CLAUDE.md pitfalls).
"""
import asyncio
import json
import random
import re
from collections import Counter
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
import prompts
from services import mistral
from services.validators import (
    _norm,
    _strip,
    _validate_type,
    _sanitize_native_fields,
    _clean_word_hints,
    _require_word_hints,
    _fix_flashcard_exercise,
    _fix_mc_exercise,
    _fix_fill_blank_exercise,
    _fix_letter_tiles_exercise,
    _tilesify,
    _fix_translate_exercise,
    _fix_judge_sentence_exercise,
    _fix_order_words_exercise,
    _fix_word_definition_exercise,
    _too_similar,
    _question_skeleton,
    _is_numeral_word,
    _dedup_question_key,
)
from services.i18n import lang_name, ui

_LEVEL_ORDER = ["A0", "A1", "A2", "B1", "B2", "C1", "C2"]

_VOCAB_CEILING = "B2"  # the app pulls the learner UP; only cap is "harder than B2"

def _eligible_vocab_levels(user_level: str) -> list:
    """Words to teach as NEW: the user's current level and a 2-step stretch upward,
    never past B2. An A2 user gets A2/B1/B2 — the engine should pull upward, not cap
    new vocab at the current level (that left the learner with nothing fresh)."""
    idx = _LEVEL_ORDER.index(user_level) if user_level in _LEVEL_ORDER else 2
    ceil = min(idx + 2, _LEVEL_ORDER.index(_VOCAB_CEILING))
    return _LEVEL_ORDER[idx:ceil + 1]


def _clamp_vocab_level(raw, user_level: str) -> str:
    """Keep a Mistral-tagged word level within the eligible stretch; else default to current."""
    lv = (raw or "").strip().upper()
    return lv if lv in set(_eligible_vocab_levels(user_level)) else user_level


# Per-topic emphasis injected into topic generation (lean — only where the default
# explanation misses a pattern users specifically struggle with).
_TOPIC_FOCUS = {
    "prepositions": (
        "Focus on the CHOICE of preposition: whether one is needed and which. Contrast cases where "
        "Polish uses a preposition but the user's language may not (czekać NA kogoś, martwić się O kogoś, "
        "słuchać kogoś with no preposition) and which case each preposition governs."
    ),
    "negation": (
        "Focus on nie + dopełniacz: under negation biernik→dopełniacz (mam kota → nie mam kota; "
        "lubię herbatę → nie lubię herbaty). Include double negation (nikt nic nie wie)."
    ),
    "instrumental": (
        "IMPORTANT: the difference between «być/zostać + narzędnik» (jest lekarzem) and «pracować JAKO + "
        "mianownik» (pracuje jako lekarz — NOT lekarzem!). After jako — NOMINATIVE case. Never mix these up."
    ),
}


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
            "question": ui("assemble_word", native_language, translation=translation),
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
                desc += f' (reported issue: {r.comment})'
            report_lines.append(desc)
        except Exception:
            pass
    if report_lines:
        result += "\n\nNEVER repeat these exercises — the user flagged them as faulty:\n" + "\n".join(report_lines)

    return result


def _save_to_pool(item: dict, level: str, topic_id, db: Session):
    """Save a validated exercise item to the shared pool. Returns pool_exercise_id or None."""
    q_norm = _dedup_question_key(item)  # order_words keyed by sentence, not the shuffle (#247/#249)
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


def _pool_active(db: Session, pool_id) -> bool:
    """False when this pool entry exists and was retired (is_active=0) — e.g. by a report.
    Used to drop a regenerated copy of a reported question before it reaches the user."""
    if not pool_id:
        return True
    row = db.query(models.ExercisePool.is_active).filter(
        models.ExercisePool.id == pool_id
    ).first()
    return bool(row[0]) if row else True


def _pool_draw(db: Session, user_id: int, level: str, count: int,
               seen_norms: set | None = None, seen_skeletons: set | None = None,
               seen_answers: set | None = None) -> list:
    """Draw up to count unseen active exercises from the shared pool for this user at this level.

    Excludes by pool_exercise_id (entries already served from the pool), by question_norm
    against `seen_norms` (a question met via a NON-pool DailyExercise — reports #194/#99),
    AND by construction skeleton against `seen_skeletons` — the pool holds many variants of
    one template ('prezent dla mamy' / 'prezent dla brata') with different question_norm, so
    norm-dedup alone keeps surfacing the same drill (reports #224/#225). Also dedups skeletons
    within this single draw."""
    seen_sq = db.query(models.DailyExercise.pool_exercise_id).filter(
        models.DailyExercise.user_id == user_id,
        models.DailyExercise.pool_exercise_id.isnot(None),
    ).subquery()
    q = db.query(models.ExercisePool).filter(
        models.ExercisePool.level == level,
        models.ExercisePool.is_active == True,
        models.ExercisePool.id.notin_(seen_sq),
    )
    if not seen_norms and not seen_skeletons and not seen_answers:
        return q.order_by(func.random()).limit(count).all()
    # over-fetch then filter in Python by normalized text + opening skeleton + answer word
    candidates = q.order_by(func.random()).limit(count * 6).all()
    seen_norms = seen_norms or set()
    used_sk = set(seen_skeletons or set())
    used_ans = set(seen_answers or set())
    out = []
    for p in candidates:
        if (p.question_norm or "") in seen_norms:
            continue
        try:
            d = json.loads(p.content)
        except Exception:
            d = {}
        sk = _question_skeleton(d.get("question", "")) if d else ""
        if sk and sk in used_sk:
            continue  # same construction already seen / already drawn this session
        ans = _answer_dedup_key(d)
        if ans and ans in used_ans:
            continue  # same target word/numeral already seen (drogeria #234, piątego #147)
        if sk:
            used_sk.add(sk)
        if ans:
            used_ans.add(ans)
        out.append(p)
        if len(out) >= count:
            break
    return out


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
            d = json.loads(de.content)
            key = _dedup_question_key(d)
            if key:
                result.add(key)
        except Exception:
            pass
    return result


def _seen_skeletons(user_id: int, db: Session, limit: int = 80) -> Counter:
    """Count opening-construction skeletons across recently completed AI exercises, so
    generation can refuse a template the user has already seen too many times
    ('Na stole leży ___' over and over). Returns Counter{skeleton: times_seen}."""
    rows = db.query(models.DailyExercise).filter(
        models.DailyExercise.user_id == user_id,
        models.DailyExercise.source.in_(["new", "bonus", "review_ai", "topic", "topic_d"]),
        models.DailyExercise.is_completed == True,
    ).order_by(models.DailyExercise.completed_at.desc()).limit(limit).all()
    counts = Counter()
    for de in rows:
        try:
            q = json.loads(de.content).get("question", "")
            sk = _question_skeleton(q)
            if sk:
                counts[sk] += 1
        except Exception:
            pass
    return counts


# Types where the ANSWER word is the thing being learned — repeating it (drogeria over
# and over, #234; typing 'pracy' yet again, feedback #134) wastes the slot regardless
# of how the riddle/sentence around it is worded.
_ANSWER_DEDUP_TYPES = {"word_definition", "flashcard", "letter_tiles"}


def _answer_dedup_key(d: dict):
    """Normalized answer for dedup, or None. Covers the answer-centric types AND
    fill_blank with a numeral answer — the same 'piątego (5)' kept coming back in
    different date sentences (#147: 'числа одни и те же')."""
    t = d.get("type")
    ca = d.get("correct_answer") or ""
    if t in _ANSWER_DEDUP_TYPES or (
        t == "fill_blank" and any(_is_numeral_word(w) for w in ca.split())
    ):
        key = _strip(ca).rstrip('.?!,;')
        return key or None
    return None

_SKELETON_MAX = 2  # allow a construction at most twice before it feels like a drill

_FIXER_CHAIN = (
    ("type", _validate_type),
    ("mc", _fix_mc_exercise),
    ("fill_blank", _fix_fill_blank_exercise),
    ("tilesify", _tilesify),
    ("letter_tiles", _fix_letter_tiles_exercise),
    ("order_words", _fix_order_words_exercise),
    ("flashcard", _fix_flashcard_exercise),
    ("translate", _fix_translate_exercise),
    ("judge", _fix_judge_sentence_exercise),
    ("word_def", _fix_word_definition_exercise),
)


def _validate_batch(items: list, user, db: Session, *, pool_drawn=(), label: str = "") -> list:
    """The single validation+dedup pipeline for freshly generated exercises. Was copy-pasted
    in 3 places (daily/bonus/drill) and drifted. Logs the per-reason rejection breakdown -
    silent filtering is how the skeleton over-ban zeroed the pool and sessions shrank to
    11/20 without anyone noticing (feedback #145/#146)."""
    seen_qs = _seen_questions(user.id, db, limit=400)   # ~4 days at the user's real pace
    seen_tokens = [set(q.split()) for q in seen_qs]
    skeletons = _seen_skeletons(user.id, db, limit=400)
    answers = _seen_answers(user.id, db)
    # Items just drawn from the pool are part of THIS session - without seeding, a freshly
    # generated twin of a drawn question passed seen_qs and the same phrase appeared twice.
    for pool_ex in pool_drawn:
        try:
            d0 = json.loads(pool_ex.content)
        except Exception:
            continue
        qn0 = _norm(d0.get("question", ""))
        if qn0:
            seen_qs.add(qn0); seen_tokens.append(set(qn0.split()))
        sk0 = _question_skeleton(d0.get("question", ""))
        if sk0:
            skeletons[sk0] += 1
        a0 = _answer_dedup_key(d0)
        if a0:
            answers.add(a0)
    validated = []
    rejects = Counter()
    for item in items:
        for name, fn in _FIXER_CHAIN:
            item = fn(item)
            if item is None:
                rejects[name] += 1
                break
        if item is None:
            continue
        item = _sanitize_native_fields(item, user.native_language)
        item = _clean_word_hints(item)
        item = _require_word_hints(item)
        if item is None:
            rejects["hints"] += 1
            continue
        qn = _dedup_question_key(item)
        if qn in seen_qs or _too_similar(qn, seen_tokens):
            rejects["duplicate"] += 1
            continue
        sk = _question_skeleton(item.get("question", ""))
        if sk and skeletons[sk] >= _SKELETON_MAX:
            rejects["skeleton"] += 1
            continue
        ans = _answer_dedup_key(item)
        if ans and ans in answers:
            rejects["answer"] += 1
            continue
        if sk:
            skeletons[sk] += 1
        if ans:
            answers.add(ans)
        seen_qs.add(qn); seen_tokens.append(set(qn.split()))
        validated.append(item)
    if label:
        print(f"[validate:{label}] raw={len(items)} kept={len(validated)} rejected={dict(rejects)}")
    return validated

def _seen_answers(user_id: int, db: Session, limit: int = 1500) -> set:
    """Normalized answer words the user recently saw for answer-centric types, so generation
    and pool draws don't keep serving the same target word with a reworded clue (#230/#234).
    The window must be LONG: users remember a riddle for weeks — with limit=120 'cytryna'
    fell out of the window in 5 active days and came back a 10th time (#237)."""
    rows = db.query(models.DailyExercise).filter(
        models.DailyExercise.user_id == user_id,
        models.DailyExercise.source.in_(["new", "bonus", "review_ai", "topic", "topic_d"]),
        models.DailyExercise.is_completed == True,
    ).order_by(models.DailyExercise.completed_at.desc()).limit(limit).all()
    result = set()
    for de in rows:
        try:
            d = json.loads(de.content)
            ca = _answer_dedup_key(d)
            if ca:
                result.add(ca)
        except Exception:
            pass
    return result


def _worddef_candidates_block(user_id: int, db: Session) -> str:
    """Feedback #68: seed word_definition riddles with words the user has already learned
    (reinforcement + naturally no repeats: already-riddled answers are excluded)."""
    if db is None:
        return ""
    seen = _seen_answers(user_id, db)
    rows = db.query(models.Vocabulary.polish).join(
        models.UserVocabulary,
        models.UserVocabulary.vocab_id == models.Vocabulary.id,
    ).filter(
        models.UserVocabulary.user_id == user_id,
        models.UserVocabulary.correct_streak >= 1,
    ).all()
    words = [r[0] for r in rows
             if r[0] and " " not in r[0] and len(r[0]) >= 4
             and _strip(r[0]).rstrip('.?!,;') not in seen]
    if len(words) < 3:
        return ""
    sample = random.sample(words, min(6, len(words)))
    return ("Build roughly half of the riddles around these words from the user's own vocabulary "
            "(reinforcement of learned words): " + ", ".join(sample) + ". The rest — new words.\n")


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
        "\n\nThe user already knows these words — work some of them"
        " into the exercises (fill_blank, translate, judge_sentence) for reinforcement: "
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
        return f"\n\nADAPTATION: last {total} answers — {pct:.0f}% correct. The user is doing well — make vocabulary and grammar slightly harder."
    elif pct <= 45:
        return f"\n\nADAPTATION: last {total} answers — {pct:.0f}% correct. The user makes many mistakes — simplify, more basic constructions and short phrases."
    else:
        return f"\n\nADAPTATION: last {total} answers — {pct:.0f}% correct. Keep the current difficulty."


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
        native_language=lang_name(user.native_language),
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
        item = _tilesify(item) if item else None  # format A: Python picks the blank word (#114)
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
        item["topic_title"] = ui("idioms_badge", user.native_language)  # session header badge
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


async def _ensure_vocab_pool(user, db: Session, threshold: int = 40, batch: int = 50):
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
                native_language=lang_name(user.native_language),
                count=batch,
                avoid_words=avoid_list,
            ),
            temperature=0.85,
            max_tokens=4000,
            timeout=45.0,   # batch=50 words takes >20s on small; was timing out
            retries=2,
            model="mistral-small-latest",
            purpose="vocab_gen",
            user_id=user.id,
        )
        generated = await mistral.parse_json_response(raw)
    except Exception as e:
        print(f"[vocab_gen] Mistral failed for user {user.id}: {type(e).__name__}: {e}")
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
            level=_clamp_vocab_level(item.get("level"), user.level),  # keep real level (B1/B2), not always current
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
    fallback = "not set (use varied themes)"
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
    _DONE_REVIEW_SLUGS = _SKIP_GENERATION_SLUGS

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

    # If >=60% of current+below topics are done, inject one next-level topic (pull upward sooner)
    if next_level and all_eligible:
        coverage = 1 - len(candidates) / len(all_eligible)
        if coverage >= 0.6:
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

    # Done topics resurface for spaced review (not in the last 7 days) — otherwise a
    # mastered topic like negation disappears forever and never gets reinforced.
    done_review = db.query(models.Topic).filter(
        models.Topic.explanation_ru.isnot(None),
        models.Topic.explanation_ru != "",
        models.Topic.id.in_(done_ids) if done_ids else False,
    ).all()
    done_review = [t for t in done_review
                   if t.id not in recent_ids and t.slug not in _DONE_REVIEW_SLUGS]
    random.shuffle(done_review)  # vary which mastered topic comes back

    # Pick n topics: weakest non-done first, then recently-covered non-done, then a
    # mastered topic for spaced review.
    chosen = []
    used_ids = set()
    fresh = [t for t in candidates if t.id not in recent_ids]
    stale = [t for t in candidates if t.id in recent_ids]

    # fresh first; then MASTERED topics coming back for spaced review; recently-covered
    # (stale) topics are the LAST resort — with few non-done topics left, the old order
    # served vocative/numbers-dates several days in a row (feedback #149/#150)
    for pool in (fresh, done_review, stale):
        for t in pool:
            if t.id not in used_ids:
                chosen.append(t)
                used_ids.add(t.id)
            if len(chosen) >= n:
                break
        if len(chosen) >= n:
            break

    return chosen


async def _generate_exercises(user, count: int, interest_themes_str: str, level: str = None, topics: list = None, db=None) -> list:
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
            level=gen_level, native_language=lang_name(user.native_language), count=batch_count,
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

    word_def_candidates = _worddef_candidates_block(user.id, db) if db is not None else ""

    async def _batch(prompt_template, batch_count, label):
        prompt = prompt_template.format(
            level=gen_level,
            native_language=lang_name(user.native_language),
            interest_themes=interest_themes_str,
            count=batch_count,
            candidate_words=word_def_candidates,
        )
        if topics:
            rule_names = ", ".join(t.title_ru or t.slug for t in topics)
            prompt = f"Grammar rules of this session: {rule_names}. Build examples in the context of these rules.\n\n" + prompt
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
        focus = _TOPIC_FOCUS.get(topic_obj.slug, "")
        nl = lang_name(user.native_language)
        prompt = (
            "You generate Polish language exercises.\n"
            f"Level: {gen_level}. User's native language: {nl}.\n"
            f"Grammar rule topic: {title}\n\n"
            f"Rule description:\n{summary}\n\n"
            + (f"SPECIAL FOCUS: {focus}\n\n" if focus else "")
            + prompts._EXERCISE_COMMON_RULES + "\n\n"
            f"Generate {batch_count} exercises. Types: fill_blank, multiple_choice. Mix evenly.\n"
            "ALL exercises must explicitly test this rule.\n"
            "FORBIDDEN: tasks about pronunciation or 'how is it read' — grammar only.\n\n"
            "FILL_BLANK:\n"
            "- EXACTLY ONE ___ in question\n"
            "- The answer is NOT present in question\n"
            "- hint: the grammatical category, NOT the answer itself\n\n"
            "MULTIPLE_CHOICE — 4 options:\n"
            "- correct_answer matches one of options VERBATIM\n"
            "- FORBIDDEN: meta-questions where the answer is visible in the question text\n\n"
            f"translation/explanation/word_hints values are written in {nl} "
            "(example values below are in English — write yours in the user's language).\n"
            "Answer ONLY with valid JSON, no markdown:\n"
            '[{"type": "fill_blank", "question": "Poproszę ___ kawy.", "correct_answer": "filiżankę", '
            '"options": null, "hint": "biernik od filiżanka", "explanation": "After poproszę — biernik", '
            '"translation": "A cup of coffee, please.", "word_hints": {"poproszę": "please give me", "kawy": "coffee"}}]'
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
        nl = lang_name(user.native_language)
        prompt = (
            "You generate Polish language exercises.\n"
            f"Level: {gen_level}. User's native language: {nl}.\n"
            f"Topic: {title}\n\n"
            f"Rule context:\n{summary}\n\n"
            + prompts._EXERCISE_COMMON_RULES + "\n\n"
            f"Generate {batch_count} exercises with vocabulary and phrases tied to this topic.\n"
            "Types (mix evenly): translate, order_words. (Do NOT generate idioms/flashcards here.)\n"
            f"TRANSLATE: a phrase in {nl}, ≤ 10 words → Polish translation using the topic's grammar.\n"
            f"ORDER_WORDS: the Polish sentence's words shuffled and joined with ' / ', correct_answer = the right order, translation = translation into {nl}.\n"
            f"question (for translate) and translation values are written in {nl} — "
            "example values below are in English, write yours in the user's language.\n"
            "Answer ONLY with a valid JSON array, no markdown:\n"
            "[\n"
            '  {"type": "translate", "question": "This is my book.", "correct_answer": "To jest moja książka.", "hint": null, "translation": null},\n'
            '  {"type": "order_words", "question": "jest / moja / To / książka", "correct_answer": "To jest moja książka.", "hint": null, "translation": "This is my book."}\n'
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
    all_items = await _verify_judge_false(all_items, user)
    all_items = await _verify_word_definitions(all_items, user)
    return all_items


async def _verify_word_definitions(items: list, user) -> list:
    """Post-validation for word_definition riddles: drop any whose description is factually
    wrong or ambiguous (sour-apple #213, ambiguous carrot #219). One batched cheap call."""
    suspects = [it for it in items if it.get("type") == "word_definition"]
    if not suspects:
        return items
    payload = [
        {"id": i, "description": it.get("question", ""), "answer": it.get("correct_answer", "")}
        for i, it in enumerate(suspects)
    ]
    try:
        raw = await mistral.simple_prompt(
            system="You are a strict Polish riddle editor. Respond only with JSON.",
            user=prompts.WORD_DEFINITION_VERIFY_PROMPT.format(items=json.dumps(payload, ensure_ascii=False)),
            temperature=0.0,
            max_tokens=600,
            timeout=30.0,
            retries=1,
            model="mistral-small-latest",
            purpose="worddef_verify",
            user_id=user.id,
        )
        verdicts = await mistral.parse_json_response(raw)
        ok = {v["id"] for v in verdicts if isinstance(v, dict) and v.get("verdict") == "ok"}
    except Exception as e:
        print(f"[worddef_verify] failed for user {user.id}: {type(e).__name__}: {e}")
        ok = set()  # verifier down → drop unverified riddles rather than ship bad ones
    rejected = {id(suspects[i]) for i in range(len(suspects)) if i not in ok}
    kept = [it for it in items if id(it) not in rejected]
    dropped = len(items) - len(kept)
    if dropped:
        print(f"[worddef_verify] dropped {dropped}/{len(suspects)} riddles for user {user.id}")
    return kept


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

    nl = lang_name(user.native_language)
    prompt = (
        "You generate Polish language exercises.\n"
        "Grammar rule topic: " + title + " (level " + user.level + ", user's native language: " + nl + ")\n\n"
        "Rule description (use it as the base for the tasks):\n" + summary + "\n\n"
        + prompts._EXERCISE_COMMON_RULES + "\n\n"
        "Generate exactly " + str(count) + " exercises STRICTLY on this topic.\n"
        "Types: fill_blank and multiple_choice (roughly half each).\n"
        "ALL exercises must explicitly test the understanding of this exact rule.\n"
        "FORBIDDEN: tasks about pronunciation, phonetic transcription or 'how is it read' — grammar and vocabulary only.\n\n"
        "FILL_BLANK:\n"
        "- EXACTLY ONE ___ in question\n"
        "- The answer is NOT present in question (not in parentheses, not near ___)\n"
        "- FORBIDDEN: masculine inanimate in biernik (form unchanged → trivial)\n"
        "- correct_answer: one word or a fixed phrase, no /\n"
        "- hint: the grammatical category, NOT the answer itself\n"
        "- word_hints: Polish words of the question → " + nl + "\n\n"
        "MULTIPLE_CHOICE — 4 options:\n"
        "- correct_answer matches one of options VERBATIM\n"
        "- Options are substantially different (different cases/forms)\n"
        "- If the question is about meaning — all options in " + nl + "\n"
        "- word_hints: Polish words of the question → " + nl + " (1-3 key ones, excluding the options)\n\n"
        "explanation/word_hints values are written in " + nl + " (example values below are in English — "
        "write yours in the user's language).\n"
        "Answer ONLY with a valid JSON array, no markdown:\n"
        "[\n"
        '  {"type": "fill_blank", "question": "Poproszę ___ kawy.", "correct_answer": "filiżankę", "options": null, "hint": "biernik od filiżanka", "explanation": "After poproszę — biernik", "translation": null, "word_hints": {"poproszę": "please give me"}},\n'
        '  {"type": "multiple_choice", "question": "Lubię ___ (herbata).", "options": ["herbatę", "herbaty", "herbacie", "herbata"], "correct_answer": "herbatę", "hint": null, "explanation": "After lubię — biernik", "translation": null, "word_hints": {"lubię": "I like"}}\n'
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
        nl = lang_name(user.native_language)
        prompt = (
            "You generate Polish language exercises.\n"
            "Grammar rule topic: " + title + " (level " + user.level + ", user's native language: " + nl + ")\n\n"
            "Rule description (use it as the base for the tasks):\n" + summary + "\n\n"
            + prompts._EXERCISE_COMMON_RULES + "\n\n"
            "Generate exactly 2 exercises STRICTLY on this topic.\n"
            "Types: fill_blank and multiple_choice (one of each).\n"
            "ALL exercises must explicitly test the understanding of this exact rule.\n"
            "FORBIDDEN: tasks about pronunciation, phonetic transcription or 'how is it read' — grammar and vocabulary only.\n\n"
            "FILL_BLANK:\n"
            "- EXACTLY ONE ___ in question\n"
            "- The answer is NOT present in question\n"
            "- correct_answer: one word or a fixed phrase, no /\n"
            "- hint: the grammatical category, NOT the answer itself\n\n"
            "MULTIPLE_CHOICE — 4 options:\n"
            "- correct_answer matches one of options VERBATIM\n"
            "- Options are substantially different (different cases/forms)\n"
            "- word_hints: Polish words of the question → " + nl + " (1-3 key ones)\n\n"
            "explanation/word_hints values are written in " + nl + " (example values below are in English — "
            "write yours in the user's language).\n"
            "Answer ONLY with a valid JSON array, no markdown:\n"
            "[\n"
            '  {"type": "fill_blank", "question": "Poproszę ___ kawy.", "correct_answer": "filiżankę", "options": null, "hint": "biernik od filiżanka", "explanation": "After poproszę — biernik", "translation": null, "word_hints": {"poproszę": "please give me"}},\n'
            '  {"type": "multiple_choice", "question": "Lubię ___ (herbata).", "options": ["herbatę", "herbaty", "herbacie", "herbata"], "correct_answer": "herbatę", "hint": null, "explanation": "After lubię — biernik", "translation": null, "word_hints": {"lubię": "I like"}}\n'
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
        # topic_d repeats every ~10 days per topic — the default 60-item window (~2 days)
        # forgot earlier runs and the same question came back 4x ('буква ц', feedback #138)
        seen_qs = _seen_questions(user.id, db, limit=500)
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


def _error_retry_entries(user, db: Session, today, source: str, limit: int = None) -> list:
    """Error-work injected into the general pools (user decision 2026-07-15: daily/bonus
    include EVERYTHING — errors never shrink if they live only in a mode the user rarely
    opens). A copy is served; on a correct answer the dupes-clearing block in submit_answer
    marks the wrong ORIGINAL fixed, and SM2 puts the item into the practice queue."""
    backlog_q = db.query(models.DailyExercise).filter(
        models.DailyExercise.user_id == user.id,
        models.DailyExercise.is_completed == True,
        models.DailyExercise.is_correct == False,
        models.DailyExercise.source.in_(["bonus", "new", "topic", "topic_d", "review_ai"]),
        models.DailyExercise.completed_at.isnot(None),
        models.DailyExercise.completed_at >= datetime.utcnow() - timedelta(days=14),
        ~models.DailyExercise.content.contains('"is_error_retry"'),
    )
    if limit is None:
        # Scale with the backlog (feedback #156/#159: 3 retries/session vs 4-9 new
        # mistakes — the pile could only grow). 6 when drowning, 3 when nearly clear.
        backlog = backlog_q.count()
        limit = 6 if backlog > 50 else 5 if backlog > 20 else 3
    err_due = backlog_q.order_by(func.random()).limit(limit).all()
    out = []
    for de_err in err_due:
        try:
            c_err = json.loads(de_err.content)
        except Exception:
            continue
        c_err["is_error_retry"] = True  # serve-time badge override → '⚠️ Ошибка'
        out.append(models.DailyExercise(
            user_id=user.id, date=today, exercise_type=de_err.exercise_type,
            content=json.dumps(c_err, ensure_ascii=False), source=source,
            content_type=de_err.content_type, topic_id=de_err.topic_id,
            pool_exercise_id=de_err.pool_exercise_id,
        ))
    return out


def _bonus_vocab_entries(user, db: Session, today, limit: int = 3) -> list:
    """Due vocab cards for the bonus mix (daily already carries them as source='review').
    Skips words already sitting in today's still-open exercises."""
    used_vocab_ids = set()
    for (content,) in db.query(models.DailyExercise.content).filter(
        models.DailyExercise.user_id == user.id,
        models.DailyExercise.date == today,
        models.DailyExercise.is_completed == False,
    ).all():
        try:
            vid = json.loads(content).get("vocab_id")
            if vid:
                used_vocab_ids.add(vid)
        except Exception:
            pass
    due = db.query(models.UserVocabulary).filter(
        models.UserVocabulary.user_id == user.id,
        models.UserVocabulary.next_review <= today,
    ).order_by(func.random()).limit(limit * 2).all()
    out = []
    for uv in due:
        if uv.vocab_id in used_vocab_ids or len(out) >= limit:
            continue
        card = _vocab_card_content(uv.vocab, "review", user.native_language, uv.correct_streak or 0)
        out.append(models.DailyExercise(
            user_id=user.id, date=today, exercise_type=card["type"],
            content=json.dumps(card, ensure_ascii=False), source="bonus",
        ))
    return out


# One generation at a time per user. Two concurrent session requests (frontend retry
# after a slow Mistral call, double tap) both saw an empty batch and both generated —
# the same pool entries were served twice in one day (feedback #112/#122/#124-127:
# pool ids 780-784 duplicated 30s apart). The second request now waits, re-checks
# inside the lock and returns if the batch already exists. Single uvicorn worker →
# an in-process asyncio.Lock is sufficient.
_USER_GEN_LOCKS: dict = {}

def _user_gen_lock(user_id: int) -> asyncio.Lock:
    return _USER_GEN_LOCKS.setdefault(user_id, asyncio.Lock())


async def _generate_reading(user, db: Session, today, level: str = None):
    async with _user_gen_lock(user.id):
        db.commit()  # end any read snapshot so rows committed by a parallel request are visible
        if db.query(models.DailyExercise).filter(
            models.DailyExercise.user_id == user.id,
            models.DailyExercise.date == today,
            models.DailyExercise.source == "reading",
            models.DailyExercise.is_completed == False,
        ).count() > 0:
            return
        return await _generate_reading_inner(user, db, today, level)


async def _generate_reading_inner(user, db: Session, today, level: str = None):
    """Generate one reading-comprehension passage + 3 MC questions (source='reading').
    A single DailyExercise of type='reading'; scored as a unit in submit_answer."""
    gen_level = level or user.level
    themes = _select_interest_themes(user.content_preferences)
    prompt = prompts.READING_PROMPT.format(
        level=gen_level, native_language=lang_name(user.native_language), interest_themes=themes,
    )
    raw = None
    for model_name, timeout_sec in [("mistral-large-latest", 60.0), ("mistral-small-latest", 40.0)]:
        try:
            raw = await mistral.simple_prompt(
                system="You are a Polish reading-comprehension generator. Respond only with a valid JSON object.",
                user=prompt, temperature=0.8, max_tokens=2000,
                timeout=timeout_sec, retries=1, model=model_name,
                purpose="reading", user_id=user.id,
            )
            break
        except Exception as e:
            print(f"[reading] {model_name} failed for user {user.id}: {type(e).__name__}: {e}")
    if not raw:
        return
    try:
        item = await mistral.parse_json_response(raw)
    except Exception:
        return
    if not isinstance(item, dict) or not item.get("text") or not isinstance(item.get("questions"), list):
        return
    # Keep only well-formed questions. Mistral often labels options ("B. ...") and returns
    # correct_answer as a bare letter ("B") — strip labels and map the letter to its option.
    def _strip_label(o):
        m = re.match(r'^\s*[A-Da-d][.)]\s*(.+)$', str(o))
        return (m.group(1) if m else str(o)).strip()

    qs = []
    for q in item["questions"]:
        opts = q.get("options") or []
        if not isinstance(opts, list) or len(opts) < 2:
            continue
        clean = [_strip_label(o) for o in opts]
        raw_ca = str(q.get("correct_answer", "")).strip()
        idx = None
        if len(raw_ca) == 1 and raw_ca.upper() in "ABCD" and int("ABCD".index(raw_ca.upper())) < len(clean):
            idx = "ABCD".index(raw_ca.upper())
        else:
            ca_clean = _strip_label(raw_ca)
            for i, o in enumerate(clean):
                if ca_clean == o or raw_ca == str(opts[i]).strip():
                    idx = i
                    break
        if idx is None:
            continue
        qs.append({
            "question": q.get("question", ""),
            "options": clean,
            "correct_answer": clean[idx],
            "explanation": q.get("explanation") if isinstance(q.get("explanation"), str) else None,
        })
    if len(qs) < 2:
        return
    item["questions"] = qs
    item["type"] = "reading"
    db.add(models.DailyExercise(
        user_id=user.id, date=today, exercise_type="reading",
        content=json.dumps(item, ensure_ascii=False), source="reading",
    ))
    db.commit()
    print(f"[reading] generated passage with {len(qs)} questions for user {user.id}")


async def _generate_daily_pool(user, db: Session, today, count: int):
    async with _user_gen_lock(user.id):
        db.commit()  # see rows a parallel request just committed
        if db.query(models.DailyExercise).filter(
            models.DailyExercise.user_id == user.id,
            models.DailyExercise.date == today,
            models.DailyExercise.source.notin_(["bonus", "vocab", "topic", "practice"]),
        ).count() > 0:
            return  # a concurrent request already built today's pool
        return await _generate_daily_pool_inner(user, db, today, count)


async def _generate_daily_pool_inner(user, db: Session, today, count: int):
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

    error_entries = _error_retry_entries(user, db, today, source="new")

    # AI fills whatever is left; reserve ~6 slots for new_vocab(2) and topic_d(~4)
    ai_target = max(count - len(weak_exs) - len(due_vocab) - len(ai_due) - len(error_entries) - 6, count // 4)

    interest_themes_str = _select_interest_themes(prefs)  # max 2 themes, even rotation

    gen_topics = _select_topics_for_generation(user, db)
    topic_id_by_slug = {t.slug: t.id for t in gen_topics}

    entries = list(error_entries)

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
    pool_drawn = _pool_draw(db, user.id, user.level, ai_target,
                            seen_norms=_seen_questions(user.id, db, limit=400),
                            seen_skeletons={sk for sk, n in _seen_skeletons(user.id, db, limit=600).items() if n >= 2},  # only WORN templates (2+); banning every once-seen skeleton left pool_draw with 0 of 423
                            seen_answers=_seen_answers(user.id, db))
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
            # Overshoot ~1.5x: validators/dedups reject 30-50% of raw items; generating
            # exactly `deficit` left sessions short (11/20) once the pool ran dry for the
            # user (he had seen 420 of 423 entries). Extras all land in the pool anyway.
            _generate_exercises(user, min(deficit * 2, deficit + 16), interest_themes_str, topics=gen_topics or None, db=db),
            _generate_topic_exercises_for_daily(user, db, today),
        )
        validated = _validate_batch(generated, user, db, pool_drawn=pool_drawn, label="daily")
        # Save ALL valid exercises to pool (populates shared pool regardless of deficit)
        for item in validated:
            topic_id = topic_id_by_slug.get(item.get("topic_slug"))
            _save_to_pool(item, user.level, topic_id, db)
        # Fill to the FULL session. The fixed 6-slot reserve (4 topic_d + 2 new-vocab)
        # burned empty when topic_d yielded nothing and vocab cards don't count toward
        # the visible session length — the user got 14/20 (#145). Reclaim unused slots
        # from the already-generated surplus (no extra API calls).
        allowed = deficit + max(0, 4 - len(topic_d_entries)) + 2
        ai_added = 0
        for item in validated:
            if ai_added >= allowed:
                break
            topic_id = topic_id_by_slug.get(item.get("topic_slug"))
            pool_id = _save_to_pool(item, user.level, topic_id, db)
            if not _pool_active(db, pool_id):
                continue  # regenerated copy of a reported question — don't serve it
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

    # Top up to the FULL session from the pool. The reserve slots (topic_d + new vocab)
    # can go unused even when deficit==0 — pool covered ai_target, topic_d yielded
    # nothing, vocab cards don't count → 14/20 again (feedback #148). The nightly job
    # keeps the pool stocked, so this draw is cheap.
    countable = sum(1 for e in entries if e.source != "vocab")
    shortfall = count - countable
    if shortfall > 0:
        session_norms = set()
        for e in entries:
            try:
                session_norms.add(_dedup_question_key(json.loads(e.content)))
            except Exception:
                pass
        extra = _pool_draw(db, user.id, user.level, shortfall,
                           seen_norms=_seen_questions(user.id, db, limit=400) | session_norms,
                           seen_skeletons={sk for sk, n in _seen_skeletons(user.id, db, limit=600).items() if n >= 2},
                           seen_answers=_seen_answers(user.id, db))
        for pool_ex in extra:
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
        if extra:
            print(f"[daily_pool] topped up {len(extra)} from pool (shortfall was {shortfall})")

    for entry in entries:
        db.add(entry)
    db.commit()


async def _generate_bonus_pool(user, db: Session, today, count: int):
    async with _user_gen_lock(user.id):
        db.commit()  # see rows a parallel request just committed
        if db.query(models.DailyExercise).filter(
            models.DailyExercise.user_id == user.id,
            models.DailyExercise.date == today,
            models.DailyExercise.source == "bonus",
            models.DailyExercise.is_completed == False,
        ).count() > 0:
            return  # a concurrent request already produced this batch (#122/#124-127)
        return await _generate_bonus_pool_inner(user, db, today, count)


async def _generate_bonus_pool_inner(user, db: Session, today, count: int):
    prefs = user.content_preferences

    # Drill known idioms before generating the main bonus batch
    await _generate_idiom_drill_exercises(user, db, today, source="bonus")

    interest_themes_str = _select_interest_themes(prefs)  # max 2 themes, even rotation

    challenge_level = _next_level(user.level)
    gen_topics = _select_topics_for_generation(user, db)
    topic_id_by_slug = {t.slug: t.id for t in gen_topics}

    # Universal mix (user decision 2026-07-15): bonus carries error-work and vocab
    # cards too, not only fresh AI exercises.
    mix_entries = _error_retry_entries(user, db, today, source="bonus") + \
        _bonus_vocab_entries(user, db, today)
    for e in mix_entries:
        db.add(e)
    count = max(count - len(mix_entries), count // 2)

    # Pool-first: serve unseen bonus exercises from shared pool at challenge level
    pool_drawn = _pool_draw(db, user.id, challenge_level, count,
                            seen_norms=_seen_questions(user.id, db, limit=400),
                            seen_skeletons={sk for sk, n in _seen_skeletons(user.id, db, limit=600).items() if n >= 2},  # only WORN templates (2+); banning every once-seen skeleton left pool_draw with 0 of 423
                            seen_answers=_seen_answers(user.id, db))
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
        # Overshoot ~1.5x — see the daily-pool comment: raw rejects made sessions short
        generated = await _generate_exercises(user, min(deficit * 2, deficit + 16), interest_themes_str, level=challenge_level, topics=gen_topics or None, db=db)
        validated = _validate_batch(generated, user, db, pool_drawn=pool_drawn, label="bonus")
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
            if not _pool_active(db, pool_id):
                continue  # regenerated copy of a reported question — don't serve it
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
