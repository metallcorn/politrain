"""Pure exercise validation/normalization helpers — no DB, no API calls.

Extracted from routers/training.py so they can be unit-tested in isolation.
Every generated exercise passes through the _fix_* chain; a None return discards it.
"""
import random
import re

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

    # Multi-word answer that reuses a word already printed in the question — usually a
    # parenthetical base form like "Ten film jest ___ (interesujący)" with answer
    # "bardziej interesujący". The blank is really two words but one is given away, so the
    # user can't tell the missing word ("bardziej") belongs there (reports #189, #195).
    if len(correct.split()) >= 2:
        ans_words = [w for w in re.findall(r'[a-z]+', c_norm) if len(w) >= 4]
        q_words_norm = re.findall(r'[a-z]+', q_norm)  # strips parens/punctuation
        if any(any(_stem_match(aw, qw) for qw in q_words_norm) for aw in ans_words):
            return None

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
# correct_answer is compared via _strip (diacritics removed) — the set must be in the
# same form, otherwise "muszę"/"mogę"/"chcę" never match and the check is dead code
_MODAL_VERBS_NORM = {_strip(m) for m in _MODAL_VERBS_PL}


def _check_modal_has_infinitive(item: dict) -> bool:
    """If correct_answer is a modal verb, the question must contain an infinitive (-ć/-c)."""
    correct = _strip(item.get("correct_answer", "").rstrip(".?!,;"))
    if correct not in _MODAL_VERBS_NORM:
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
        # same rule as literal "false": no explanation → user can't learn why it's wrong
        if not item.get("explanation"):
            return None
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
    # Answer must be a single word — Mistral sometimes returns a reflexive joined with an
    # underscore ("mycie_się") or a space ("mycie się"); tiles/typing expect one token (report #182)
    if "_" in correct or " " in correct.strip():
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


def _same_word_multiset(user_answer: str, correct_answer: str) -> bool:
    """True when both strings contain the same words (ignoring order/case/punctuation)."""
    u = sorted(_strip(w.rstrip('.?!,;')) for w in (user_answer or "").split() if w.strip())
    c = sorted(_strip(w.rstrip('.?!,;')) for w in (correct_answer or "").split() if w.strip())
    return bool(u) and u == c


def _too_similar(question_norm: str, seen_token_sets: list, threshold: float = 0.7) -> bool:
    """True when question_norm overlaps an already-seen question above `threshold` (Jaccard
    on word sets). Catches near-duplicates that exact-match dedup misses — e.g.
    'это подарок для мамы' vs 'это подарок для моей мамы'. Cheap, Python-only (no prompt
    growth — Mistral has no memory of what it already produced)."""
    toks = set(question_norm.split())
    if len(toks) < 3:
        return False  # too short to judge by overlap
    for s in seen_token_sets:
        if not s:
            continue
        inter = len(toks & s)
        union = len(toks | s)
        if union and inter / union >= threshold:
            return True
    return False
