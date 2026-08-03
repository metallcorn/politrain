import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user
import models
import schemas
import prompts
from services import mistral
from services.i18n import lang_name
from services.generation import build_validated_reading, build_exam_grammar

router = APIRouter(prefix="/exam", tags=["exam"])

EXAM_TASKS = [
    {
        "type": "reading",
        "title_ru": "Чтение (Rozumienie tekstów pisanych)",
        "title_en": "Reading (Rozumienie tekstów pisanych)",
        "description_ru": "Прочитайте текст и ответьте на вопросы",
        "description_en": "Read the text and answer the questions",
        "available": True,
    },
    {
        "type": "listening",
        "title_ru": "Аудирование (Rozumienie ze słuchu)",
        "title_en": "Listening (Rozumienie ze słuchu)",
        "description_ru": "Скоро будет доступно",
        "description_en": "Coming soon",
        "available": False,
    },
    {
        "type": "grammar",
        "title_ru": "Грамматика (Poprawność gramatyczna)",
        "title_en": "Grammar (Poprawność gramatyczna)",
        "description_ru": "20 вопросов по грамматике B1",
        "description_en": "20 B1 grammar questions",
        "available": True,
    },
    {
        "type": "writing",
        "title_ru": "Письмо (Pisanie)",
        "title_en": "Writing (Pisanie)",
        "description_ru": "Напишите текст по заданию",
        "description_en": "Write a text based on the task",
        "available": True,
    },
    {
        "type": "speaking",
        "title_ru": "Говорение (Mówienie)",
        "title_en": "Speaking (Mówienie)",
        "description_ru": "Скоро будет доступно",
        "description_en": "Coming soon",
        "available": False,
    },
]

WRITING_TASKS = [
    "Напишите письмо другу о вашем городе. Расскажите, что вам в нём нравится и не нравится. Объём: 80-100 слов.",
    "Напишите email в гостиницу с просьбой забронировать номер на 3 ночи. Укажите дату заезда и ваши пожелания. Объём: 80-100 слов.",
    "Напишите сообщение другу, объяснив почему вы не смогли прийти на встречу и предложив другое время. Объём: 80-100 слов.",
    "Напишите отзыв о ресторане, в котором вы недавно были. Опишите еду, обслуживание и атмосферу. Объём: 80-100 слов.",
]

READING_TOPICS = [
    "польские традиции и праздники",
    "жизнь в польском городе",
    "польская кухня",
    "путешествия по Польше",
    "польская культура и история",
]


@router.get("/tasks")
def list_tasks(current_user: models.User = Depends(get_current_user)):
    level_order = ["A0", "A1", "A2", "B1"]
    unlocked = level_order.index(current_user.level) >= level_order.index("A2")
    return {"tasks": EXAM_TASKS, "unlocked": unlocked}


@router.get("/task/{task_type}")
async def get_task(
    task_type: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if task_type == "listening" or task_type == "speaking":
        return {"status": "not_implemented", "message": "Скоро будет доступно"}

    if task_type == "reading":
        # Validated pipeline (2026-08-06): same label-stripping / letter-mapping / well-formed
        # filtering as the daily reading mode — the exam no longer serves raw Mistral output.
        try:
            data = await build_validated_reading(current_user, db, exam=True)
            if not data:
                return {"type": "reading", "data": None, "error": "AI временно недоступен"}
            return {"type": "reading", "data": data}
        except Exception:
            return {"type": "reading", "data": None, "error": "AI временно недоступен"}

    if task_type == "grammar":
        # Validated pipeline: pool-first (already past all validators/dedup) + validated
        # top-up. No more raw GRAMMAR_EXAM_PROMPT with its wrong-answer/meta-question bugs.
        try:
            # exam challenges the level you're climbing toward, not the one you already have
            from services.generation import _next_level
            questions = await build_exam_grammar(current_user, db, level=_next_level(current_user.level), count=12)
            if not questions:
                return {"type": "grammar", "questions": [], "error": "AI временно недоступен"}
            return {"type": "grammar", "questions": questions}
        except Exception:
            return {"type": "grammar", "questions": [], "error": "AI временно недоступен"}

    if task_type == "writing":
        import random
        task_desc = random.choice(WRITING_TASKS)
        return {"type": "writing", "task_description": task_desc}

    raise HTTPException(status_code=404, detail="Unknown task type")


@router.post("/task/{task_type}/submit")
async def submit_task(
    task_type: str,
    body: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if task_type == "writing":
        student_text = body.get("student_text", "")
        task_description = body.get("task_description", "")

        try:
            raw = await mistral.simple_prompt(
                system="You are a B1 Polish exam evaluator. Respond only with valid JSON.",
                user=prompts.WRITING_EVALUATION_PROMPT.format(
                    task_description=task_description,
                    student_text=student_text,
                    native_language=lang_name(current_user.native_language),
                ),
                temperature=0.3,
                max_tokens=800,
            )
            result = await mistral.parse_json_response(raw)
            return {"type": "writing", "result": result}
        except Exception:
            return {"type": "writing", "result": None, "error": "AI временно недоступен"}

    if task_type == "reading":
        answers = body.get("answers", [])
        questions = body.get("questions_data", [])
        correct = 0
        for i, q in enumerate(questions):
            # validated reading exposes 'correct_answer' (old raw prompt used 'correct')
            expected = q.get("correct_answer", q.get("correct", ""))
            if i < len(answers) and str(answers[i]).strip() == str(expected).strip():
                correct += 1
        total = len(questions)
        return {
            "type": "reading",
            "correct": correct,
            "total": total,
            "score": round(correct / total * 100, 1) if total > 0 else 0,
        }

    if task_type == "grammar":
        answers = body.get("answers", [])
        questions = body.get("questions_data", [])
        correct = 0
        for i, q in enumerate(questions):
            if i < len(answers) and answers[i].strip().lower() == q.get("correct_answer", "").strip().lower():
                correct += 1
        total = len(questions)
        return {
            "type": "grammar",
            "correct": correct,
            "total": total,
            "score": round(correct / total * 100, 1) if total > 0 else 0,
        }

    raise HTTPException(status_code=404, detail="Unknown task type")


@router.get("/history")
def exam_history(current_user: models.User = Depends(get_current_user)):
    return {"history": []}
