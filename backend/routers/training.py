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
from services.sm2 import calculate_next_review
from services.gamification import (
    add_xp, XP_CORRECT, XP_INCORRECT, XP_VOCAB, XP_VOCAB_NEW, XP_VOCAB_REVIEW, XP_COMPLETE_SESSION,
    check_achievements, update_daily_activity, update_streak
)

_DIACRITIC_MAP = str.maketrans('ąćęłńóśźżĄĆĘŁŃÓŚŹŻ', 'acelnoszz' 'ACELNOSZZ')
# ё and е are interchangeable in Russian — normalize ё→е
_YO_MAP = str.maketrans('ёЁ', 'еЕ')

def _strip(text: str) -> str:
    return text.strip().lower().translate(_DIACRITIC_MAP).translate(_YO_MAP)

def _norm(text: str) -> str:
    """Normalize for comparison: strip whitespace, trailing punctuation, lowercase, remove hyphens."""
    return text.strip().rstrip('.?!,;').strip().lower().replace('-', '').translate(_YO_MAP)


_VALID_EXERCISE_TYPES = {"fill_blank", "multiple_choice", "flashcard", "translate", "order_words", "judge_sentence", "letter_tiles", "word_definition"}

def _validate_type(item: dict) -> dict | None:
    """Discard exercises with unsupported types (e.g. 'situational')."""
    return item if item.get("type") in _VALID_EXERCISE_TYPES else None


_CYRILLIC_RE = re.compile(r'[а-яёА-ЯЁ]')

def _sanitize_native_fields(item: dict, native_language: str) -> dict:
    """If native_language expects Cyrillic (ru) but translation/explanation are in Latin, null them out.
    Also nulls out any field that is a dict instead of a string (Mistral sometimes returns nested objects)."""
    for field in ("translation", "explanation", "hint"):
        val = item.get(field)
        if val is not None and not isinstance(val, str):
            item[field] = None
    if native_language != "ru":
        return item
    for field in ("translation", "explanation", "hint"):
        val = item.get(field)
        if val and isinstance(val, str) and len(val) > 4 and not _CYRILLIC_RE.search(val):
            item[field] = None
    return item


_PL_VERB_ENDINGS = re.compile(
    r'\b\w+(?:ić|yć|ać|eć|ować|nąć|wać|mieć|być|wiedzieć|móc|chcieć|iść|jść)\b'
    r'|\b(?:mieć|być|robić|wziąć|brać|dać|mówić|pójść|iść|widzieć|wiedzieć|mówi|jest|ma|idzie|robi|'
    r'ma|mam|masz|jest|są|idę|pójdę|mogę|chcę|wiem)\b',
    re.IGNORECASE
)

def _fix_flashcard_exercise(item: dict) -> dict | None:
    """Validate idiom flashcards. Single merged validator (do NOT redefine below).

    Rejects:
    - missing question/answer, or a blank (___) → that's a fill_blank, not a flashcard
    - single words/letters and short verbless phrases (zielone drzewo, czerwony) — not idioms
    Fixes:
    - if correct_answer is still Polish (== question or no Cyrillic), swap in the translation
    """
    if item.get("type") != "flashcard":
        return item
    question = (item.get("question") or "").strip()
    correct = (item.get("correct_answer") or "").strip()
    translation = (item.get("translation") or "").strip()
    if not question or not correct:
        return None
    # Flashcard question must not contain a blank — that's a fill_blank
    if "___" in question:
        return None
    # Idiom shape check: reject single words and short verbless phrases
    words = question.split()
    if len(words) < 2:
        return None
    if len(words) <= 3 and not _PL_VERB_ENDINGS.search(question):
        return None
    # If correct_answer is identical to question, it's still Polish — use translation as the answer
    if correct.lower() == question.lower():
        if translation and translation.lower() != question.lower():
            item["correct_answer"] = translation
            return item
        return None
    # If correct_answer looks Polish (no Cyrillic) but translation has Cyrillic, swap
    has_cyr = lambda s: bool(re.search(r'[а-яёА-ЯЁ]', s))
    if not has_cyr(correct) and has_cyr(translation):
        item["correct_answer"] = translation
    return item


_PL_WORD_RE = re.compile(r'[a-ząęóśćźżńł]+', re.IGNORECASE)

def _stem_match(a: str, b: str) -> bool:
    """True if a and b are the same word modulo Polish inflection (shared prefix, differ only in suffix)."""
    m = min(len(a), len(b))
    if m < 4:
        return a == b
    cp = 0
    while cp < len(a) and cp < len(b) and a[cp] == b[cp]:
        cp += 1
    return cp >= 3 and cp >= m - 3

def _clean_word_hints(item: dict) -> dict:
    """Drop word_hints keys that don't correspond to a word actually in the question (typos like
    'zubierasz' for 'ubierasz', mismatches). Multi-word keys require all their parts present.
    For translate the question is in the user's language and hints would give away the answer — drop entirely."""
    wh = item.get("word_hints")
    if not isinstance(wh, dict) or not wh:
        return item
    if item.get("type") == "translate":
        item["word_hints"] = None
        return item
    q_words = [w.lower() for w in _PL_WORD_RE.findall(item.get("question", ""))]
    def key_ok(key):
        parts = [p.lower() for p in _PL_WORD_RE.findall(key)]
        return bool(parts) and all(any(_stem_match(p, qw) for qw in q_words) for p in parts)
    cleaned = {k: v for k, v in wh.items() if key_ok(k)}
    item["word_hints"] = cleaned or None
    return item


def _require_word_hints(item: dict | None) -> dict | None:
    """letter_tiles in sentence format (___) without clickable word translations is a UX dead
    end — the user can't understand the Polish sentence (feedback #93). Spelling format
    ('Напиши по-польски: …', no ___) has a native-language question and needs no hints.
    Runs AFTER _clean_word_hints so exercises whose hints were all bogus are rejected too."""
    if item and item.get("type") == "letter_tiles" and "___" in item.get("question", "") \
            and not item.get("word_hints"):
        return None
    return item


def _fix_mc_exercise(item: dict) -> dict | None:
    """Ensure multiple_choice correct_answer exactly matches one of the options. Returns None if unfixable."""
    if item.get("type") != "multiple_choice":
        return item
    opts = item.get("options") or []
    ca = item.get("correct_answer", "")
    if not opts or not ca:
        return None

    opts_stripped = [str(o).strip() for o in opts]

    # Reject exact-duplicate options (e.g. ["ładne","ładne","ładny","ładna"] — two identical choices).
    seen = [o.lower() for o in opts_stripped]
    if len(seen) != len(set(seen)):
        return None

    # Reject when the option list leaked into the question as a parenthetical
    # (e.g. "Ona ma ___ sukienkę. (ładny, ładna, ładne, ładne)" — meta-annotation, confusing).
    question = item.get("question", "")
    for paren in re.findall(r'\(([^)]*)\)', question):
        listed = [p.strip().lower() for p in re.split(r'[,/]', paren) if p.strip()]
        if len(listed) >= 2 and sum(1 for o in seen if o in listed) >= 2:
            return None

    # Reject if any option is a strict substring of another option (same words with added commentary).
    # Catches "-ę" vs "-ę (без изменения)" but NOT jabłko/jabłka/jabłku (different endings).
    for i, o1 in enumerate(opts_stripped):
        for j, o2 in enumerate(opts_stripped):
            if i != j and o1 and o1 in o2 and o1 != o2:
                return None

    if ca in opts:
        random.shuffle(opts)
        item["options"] = opts
        return item
    # Try case-insensitive / diacritic-normalized match
    ca_norm = _strip(ca)
    for opt in opts:
        if _strip(opt) == ca_norm:
            item["correct_answer"] = opt
            random.shuffle(opts)
            item["options"] = opts
            return item
    # correct_answer not in options at all — discard
    return None


def _fix_fill_blank_exercise(item: dict) -> dict | None:
    """Ensure fill_blank has exactly one ___ and the answer isn't already visible in the question."""
    if item.get("type") != "fill_blank":
        return item
    question = item.get("question", "")
    correct = item.get("correct_answer", "").strip()
    if not question or not correct:
        return None

    # Multiple blanks or slash-separated answers → ambiguous, discard
    if question.count("___") > 1:
        return None
    if "/" in correct and len(correct.split("/")) > 1:
        return None

    has_blank = "___" in question
    # Normalize diacritics for reliable leak detection; use word boundaries to avoid
    # false positives when a short answer is a substring of another word.
    c_norm = _strip(correct)
    q_norm = _strip(question)
    answer_leaked = bool(re.search(r'\b' + re.escape(c_norm) + r'\b', q_norm))

    if has_blank and not answer_leaked:
        if not _check_modal_has_infinitive(item):
            return None  # modal verb answer but no infinitive in question — incomplete sentence
        return item  # perfect format

    def _remove_group(m):
        return '' if re.search(r'\b' + re.escape(c_norm) + r'\b', _strip(m.group(0))) else m.group(0)

    if not has_blank and answer_leaked:
        # No blank but answer is in the text — replace first occurrence with ___
        fixed = re.sub(re.escape(correct), "___", question, count=1, flags=re.IGNORECASE)
        if "___" not in fixed:
            # Diacritic mismatch: find word by normalized form and replace it
            for word in re.findall(r'\S+', question):
                if _strip(word.rstrip('.?!,;')) == c_norm:
                    fixed = question.replace(word, "___", 1)
                    break
        if "___" in fixed:
            item["question"] = fixed
            if not _check_modal_has_infinitive(item):
                return None
            return item
        return None

    if has_blank and answer_leaked:
        # If any bracket literally contains the exact answer, the bracket IS the hint
        # and removing it leaves an unanswerable exercise (e.g. "nowy ___ (telefon)" → A=telefon).
        # This also catches masculine inanimate nouns in biernik that don't change form.
        bracket_contents = re.findall(r'\(([^)]+)\)', question) + re.findall(r'\[([^\]]+)\]', question)
        if any(_strip(b.strip()) == c_norm for b in bracket_contents):
            return None
        # Otherwise remove the bracket group that reveals the answer
        fixed = re.sub(r'\([^)]*\)', _remove_group, question).strip()
        fixed = re.sub(r'\[[^\]]*\]', _remove_group, fixed).strip()
        if not re.search(r'\b' + re.escape(c_norm) + r'\b', _strip(fixed)):
            item["question"] = fixed
            return item
        return None  # can't fix — discard

    # No blank and answer not in question at all — can't build a proper exercise
    return None


_MODAL_VERBS_PL = {
    "muszę", "musisz", "musi", "musimy", "musicie", "muszą",
    "mogę", "możesz", "może", "możemy", "możecie", "mogą",
    "chcę", "chcesz", "chce", "chcemy", "chcecie", "chcą",
    "powinienem", "powinnam", "powinieneś", "powinnaś",
    "powinien", "powinna", "powinniśmy", "powinnyśmy",
    "powinniście", "powinnyście", "powinni", "powinny",
    "trzeba", "warto", "wolno", "można",
    "staram", "stara", "staramy",
}


def _check_modal_has_infinitive(item: dict) -> bool:
    """If correct_answer is a modal verb, the question must contain an infinitive (-ć/-c)."""
    correct = _strip(item.get("correct_answer", "").rstrip(".?!,;"))
    if correct not in _MODAL_VERBS_PL:
        return True  # not a modal — no check needed
    question = item.get("question", "")
    # An infinitive ends in -ć or -c (e.g. przyjść, być, pracować, móc)
    return bool(re.search(r'\w+[ćc]\b', question, re.IGNORECASE))


def _fix_letter_tiles_exercise(item: dict) -> dict | None:
    """Validate letter_tiles: single-word answer, answer not visible in question.
    Two valid formats:
    A) Sentence with exactly one ___ (tests word form in context)
    B) Spelling question without ___ e.g. 'Напиши по-польски: школа' (tests pure spelling)
    """
    if item is None or item.get("type") != "letter_tiles":
        return item
    question = item.get("question", "")
    correct = (item.get("correct_answer") or "").strip()
    if not question or not correct:
        return None
    if " " in correct:
        return None  # multi-word answer can't be assembled from tiles
    blank_count = question.count("___")
    if blank_count > 1:
        return None  # multiple blanks not supported
    c_norm = _strip(correct)
    q_norm = _strip(question)
    if re.search(r'\b' + re.escape(c_norm) + r'\b', q_norm):
        return None  # answer visible in question
    return item


def _fix_translate_exercise(item: dict) -> dict | None:
    """Ensure translate exercises are a single short sentence (≤12 words)."""
    if item.get("type") != "translate":
        return item
    question = (item.get("question") or "").strip()
    if not question:
        return None
    # Reject if multiple sentences (contains . or ! or ? in the middle)
    sentences = re.split(r'[.!?]+', question)
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) > 1:
        return None
    # Reject if too many words
    if len(question.split()) > 12:
        return None
    return item


def _fix_judge_sentence_exercise(item: dict) -> dict | None:
    """Ensure judge_sentence has correct_answer of 'true' or 'false' and no blanks."""
    if item.get("type") != "judge_sentence":
        return item
    if "___" in (item.get("question") or ""):
        return None
    ca = str(item.get("correct_answer", "")).strip().lower()
    if ca in ("true", "false"):
        item["correct_answer"] = ca
        # Reject false exercises without explanation — user can't learn why it's wrong
        if ca == "false" and not item.get("explanation"):
            return None
        return item
    # Try to coerce common variants
    if ca in ("yes", "да", "верно", "правильно", "correct"):
        item["correct_answer"] = "true"
        return item
    if ca in ("no", "нет", "неверно", "неправильно", "incorrect", "wrong"):
        item["correct_answer"] = "false"
        return item
    return None


def _fix_order_words_exercise(item: dict) -> dict | None:
    """Validate that question words match correct_answer words (all alternatives), then shuffle."""
    if item.get("type") != "order_words":
        return item
    question = item.get("question", "")
    correct = item.get("correct_answer", "")
    if not question or not correct:
        return None

    # Extract words from question (split by /)
    raw_words = [w.strip() for w in question.split("/") if w.strip()]
    q_words = sorted(_strip(re.sub(r'\(.*?\)', '', w).rstrip('.?!,;')) for w in raw_words)
    q_words = [w for w in q_words if w]

    # Support multiple valid orderings separated by ' / '
    # Each alternative must contain exactly the same word set as the question
    alternatives = [a.strip() for a in correct.split(' / ') if a.strip()]
    valid_alternatives = []
    _PL_CLAUSE_ENDS = {"na", "w", "do", "z", "ze", "od", "po", "przy", "nad", "pod",
                       "przed", "za", "przez", "o", "u", "dla", "bez", "i", "a", "ale",
                       "że", "czy", "bo", "lub", "albo", "ani"}
    for alt in alternatives:
        a_words = sorted(_strip(w.rstrip('.?!,;')) for w in alt.split() if w.strip())
        a_words = [w for w in a_words if w]
        if not a_words or a_words != q_words:
            continue
        last_word = alt.rstrip('.?!,;').split()[-1].lower() if alt.split() else ""
        if last_word in _PL_CLAUSE_ENDS:
            continue
        valid_alternatives.append(alt)

    if not valid_alternatives:
        return None

    # Require at least 3 words
    first_alt_words = valid_alternatives[0].split()
    if len(first_alt_words) < 3:
        return None

    item["correct_answer"] = " / ".join(valid_alternatives)

    # Shuffle words so they're not in the same order as any alternative
    shuffled = raw_words[:]
    for _ in range(10):
        random.shuffle(shuffled)
        shuffled_str = " ".join(shuffled).lower()
        if not any(shuffled_str == alt.lower().rstrip('.?!,;') for alt in valid_alternatives):
            break
    item["question"] = " / ".join(shuffled)
    return item


def _fix_word_definition_exercise(item: dict) -> dict | None:
    """Validate word_definition: no blank in question, single answer not visible in question."""
    if item is None or item.get("type") != "word_definition":
        return item
    question = (item.get("question") or "").strip()
    correct = (item.get("correct_answer") or "").strip()
    if not question or not correct:
        return None
    if "___" in question:
        return None
    if "/" in correct:
        return None
    c_norm = _strip(correct)
    q_norm = _strip(question)
    if re.search(r'\b' + re.escape(c_norm) + r'\b', q_norm):
        return None
    # Check word stem: if answer minus last char appears in question, likely a derivative is used
    if len(c_norm) >= 5 and c_norm[:-1] in q_norm:
        return None
    # Fallback hint: at least first letter if Mistral skipped it
    if not item.get("hint"):
        item["hint"] = correct[0].upper() + "..."
    return item


def _check_answer(user: str, correct: str) -> tuple[bool, bool]:
    """Returns (is_correct, diacritic_hint). diacritic_hint=True means correct only without diacritics.
    Handles multiple acceptable answers separated by ' / '.
    Always checks the full correct_answer first so multiple_choice clicks (which send the full
    option text including ' / ') are not incorrectly split and rejected."""
    candidates = [correct] + [a.strip() for a in correct.split(' / ') if a.strip()]
    seen = set()
    for alt in candidates:
        if alt in seen:
            continue
        seen.add(alt)
        u = _norm(user)
        c = _norm(alt)
        if u == c:
            return True, False
        if _strip(user).rstrip('.?!,;') == _strip(alt).rstrip('.?!,;'):
            return True, True
    return False, False

router = APIRouter(prefix="/training", tags=["training"])

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


def _pool_draw(db: Session, user_id: int, level: str, count: int) -> list:
    """Draw up to count unseen active exercises from the shared pool for this user at this level."""
    seen_sq = db.query(models.DailyExercise.pool_exercise_id).filter(
        models.DailyExercise.user_id == user_id,
        models.DailyExercise.pool_exercise_id.isnot(None),
    ).subquery()
    return db.query(models.ExercisePool).filter(
        models.ExercisePool.level == level,
        models.ExercisePool.is_active == True,
        models.ExercisePool.id.notin_(seen_sq),
    ).order_by(func.random()).limit(count).all()


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
                    models.DailyExercise.source.in_(["bonus", "new", "topic", "topic_d"]),
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
                _enrich(content, de)
                exercises.append(content)
            except Exception:
                pass

        # Fallback to DB if Mistral failed
        if len(exercises) < count:
            already_seen = {
                h.exercise_id for h in db.query(models.UserExerciseHistory).filter(
                    models.UserExerciseHistory.user_id == current_user.id
                ).limit(200).all() if h.exercise_id
            }
            need = count - len(exercises)
            db_exercises = db.query(models.Exercise).filter(
                models.Exercise.level == current_user.level,
                models.Exercise.is_flagged == False,
                models.Exercise.id.notin_(already_seen),
            ).limit(need).all()
            # If all level exercises have been seen, allow repeats (but still exclude flagged)
            if not db_exercises:
                db_exercises = db.query(models.Exercise).filter(
                    models.Exercise.level == current_user.level,
                    models.Exercise.is_flagged == False,
                ).limit(need).all()
            for ex in db_exercises:
                opts = None
                if ex.options:
                    try:
                        opts = json.loads(ex.options)
                    except Exception:
                        pass
                exercises.append({
                    "id": ex.id, "type": ex.type, "question": ex.question,
                    "correct_answer": ex.correct_answer, "options": opts,
                    "hint": ex.hint, "explanation": ex.explanation, "source": "db",
                })

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
        uncompleted = db.query(models.DailyExercise).filter(
            models.DailyExercise.user_id == current_user.id,
            models.DailyExercise.date == today,
            models.DailyExercise.source == "topic",
            models.DailyExercise.topic_id == topic_obj.id,
            models.DailyExercise.is_completed == False,
        ).count()
        if uncompleted == 0:
            await _generate_topic_pool(current_user, topic_obj, db, today, count)
        topic_daily = db.query(models.DailyExercise).filter(
            models.DailyExercise.user_id == current_user.id,
            models.DailyExercise.date == today,
            models.DailyExercise.source == "topic",
            models.DailyExercise.topic_id == topic_obj.id,
            models.DailyExercise.is_completed == False,
        ).all()
        for de in topic_daily:
            try:
                content = json.loads(de.content)
                content["daily_exercise_id"] = de.id
                content["source"] = de.source
                _enrich(content, de)
                exercises.append(content)
            except Exception:
                pass

    elif mode == "practice":
        # Review/consolidation: ONLY correctly answered AI exercises from past 60 days.
        # Incorrectly answered exercises stay in errors mode until fixed there.
        # No daily limit — can be done multiple times.
        cutoff = datetime.utcnow() - timedelta(days=60)
        completed_ai = db.query(models.DailyExercise).filter(
            models.DailyExercise.user_id == current_user.id,
            models.DailyExercise.is_completed == True,
            models.DailyExercise.is_correct == True,
            models.DailyExercise.source.in_(["new", "bonus", "review_ai", "topic_d"]),
            models.DailyExercise.content.isnot(None),
            models.DailyExercise.completed_at >= cutoff,
        ).order_by(func.random()).limit(count).all()

        for de in completed_ai:
            try:
                content = json.loads(de.content)
                content["daily_exercise_id"] = de.id
                content["source"] = "practice"
                _enrich(content, de)
                exercises.append(content)
            except Exception:
                pass

        # Also include curriculum exercises answered correctly at least once (not errors, not mastered)
        mastered_ids = _mastered_exercise_ids(current_user.id, db)
        latest_sq2 = (
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
        correct_hist = (
            db.query(models.UserExerciseHistory)
            .join(latest_sq2, (models.UserExerciseHistory.exercise_id == latest_sq2.c.exercise_id)
                  & (models.UserExerciseHistory.created_at == latest_sq2.c.last_at))
            .join(models.Exercise, models.UserExerciseHistory.exercise_id == models.Exercise.id)
            .filter(
                models.UserExerciseHistory.user_id == current_user.id,
                models.UserExerciseHistory.is_correct == True,
                models.Exercise.is_flagged == False,
                ~models.Exercise.id.in_(mastered_ids) if mastered_ids else True,
            )
            .order_by(func.random())
            .limit(5).all()
        )
        for h in correct_hist:
            ex = db.query(models.Exercise).filter(models.Exercise.id == h.exercise_id).first()
            if ex:
                opts = None
                if ex.options:
                    try:
                        opts = json.loads(ex.options)
                    except Exception:
                        pass
                exercises.append({
                    "id": ex.id, "type": ex.type, "question": ex.question,
                    "correct_answer": ex.correct_answer, "options": opts,
                    "hint": ex.hint, "explanation": ex.explanation, "source": "practice",
                })

        random.shuffle(exercises)
        exercises = exercises[:count]

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

                if ex_type == "translate":
                    is_correct, diacritic_hint = _check_answer(body.user_answer, correct_answer)
                    if not is_correct:
                        is_correct = await _check_translation(
                            body.user_answer, correct_answer,
                            content.get("question", ""),
                            current_user
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
                de.completed_at = datetime.utcnow()

                # XP mode for vocab cards (flashcard OR letter_tiles tied to a vocab word)
                if de.source == "vocab":
                    _vocab_mode = "vocab_session"  # vocab session — small XP
                elif ex_type in ("flashcard", "letter_tiles") and content.get("vocab_id"):
                    _vocab_mode = "reduced"   # SRS vocab in daily review — easier than exercises

                # SRS scheduling for AI exercises
                if de.source in ("new", "bonus", "review_ai"):
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
                    prog.score = (old_score * old_att + (1.0 if is_correct else 0.0)) / (old_att + 1)
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
                                prog.score = (old_score * old_att + (1.0 if is_correct else 0.0)) / (old_att + 1)
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
                    exercise.question, current_user
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
                progress.score = (old_score * old_attempts + result) / (old_attempts + 1)
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

    if diacritic_hint and _vocab_mode == "normal":
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
            # Deactivate pool exercise so no other user sees it
            if de.pool_exercise_id:
                pool_ex = db.query(models.ExercisePool).filter(
                    models.ExercisePool.id == de.pool_exercise_id
                ).first()
                if pool_ex:
                    pool_ex.report_count = (pool_ex.report_count or 0) + 1
                    if pool_ex.report_count >= 2:
                        pool_ex.is_active = False
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
        models.DailyExercise.source.in_(["bonus", "new", "topic", "topic_d"]),
        models.DailyExercise.completed_at.isnot(None),
        models.DailyExercise.completed_at >= ai_cutoff,
    ).count()
    vocab_errors = db.query(models.UserVocabulary).filter(
        models.UserVocabulary.user_id == current_user.id,
        models.UserVocabulary.correct_streak == 0,
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
    return {
        "total_exercises": total,
        "correct": correct,
        "errors": total_errors,
        "accuracy": round(correct / total * 100, 1) if total > 0 else 0,
        "today_done": daily_done,
        "today_total": daily_total,
    }


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
        "fill_blank": "вставить пропущенное слово",
        "multiple_choice": "выбрать правильный вариант",
        "translate": "перевод",
        "order_words": "составить предложение",
        "judge_sentence": "верно / неверно",
        "letter_tiles": "собрать слово из букв",
        "flashcard": "карточка",
        "word_definition": "угадай слово по описанию",
    }

    if level == 1:
        system = (
            f"Ты учитель польского языка. "
            f"Ученик: уровень польского {current_user.level}, родной язык: {current_user.native_language}.\n\n"
            "Объясни результат конкретного упражнения — кратко, 3-5 предложений, без вступлений.\n\n"
            "Структура ответа:\n"
            "0. Если в задании есть польское предложение — выведи его перевод на "
            f"{current_user.native_language} в начале (одной строкой, курсивом через *).\n"
            "   Если перевод уже дан в поле «Перевод задания» — используй его.\n"
            "1. Почему ответ верный или неверный — со ссылкой на конкретное правило польского языка.\n"
            "   Для типа «верно/неверно»: укажи КОНКРЕТНОЕ слово или форму, которая делает предложение\n"
            "   верным или неверным. Не рассуждай о теме вообще — только про эту ошибку.\n"
            "2. Как это правило работает и как его запомнить.\n"
            "3. Только если ответ ученика объективно тоже грамматически верен — честно скажи об этом.\n"
            "   Если же ответ ученика неверен — не упоминай тему ошибок в заданиях вообще.\n\n"
            f"Отвечай на {current_user.native_language}. Польские слова и формы оставляй в польском."
        )
        max_tokens = 500
    else:
        system = (
            f"Ты учитель польского языка. "
            f"Ученик: уровень польского {current_user.level}, родной язык: {current_user.native_language}.\n\n"
            "Ученик уже получил краткое объяснение и хочет разобраться глубже. "
            "Дай развёрнутое объяснение с примерами — 8-12 предложений.\n\n"
            "Структура ответа:\n"
            "1. Полная формулировка правила, включая исключения\n"
            "2. **2-3 живых примера** с переводом, демонстрирующих правило\n"
            "3. Типичные ошибки которые делают изучающие — и как их избежать\n"
            "4. Мнемоника или аналогия с {native_language} если есть\n\n"
            "Используй markdown-форматирование: **жирный** для терминов, списки для примеров.\n"
            f"Отвечай на {current_user.native_language}. Польские слова и формы оставляй в польском."
        ).replace("{native_language}", current_user.native_language)
        max_tokens = 900

    result_label = "правильно ✓" if data.is_correct else "неправильно ✗"
    user_msg = (
        f"Тип задания: {type_labels.get(data.exercise_type, data.exercise_type)}\n"
        f"Вопрос: {data.question}\n"
        f"Правильный ответ: {data.correct_answer}\n"
        f"Ответ ученика: {data.user_answer or '(ничего не введено)'}\n"
        f"Засчитано: {result_label}\n"
    )
    if data.translation:
        user_msg += f"Перевод задания: {data.translation}\n"
    if data.explanation:
        user_msg += f"Пояснение в задании: {data.explanation}\n"

    try:
        text = await mistral.simple_prompt(
            system=system,
            user=user_msg,
            temperature=0.3,
            max_tokens=max_tokens,
            timeout=25.0,
            retries=1,
            model="mistral-small-latest",
            purpose="explain",
            user_id=current_user.id,
        )
        text = text.strip()
    except Exception:
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
    db.add(models.SessionRating(
        user_id=current_user.id,
        mode=data.mode,
        rating=data.rating,
        comment=data.comment or None,
        exercise_ids=_json.dumps(data.exercise_ids) if data.exercise_ids else None,
    ))
    db.commit()
    return {"ok": True}


async def _check_translation(user_answer: str, correct_answer: str, question: str, user) -> bool:
    if user_answer.strip().lower() == correct_answer.strip().lower():
        return True
    prompt = prompts.TRANSLATION_CHECK_PROMPT.format(
        level=user.level,
        native_language=user.native_language,
        source_text=question,
        user_answer=user_answer,
        correct_answer=correct_answer,
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
    user's order is also grammatical/natural Polish (word order is largely free)."""
    try:
        raw = await mistral.simple_prompt(
            system="You are a Polish language checker. Respond only with JSON.",
            user=prompts.WORD_ORDER_CHECK_PROMPT.format(
                correct_answer=correct_answer,
                user_answer=user_answer,
                translation=translation or "",
            ),
            temperature=0.1,
            max_tokens=100,
            retries=2,
            model="mistral-small-latest",
            purpose="order_check",
            user_id=user.id,
        )
        result = await mistral.parse_json_response(raw)
        return bool(result.get("correct", False))
    except Exception:
        return False


def _same_word_multiset(user_answer: str, correct_answer: str) -> bool:
    """True when both strings contain the same words (ignoring order/case/punctuation)."""
    u = sorted(_strip(w.rstrip('.?!,;')) for w in (user_answer or "").split() if w.strip())
    c = sorted(_strip(w.rstrip('.?!,;')) for w in (correct_answer or "").split() if w.strip())
    return bool(u) and u == c


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
    return grammar_gen + lexical_gen + judge_gen + tiles_gen + word_def_gen + idiom_gen


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
    pool_drawn = _pool_draw(db, user.id, user.level, ai_target)
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
    pool_drawn = _pool_draw(db, user.id, challenge_level, count)
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
