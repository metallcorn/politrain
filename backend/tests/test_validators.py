# Tests for services/validators.py — pure functions, no DB/API needed.
# Many cases are regressions from real user reports (numbers reference
# generated_exercise_reports / admin_feedback ids, descriptions in CLAUDE.md).
#
# Run: venv/bin/pytest  (from backend/)
import ast
import pathlib

import pytest

from services.validators import (
    _norm, _strip, _validate_type, _sanitize_native_fields, _stem_match,
    _clean_word_hints, _require_word_hints, _check_modal_has_infinitive,
    _fix_flashcard_exercise, _fix_mc_exercise, _fix_fill_blank_exercise,
    _fix_letter_tiles_exercise, _fix_translate_exercise, _fix_judge_sentence_exercise,
    _fix_order_words_exercise, _fix_word_definition_exercise,
    _check_answer, _same_word_multiset, _too_similar, _question_skeleton, _VALID_EXERCISE_TYPES,
)


# ---------- normalization ----------

class TestNorm:
    def test_strip_removes_diacritics_and_lowercases(self):
        assert _strip("Kawę") == "kawe"
        assert _strip("ŻÓŁĆ") == "zolc"

    def test_strip_normalizes_russian_yo(self):
        assert _strip("ёлка") == _strip("елка")

    def test_norm_keeps_diacritics_but_drops_punctuation_and_hyphens(self):
        assert _norm("Kawę.") == "kawę"
        assert _norm("интернет-магазин") == "интернетмагазин"
        assert _norm("  Tak!  ") == "tak"


class TestCheckAnswer:
    def test_exact_match(self):
        assert _check_answer("kawę", "kawę") == (True, False)

    def test_diacritic_only_difference_flags_hint(self):
        assert _check_answer("kawe", "kawę") == (True, True)

    def test_alternatives_separated_by_slash(self):
        assert _check_answer("morela", "morela / абрикос")[0] is True
        assert _check_answer("абрикос", "morela / абрикос")[0] is True

    def test_full_answer_with_slash_not_split_for_mc_clicks(self):
        # multiple_choice sends the entire option text, which may contain ' / '
        assert _check_answer("morela / абрикос", "morela / абрикос") == (True, False)

    def test_wrong_answer(self):
        assert _check_answer("herbata", "kawa") == (False, False)

    def test_case_and_trailing_punctuation_ignored(self):
        assert _check_answer("Kawę.", "kawę") == (True, False)


class TestSameWordMultiset:
    def test_reordered_words_match(self):
        assert _same_word_multiset("po pracy wychodzę z domu", "Wychodzę z domu po pracy.")

    def test_different_words_dont_match(self):
        assert not _same_word_multiset("po pracy wychodzę", "Wychodzę z domu po pracy.")

    def test_empty_is_false(self):
        assert not _same_word_multiset("", "Wychodzę z domu.")


class TestTooSimilar:
    def test_near_duplicate_detected(self):
        seen = [set("это подарок для мамы".split())]
        assert _too_similar("это подарок для моей мамы", seen)

    def test_distinct_questions_pass(self):
        seen = [set("это подарок для мамы".split())]
        assert not _too_similar("вчера я пошёл в кино с другом", seen)

    def test_short_question_never_flagged(self):
        seen = [set("dobry wieczór".split())]
        assert not _too_similar("dobry wieczór", seen)

    def test_empty_seen_passes(self):
        assert not _too_similar("это подарок для мамы", [])


class TestQuestionSkeleton:
    def test_same_opening_different_content_collapse(self):
        a = _question_skeleton("Na stole leży kot.")
        b = _question_skeleton("Na stole leży duża czerwona książka.")
        assert a == b and a == "na stole lezy"

    def test_blank_and_numbers_ignored(self):
        a = _question_skeleton("Nie mam czasu na ___.")
        b = _question_skeleton("Nie mam czasu na tę pracę.")
        assert a == b == "nie mam czasu"

    def test_distinct_openings_differ(self):
        a = _question_skeleton("Idę do sklepu po chleb.")
        b = _question_skeleton("Na stole leży kot.")
        assert a != b

    def test_short_question_empty_skeleton(self):
        assert _question_skeleton("Dobry wieczór.") == ""


# ---------- generic validation ----------

class TestValidateType:
    @pytest.mark.parametrize("t", sorted(_VALID_EXERCISE_TYPES))
    def test_valid_types_pass(self, t):
        assert _validate_type({"type": t}) is not None

    def test_invented_type_discarded(self):
        # Mistral sometimes invents types like "situational"
        assert _validate_type({"type": "situational"}) is None


class TestSanitizeNativeFields:
    def test_dict_explanation_nulled(self):
        # old exercises had {"literal": ..., "real": ...} dicts → Pydantic 500
        item = {"explanation": {"literal": "x", "real": "y"}, "translation": "ок", "hint": None}
        out = _sanitize_native_fields(item, "ru")
        assert out["explanation"] is None
        assert out["translation"] == "ок"

    def test_latin_translation_for_ru_user_nulled(self):
        item = {"translation": "I drink coffee in the morning", "explanation": None, "hint": None}
        assert _sanitize_native_fields(item, "ru")["translation"] is None

    def test_cyrillic_translation_kept(self):
        item = {"translation": "Я пью кофе утром", "explanation": None, "hint": None}
        assert _sanitize_native_fields(item, "ru")["translation"] == "Я пью кофе утром"

    def test_non_ru_user_latin_kept(self):
        item = {"translation": "I drink coffee", "explanation": None, "hint": None}
        assert _sanitize_native_fields(item, "en")["translation"] == "I drink coffee"


# ---------- word hints ----------

class TestStemMatch:
    def test_inflected_form_matches_lemma(self):
        assert _stem_match("zupę", "zupa")
        assert _stem_match("przeciwieństwem", "przeciwieństwo")

    def test_unrelated_words_dont_match(self):
        assert not _stem_match("samochód", "sukienka")

    def test_short_words_require_exact(self):
        assert _stem_match("kot", "kot")
        assert not _stem_match("kot", "kos")


class TestCleanWordHints:
    def test_lemma_key_kept_when_inflected_form_in_question(self):
        item = {"type": "fill_blank", "question": "Lubię zupę pomidorową.",
                "word_hints": {"zupa": "суп"}}
        assert _clean_word_hints(item)["word_hints"] == {"zupa": "суп"}

    def test_bogus_key_dropped(self):
        # 'zubierasz' typo for 'ubierasz' — key not matching any question word
        item = {"type": "fill_blank", "question": "Rano ubierasz się szybko.",
                "word_hints": {"zubierasz": "одеваешься", "rano": "утром"}}
        out = _clean_word_hints(item)
        assert "zubierasz" not in out["word_hints"]
        assert out["word_hints"]["rano"] == "утром"

    def test_all_bogus_becomes_none(self):
        item = {"type": "fill_blank", "question": "Idę do szkoły.",
                "word_hints": {"kompletnie": "совершенно"}}
        assert _clean_word_hints(item)["word_hints"] is None

    def test_translate_hints_always_dropped(self):
        # question is in Russian → hints would reveal the Polish answer
        item = {"type": "translate", "question": "У меня есть кот.",
                "word_hints": {"kot": "кот"}}
        assert _clean_word_hints(item)["word_hints"] is None


class TestRequireWordHints:
    def test_sentence_format_without_hints_rejected(self):
        assert _require_word_hints(
            {"type": "letter_tiles", "question": "Lubię pić ___.", "word_hints": None}) is None

    def test_spelling_format_without_hints_ok(self):
        assert _require_word_hints(
            {"type": "letter_tiles", "question": "Напиши по-польски: счастье", "word_hints": None}) is not None

    def test_sentence_format_with_hints_ok(self):
        assert _require_word_hints(
            {"type": "letter_tiles", "question": "Lubię pić ___.",
             "word_hints": {"lubię": "люблю"}}) is not None

    def test_other_types_untouched(self):
        assert _require_word_hints(
            {"type": "fill_blank", "question": "X ___.", "word_hints": None}) is not None

    def test_none_passthrough(self):
        assert _require_word_hints(None) is None


# ---------- multiple_choice ----------

class TestFixMc:
    def _mc(self, **kw):
        base = {"type": "multiple_choice", "question": "Ona ma ___ sukienkę.",
                "options": ["ładną", "ładny", "ładne", "ładna"], "correct_answer": "ładną"}
        base.update(kw)
        return base

    def test_valid_passes_and_options_preserved_as_set(self):
        out = _fix_mc_exercise(self._mc())
        assert out is not None
        assert sorted(out["options"]) == sorted(["ładną", "ładny", "ładne", "ładna"])

    def test_duplicate_options_rejected(self):
        # report #92: "ładne, ładne, ładny, ładna" — two identical choices
        assert _fix_mc_exercise(self._mc(options=["ładne", "ładne", "ładny", "ładna"],
                                         correct_answer="ładne")) is None

    def test_option_list_leaked_into_question_rejected(self):
        # report #91: "(ładny, ładna, ładne, ładne)" parenthetical in question
        assert _fix_mc_exercise(self._mc(
            question="Ona ma ___ sukienkę. (ładny, ładna, ładne)")) is None

    def test_substring_option_rejected(self):
        assert _fix_mc_exercise(self._mc(options=["-ę", "-ę (без изменения)", "-a", "-o"],
                                         correct_answer="-ę")) is None

    def test_answer_not_in_options_rejected(self):
        assert _fix_mc_exercise(self._mc(correct_answer="piękną")) is None

    def test_diacritic_mismatch_recovered(self):
        out = _fix_mc_exercise(self._mc(correct_answer="ladny"))
        assert out is not None
        assert out["correct_answer"] == "ładny"  # snapped to actual option


# ---------- fill_blank ----------

class TestFixFillBlank:
    def test_perfect_format_kept(self):
        item = {"type": "fill_blank", "question": "Lubię ___ kawę.", "correct_answer": "dobrą"}
        assert _fix_fill_blank_exercise(item) is not None

    def test_two_blanks_rejected(self):
        item = {"type": "fill_blank", "question": "___ lubię ___ kawę.", "correct_answer": "dobrą"}
        assert _fix_fill_blank_exercise(item) is None

    def test_slash_answer_rejected(self):
        item = {"type": "fill_blank", "question": "Lubię ___ kawę.", "correct_answer": "dobrą/dobrej"}
        assert _fix_fill_blank_exercise(item) is None

    def test_answer_in_text_without_blank_gets_blanked(self):
        item = {"type": "fill_blank", "question": "Lubię dobrą kawę.", "correct_answer": "dobrą"}
        out = _fix_fill_blank_exercise(item)
        assert out is not None
        assert out["question"].count("___") == 1
        assert "dobrą" not in out["question"]

    def test_bracket_containing_exact_answer_rejected(self):
        # masculine inanimate biernik: "(telefon)" IS the answer → unanswerable after removal
        item = {"type": "fill_blank", "question": "Kupiłem nowy ___ (telefon).",
                "correct_answer": "telefon"}
        assert _fix_fill_blank_exercise(item) is None

    def test_bracket_leak_with_base_form_removed(self):
        # bracket holds base form + answer leaked elsewhere is removable
        item = {"type": "fill_blank", "question": "Ona ma ___ sukienkę (ładna sukienka, ładną).",
                "correct_answer": "ładną"}
        out = _fix_fill_blank_exercise(item)
        # either fixed (bracket removed) or rejected — must NOT keep the leak
        if out is not None:
            assert "ładną" not in out["question"].replace("___", "")

    def test_modal_answer_without_infinitive_rejected(self):
        item = {"type": "fill_blank", "question": "Jutro ___ do pracy wcześnie rano.",
                "correct_answer": "muszę"}
        assert _fix_fill_blank_exercise(item) is None

    def test_modal_answer_with_infinitive_kept(self):
        item = {"type": "fill_blank", "question": "Jutro ___ wstać wcześnie.",
                "correct_answer": "muszę"}
        assert _fix_fill_blank_exercise(item) is not None

    def test_twoword_answer_reusing_question_word_rejected(self):
        # reports #189/#195: "Ten film jest ___ (interesujący)" answer "bardziej interesujący"
        item = {"type": "fill_blank", "question": "Ten film jest ___ (interesujący) niż poprzedni.",
                "correct_answer": "bardziej interesujący"}
        assert _fix_fill_blank_exercise(item) is None

    def test_singleword_answer_with_parenthetical_base_kept(self):
        # single-word answer differing from the printed base form is fine
        item = {"type": "fill_blank", "question": "Lubię ___ (czarny) kawę.",
                "correct_answer": "czarną"}
        assert _fix_fill_blank_exercise(item) is not None

    def test_interrogative_answer_rejected(self):
        # report #212: "nie ma ___ chleba" → answer "czego" (real answer is "chleba")
        item = {"type": "fill_blank", "question": "Dzisiaj nie ma ___ chleba w sklepie.",
                "correct_answer": "czego"}
        assert _fix_fill_blank_exercise(item) is None

    def test_cyrillic_answer_rejected(self):
        # report #222: answer "в" — can't type Cyrillic in a Polish exercise
        item = {"type": "fill_blank", "question": "Litera 'Ł' wymawia się jak ___.",
                "correct_answer": "в"}
        assert _fix_fill_blank_exercise(item) is None

    def test_glued_blank_rejected(self):
        # report #215: "Ona ma___ samochód" — no real gap, glued token
        item = {"type": "fill_blank", "question": "Ona ma___ samochód.",
                "correct_answer": "ładny"}
        assert _fix_fill_blank_exercise(item) is None


class TestModalInfinitive:
    def test_non_modal_always_ok(self):
        assert _check_modal_has_infinitive({"question": "Lubię ___.", "correct_answer": "kawę"})

    def test_modal_needs_infinitive(self):
        assert not _check_modal_has_infinitive({"question": "Jutro ___ do pracy rano.",
                                                "correct_answer": "muszę"})
        assert _check_modal_has_infinitive({"question": "Jutro ___ wstać wcześnie.",
                                            "correct_answer": "muszę"})


# ---------- letter_tiles ----------

class TestFixLetterTiles:
    def test_valid_sentence_format(self):
        item = {"type": "letter_tiles", "question": "Lubię pić ___ rano.", "correct_answer": "kawę"}
        assert _fix_letter_tiles_exercise(item) is not None

    def test_valid_spelling_format(self):
        item = {"type": "letter_tiles", "question": "Напиши по-польски: счастье",
                "correct_answer": "szczęście"}
        assert _fix_letter_tiles_exercise(item) is not None

    def test_multiword_answer_rejected(self):
        item = {"type": "letter_tiles", "question": "___ dobry!", "correct_answer": "dzień dobry"}
        assert _fix_letter_tiles_exercise(item) is None

    def test_answer_visible_in_question_rejected(self):
        item = {"type": "letter_tiles", "question": "Kawa to ___. Lubię kawę... kawa!",
                "correct_answer": "kawa"}
        assert _fix_letter_tiles_exercise(item) is None


# ---------- translate ----------

class TestFixTranslate:
    def test_short_phrase_ok(self):
        item = {"type": "translate", "question": "У меня нет времени."}
        assert _fix_translate_exercise(item) is not None

    def test_two_sentences_rejected(self):
        item = {"type": "translate", "question": "Привет. Как дела?"}
        assert _fix_translate_exercise(item) is None

    def test_too_long_rejected(self):
        item = {"type": "translate",
                "question": "Это очень длинное предложение которое содержит слишком много слов для перевода на уровне A1 точно"}
        assert _fix_translate_exercise(item) is None


# ---------- judge_sentence ----------

class TestFixJudge:
    def test_true_passes(self):
        item = {"type": "judge_sentence", "question": "Poszedłem do sklepu.",
                "correct_answer": "true"}
        assert _fix_judge_sentence_exercise(item) is not None

    def test_blank_in_question_rejected(self):
        item = {"type": "judge_sentence", "question": "Ja ___ do sklepu.",
                "correct_answer": "false", "explanation": "x"}
        assert _fix_judge_sentence_exercise(item) is None

    def test_false_without_explanation_rejected(self):
        item = {"type": "judge_sentence", "question": "Ja poszedł do sklepu.",
                "correct_answer": "false", "explanation": None}
        assert _fix_judge_sentence_exercise(item) is None

    def test_false_with_explanation_passes(self):
        item = {"type": "judge_sentence", "question": "Ja poszedł do sklepu.",
                "correct_answer": "false", "explanation": "poszedł требует ja → poszedłem"}
        assert _fix_judge_sentence_exercise(item) is not None

    def test_russian_verno_coerced_to_true(self):
        item = {"type": "judge_sentence", "question": "Idę do domu.", "correct_answer": "верно"}
        assert _fix_judge_sentence_exercise(item)["correct_answer"] == "true"

    def test_coerced_false_also_requires_explanation(self):
        # regression: coercion path used to bypass the explanation requirement
        item = {"type": "judge_sentence", "question": "Ja poszedł.", "correct_answer": "неверно",
                "explanation": None}
        assert _fix_judge_sentence_exercise(item) is None

    def test_garbage_answer_rejected(self):
        item = {"type": "judge_sentence", "question": "Idę.", "correct_answer": "maybe"}
        assert _fix_judge_sentence_exercise(item) is None


# ---------- order_words ----------

class TestFixOrderWords:
    def test_matching_words_pass_and_get_shuffled(self):
        item = {"type": "order_words", "question": "To / jest / moja / książka",
                "correct_answer": "To jest moja książka."}
        out = _fix_order_words_exercise(item)
        assert out is not None
        assert sorted(w.lower() for w in out["question"].split(" / ")) == \
               sorted(["to", "jest", "moja", "książka"])

    def test_word_mismatch_rejected(self):
        item = {"type": "order_words", "question": "To / jest / mój / pies",
                "correct_answer": "To jest moja książka."}
        assert _fix_order_words_exercise(item) is None

    def test_ending_with_preposition_rejected(self):
        item = {"type": "order_words", "question": "Idę / szkoły / do",
                "correct_answer": "Idę szkoły do."}
        assert _fix_order_words_exercise(item) is None

    def test_fewer_than_three_words_rejected(self):
        item = {"type": "order_words", "question": "Jestem / tu", "correct_answer": "Jestem tu."}
        assert _fix_order_words_exercise(item) is None

    def test_invalid_alternative_filtered_but_valid_kept(self):
        item = {"type": "order_words", "question": "Idę / do / szkoły",
                "correct_answer": "Idę do szkoły. / Do szkoły idę. / Szkoły idę do."}
        out = _fix_order_words_exercise(item)
        assert out is not None
        alts = out["correct_answer"].split(" / ")
        assert "Idę do szkoły." in alts
        assert "Szkoły idę do." not in alts  # ends with preposition


# ---------- word_definition ----------

class TestFixWordDefinition:
    def test_valid_passes_and_hint_autofilled(self):
        item = {"type": "word_definition",
                "question": "To jest napój, który pije się rano.", "correct_answer": "kawa",
                "hint": None}
        out = _fix_word_definition_exercise(item)
        assert out is not None
        assert out["hint"].startswith("K")

    def test_answer_in_question_rejected(self):
        item = {"type": "word_definition", "question": "Kawa to napój. Co to jest?",
                "correct_answer": "kawa"}
        assert _fix_word_definition_exercise(item) is None

    def test_derivative_stem_leak_rejected(self):
        # real case: question about "aptekarz" reveals answer "apteka"
        item = {"type": "word_definition",
                "question": "Miejsce, gdzie pracuje aptekarz.", "correct_answer": "apteka"}
        assert _fix_word_definition_exercise(item) is None

    def test_slash_answer_rejected(self):
        item = {"type": "word_definition", "question": "Napój z mleka.",
                "correct_answer": "kefir/jogurt"}
        assert _fix_word_definition_exercise(item) is None

    def test_blank_rejected(self):
        item = {"type": "word_definition", "question": "To jest ___.", "correct_answer": "kawa"}
        assert _fix_word_definition_exercise(item) is None

    def test_underscore_joined_answer_rejected(self):
        # report #182: reflexive joined with underscore "mycie_się"
        item = {"type": "word_definition", "question": "Codzienny rytuał rano.",
                "correct_answer": "mycie_się"}
        assert _fix_word_definition_exercise(item) is None

    def test_multiword_answer_rejected(self):
        item = {"type": "word_definition", "question": "Codzienny rytuał rano.",
                "correct_answer": "mycie się"}
        assert _fix_word_definition_exercise(item) is None


# ---------- flashcard (idioms) ----------

class TestFixFlashcard:
    def test_single_word_rejected(self):
        assert _fix_flashcard_exercise(
            {"type": "flashcard", "question": "żółty", "correct_answer": "жёлтый"}) is None

    def test_short_verbless_phrase_rejected(self):
        # "zielone drzewo" is not an idiom — regression for the shadowed-validator bug
        assert _fix_flashcard_exercise(
            {"type": "flashcard", "question": "zielone drzewo", "correct_answer": "зелёное дерево"}) is None

    def test_real_idiom_with_verb_passes(self):
        item = {"type": "flashcard", "question": "mieć muchy w nosie",
                "correct_answer": "быть не в духе", "translation": "быть не в духе"}
        assert _fix_flashcard_exercise(item) is not None

    def test_blank_rejected(self):
        assert _fix_flashcard_exercise(
            {"type": "flashcard", "question": "mieć ___ w nosie", "correct_answer": "x"}) is None

    def test_polish_answer_swapped_for_translation(self):
        item = {"type": "flashcard", "question": "rzucać grochem o ścianę",
                "correct_answer": "rzucać grochem o ścianę",
                "translation": "как об стенку горох"}
        out = _fix_flashcard_exercise(item)
        assert out is not None
        assert out["correct_answer"] == "как об стенку горох"

    def test_polish_answer_without_translation_rejected(self):
        item = {"type": "flashcard", "question": "rzucać grochem o ścianę",
                "correct_answer": "rzucać grochem o ścianę", "translation": ""}
        assert _fix_flashcard_exercise(item) is None


# ---------- meta: duplicate top-level defs (the bug that hid a dead validator) ----------

BACKEND = pathlib.Path(__file__).resolve().parents[1]

@pytest.mark.parametrize("path", sorted(
    p for d in ("routers", "services", ".")
    for p in (BACKEND / d).glob("*.py")
))
def test_no_duplicate_toplevel_defs(path):
    """Two defs with the same name silently shadow each other — this killed
    _fix_flashcard_exercise once (strict validator was dead code for weeks)."""
    tree = ast.parse(path.read_text())
    names = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    dupes = {n for n in names if names.count(n) > 1}
    assert not dupes, f"{path.name}: duplicate top-level defs: {dupes}"
