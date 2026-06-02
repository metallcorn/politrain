import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user
import models
import schemas
import prompts
from services import mistral

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

_placement_cache: dict = {}

_DIACRITIC_MAP = str.maketrans('ąćęłńóśźżĄĆĘŁŃÓŚŹŻ', 'acelnoszzACELNOSZZ')
_LETTER_IDX = {'a': 0, 'b': 1, 'c': 2, 'd': 3}


def _norm(s: str) -> str:
    return s.strip().lower().translate(_DIACRITIC_MAP)


def _score_option(q: dict, user_ans: str) -> bool:
    """Check if user_ans is the correct answer, handling various Mistral output formats."""
    if not user_ans:
        return False
    correct_raw = q.get("correct_answer", "")
    options = q.get("options", [])

    # Direct normalized match (handles diacritics + case)
    if _norm(user_ans) == _norm(correct_raw):
        return True

    # Mistral sometimes returns letter index as correct_answer (A / B / C / D)
    key = correct_raw.strip().lower().rstrip('.').rstrip(')')
    if key in _LETTER_IDX and options:
        idx = _LETTER_IDX[key]
        if idx < len(options):
            return _norm(user_ans) == _norm(options[idx])

    # Partial: user_ans appears inside correct_answer or vice versa (strip letter prefix)
    if options:
        for opt in options:
            if _norm(opt) == _norm(user_ans) and _norm(opt) in _norm(correct_raw):
                return True

    return False


@router.get("/status")
def onboarding_status(current_user: models.User = Depends(get_current_user)):
    return {"onboarding_done": current_user.onboarding_done, "level": current_user.level}


@router.post("/settings")
def save_settings(
    body: schemas.OnboardingSettings,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    current_user.native_language = body.native_language
    current_user.target_language = body.target_language
    db.commit()
    return {"ok": True}


@router.get("/placement-test")
async def get_placement_test(current_user: models.User = Depends(get_current_user)):
    lang = current_user.native_language
    try:
        raw = await mistral.simple_prompt(
            system="You are a Polish language placement test generator. Generate exactly 10 questions.",
            user=prompts.PLACEMENT_TEST_PROMPT.format(native_language=lang),
            temperature=0.5,
            max_tokens=3000,
        )
        questions = await mistral.parse_json_response(raw)
        _placement_cache[current_user.id] = questions
        return {"questions": questions}
    except Exception:
        # Fallback static test
        questions = _get_static_placement_test(lang)
        _placement_cache[current_user.id] = questions
        return {"questions": questions}


@router.post("/placement-test", response_model=schemas.PlacementTestResult)
async def submit_placement_test(
    body: schemas.PlacementTestSubmit,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    questions = _placement_cache.get(current_user.id, _get_static_placement_test(current_user.native_language))

    # Normalize keys to str to handle both int and str ids from Mistral
    answers_map = {str(a.question_id): a.answer for a in body.answers}
    correct = 0
    for q in questions:
        user_ans = answers_map.get(str(q["id"]), "")
        if _score_option(q, user_ans):
            correct += 1

    total = len(questions)
    if correct <= 3:
        level = "A0"
        msg = "Отличное начало! Начнём с самых основ." if current_user.native_language == "ru" else "Great start! We'll begin with the basics."
    elif correct <= 6:
        level = "A1"
        msg = "Хорошая база! Продолжим с A1." if current_user.native_language == "ru" else "Good foundation! We'll continue from A1."
    elif correct <= 9:
        level = "A2"
        msg = "Неплохо! Уровень A2." if current_user.native_language == "ru" else "Not bad! Level A2."
    else:
        level = "B1"
        msg = "Отлично! Сразу к B1." if current_user.native_language == "ru" else "Excellent! Straight to B1."

    current_user.level = level
    current_user.onboarding_done = True
    db.commit()

    # Unlock topics up to user level (single pass to avoid duplicates)
    level_order = ["A0", "A1", "A2", "B1"]
    user_level_idx = level_order.index(level)
    levels_to_unlock = level_order[: user_level_idx + 1]

    existing_ids = {
        row.topic_id
        for row in db.query(models.UserTopicProgress).filter(
            models.UserTopicProgress.user_id == current_user.id
        ).all()
    }

    topics_to_unlock = db.query(models.Topic).filter(
        models.Topic.level_required.in_(levels_to_unlock)
    ).all()

    for topic in topics_to_unlock:
        if topic.id not in existing_ids:
            db.add(models.UserTopicProgress(
                user_id=current_user.id, topic_id=topic.id, status="available"
            ))
            existing_ids.add(topic.id)

    db.commit()
    _placement_cache.pop(current_user.id, None)

    return schemas.PlacementTestResult(level=level, correct_count=correct, total=total, message=msg)


def _get_static_placement_test(native_language: str) -> list:
    is_ru = native_language == "ru"
    return [
        {
            "id": 1, "type": "multiple_choice", "level": "A0",
            "question": "Как будет 'кошка' по-польски?" if is_ru else "How do you say 'cat' in Polish?",
            "options": ["pies", "kot", "koń", "ryba"],
            "correct_answer": "kot",
        },
        {
            "id": 2, "type": "multiple_choice", "level": "A0",
            "question": "Как будет 'привет' по-польски?" if is_ru else "How do you say 'hello' in Polish?",
            "options": ["dziękuję", "przepraszam", "cześć", "do widzenia"],
            "correct_answer": "cześć",
        },
        {
            "id": 3, "type": "multiple_choice", "level": "A1",
            "question": "Mam ___ (брат/brat — родительный падеж)" if is_ru else "Mam ___ (brat - genitive)",
            "options": ["brat", "brata", "bracie", "bratem"],
            "correct_answer": "brata",
        },
        {
            "id": 4, "type": "multiple_choice", "level": "A1",
            "question": "Выбери правильный вариант: Ona ___ do szkoły." if is_ru else "Choose the correct form: Ona ___ do szkoły.",
            "options": ["idę", "idziesz", "idzie", "idziemy"],
            "correct_answer": "idzie",
        },
        {
            "id": 5, "type": "multiple_choice", "level": "A1",
            "question": "Ja ___ (читать/czytać) książkę." if is_ru else "Ja ___ (to read/czytać) książkę.",
            "options": ["czyta", "czytasz", "czytam", "czytają"],
            "correct_answer": "czytam",
        },
        {
            "id": 6, "type": "multiple_choice", "level": "A1",
            "question": "Oni ___ (lubić) muzykę." if is_ru else "Oni ___ (to like/lubić) muzykę.",
            "options": ["lubię", "lubisz", "lubi", "lubią"],
            "correct_answer": "lubią",
        },
        {
            "id": 7, "type": "multiple_choice", "level": "A2",
            "question": "Что значит 'Gdzie jest toaleta?'" if is_ru else "What does 'Gdzie jest toaleta?' mean?",
            "options": [
                "Как тебя зовут?" if is_ru else "What's your name?",
                "Где туалет?" if is_ru else "Where is the toilet?",
                "Сколько стоит?" if is_ru else "How much does it cost?",
                "Который час?" if is_ru else "What time is it?",
            ],
            "correct_answer": "Где туалет?" if is_ru else "Where is the toilet?",
        },
        {
            "id": 8, "type": "multiple_choice", "level": "A2",
            "question": "Что значит 'Czy mówisz po angielsku?'" if is_ru else "What does 'Czy mówisz po angielsku?' mean?",
            "options": [
                "Ты говоришь по-польски?" if is_ru else "Do you speak Polish?",
                "Ты говоришь по-английски?" if is_ru else "Do you speak English?",
                "Ты понимаешь меня?" if is_ru else "Do you understand me?",
                "Ты из Англии?" if is_ru else "Are you from England?",
            ],
            "correct_answer": "Ты говоришь по-английски?" if is_ru else "Do you speak English?",
        },
        {
            "id": 9, "type": "multiple_choice", "level": "A2",
            "question": "Составь фразу из слов: [ja, lubić, bardzo, muzyka] — правильный порядок?" if is_ru else "Arrange: [ja, lubić, bardzo, muzyka] — correct order?",
            "options": [
                "Muzyka lubię bardzo ja",
                "Ja lubię bardzo muzykę",
                "Bardzo ja muzykę lubię",
                "Lubię ja bardzo muzyka",
            ],
            "correct_answer": "Ja lubię bardzo muzykę",
        },
        {
            "id": 10, "type": "multiple_choice", "level": "A2",
            "question": "Вчера я ___ в кино. (pójść — прошедшее время, я)" if is_ru else "Yesterday I ___ to the cinema. (pójść - past, I)",
            "options": ["poszłam/poszłem", "idę", "pójdę", "szłam/szedłem"],
            "correct_answer": "poszłam/poszłem",
        },
    ]
