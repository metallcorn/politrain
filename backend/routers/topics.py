import json
from itertools import groupby as _groupby
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from auth import get_current_user
import models
import schemas
import prompts
from services import mistral
from services.gamification import add_xp, XP_COMPLETE_TOPIC, check_achievements, update_daily_activity

router = APIRouter(prefix="/topics", tags=["topics"])


def _mastered_exercise_ids(user_id: int, db: Session, threshold: int = 3) -> set:
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


@router.get("", response_model=List[schemas.TopicResponse])
def list_topics(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    topics = db.query(models.Topic).order_by(models.Topic.order_index).all()
    result = []
    for topic in topics:
        progress = db.query(models.UserTopicProgress).filter(
            models.UserTopicProgress.user_id == current_user.id,
            models.UserTopicProgress.topic_id == topic.id,
        ).first()
        t = schemas.TopicResponse(
            id=topic.id,
            slug=topic.slug,
            title_ru=topic.title_ru,
            title_en=topic.title_en,
            description_ru=topic.description_ru,
            description_en=topic.description_en,
            level_required=topic.level_required,
            order_index=topic.order_index,
            status=progress.status if progress else "locked",
            score=progress.score if progress else 0.0,
        )
        result.append(t)
    return result


@router.get("/{slug}", response_model=schemas.TopicResponse)
def get_topic(
    slug: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    topic = db.query(models.Topic).filter(models.Topic.slug == slug).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    progress = db.query(models.UserTopicProgress).filter(
        models.UserTopicProgress.user_id == current_user.id,
        models.UserTopicProgress.topic_id == topic.id,
    ).first()

    return schemas.TopicResponse(
        id=topic.id,
        slug=topic.slug,
        title_ru=topic.title_ru,
        title_en=topic.title_en,
        description_ru=topic.description_ru,
        description_en=topic.description_en,
        level_required=topic.level_required,
        order_index=topic.order_index,
        status=progress.status if progress else "locked",
        score=progress.score if progress else 0.0,
    )


@router.get("/{slug}/lesson")
async def get_lesson(
    slug: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    topic = db.query(models.Topic).filter(models.Topic.slug == slug).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    lang = current_user.native_language
    title = topic.title_ru if lang == "ru" else topic.title_en

    # Mark as in_progress
    progress = db.query(models.UserTopicProgress).filter(
        models.UserTopicProgress.user_id == current_user.id,
        models.UserTopicProgress.topic_id == topic.id,
    ).first()
    if not progress:
        progress = models.UserTopicProgress(
            user_id=current_user.id, topic_id=topic.id, status="in_progress"
        )
        db.add(progress)
    elif progress.status == "available":
        progress.status = "in_progress"
    db.commit()

    # Get exercises for mini-test, excluding mastered ones
    TARGET = 8
    mastered_ids = _mastered_exercise_ids(current_user.id, db)
    exercises = db.query(models.Exercise).filter(
        models.Exercise.topic_id == topic.id,
        ~models.Exercise.id.in_(mastered_ids) if mastered_ids else True,
    ).all()

    # Generate more if not enough
    if len(exercises) < TARGET:
        need = TARGET - len(exercises)
        try:
            # Collect reported errors for this topic to avoid repeating them
            reports = db.query(models.ExerciseReport).join(models.Exercise).filter(
                models.Exercise.topic_id == topic.id
            ).order_by(models.ExerciseReport.created_at.desc()).limit(10).all()

            avoid_block = ""
            if reports:
                examples = []
                for r in reports:
                    try:
                        snap = json.loads(r.exercise_snapshot)
                        desc = f'- Вопрос: "{snap["question"]}" / Ответ: "{snap["correct_answer"]}"'
                        if r.comment:
                            desc += f' (ошибка: {r.comment})'
                        examples.append(desc)
                    except Exception:
                        pass
                if examples:
                    avoid_block = "\n\nИЗБЕГАЙ повторения этих упражнений — они были помечены как ошибочные:\n" + "\n".join(examples)

            raw = await mistral.simple_prompt(
                system="You are a Polish language exercise generator. Respond only with valid JSON array.",
                user=prompts.TOPIC_EXERCISES_PROMPT.format(
                    topic_title=title,
                    level=current_user.level,
                    native_language=lang,
                    count=need,
                ) + avoid_block,
                temperature=0.7,
                max_tokens=2500,
                timeout=20.0,
                retries=1,
            )
            generated = await mistral.parse_json_response(raw)
            allowed_types = {"multiple_choice", "fill_blank"}
            _norm = lambda s: s.strip().lower() if s else ""
            for item in generated:
                if not isinstance(item, dict):
                    continue
                if item.get("type") not in allowed_types:
                    continue
                # Validate MC: correct_answer must match an option
                if item.get("type") == "multiple_choice":
                    opts_list = item.get("options") or []
                    ca = item.get("correct_answer", "")
                    if opts_list and ca not in opts_list:
                        match = next((o for o in opts_list if _norm(o) == _norm(ca)), None)
                        if match:
                            item["correct_answer"] = match
                        else:
                            continue  # discard broken exercise
                opts = item.get("options")
                new_ex = models.Exercise(
                    topic_id=topic.id,
                    type=item.get("type", "fill_blank"),
                    question=item.get("question", ""),
                    correct_answer=item.get("correct_answer", ""),
                    options=json.dumps(opts, ensure_ascii=False) if opts else None,
                    hint=item.get("hint"),
                    explanation=item.get("explanation"),
                    level=current_user.level,
                )
                db.add(new_ex)
            db.commit()
            # Reload (excluding mastered)
            exercises = db.query(models.Exercise).filter(
                models.Exercise.topic_id == topic.id,
                ~models.Exercise.id.in_(mastered_ids) if mastered_ids else True,
            ).all()
        except Exception:
            pass  # Use whatever exercises we have from DB

    ex_list = []
    for ex in exercises[:TARGET]:
        opts = None
        if ex.options:
            try:
                opts = json.loads(ex.options)
            except Exception:
                opts = None
        ex_list.append({
            "id": ex.id,
            "type": ex.type,
            "question": ex.question,
            "correct_answer": ex.correct_answer,
            "options": opts,
            "hint": ex.hint,
            "explanation": ex.explanation,
            "last_result": None,
        })

    # Pre-populate last_result from UserExerciseHistory
    if ex_list:
        ex_ids = [e["id"] for e in ex_list]
        history_rows = (
            db.query(models.UserExerciseHistory)
            .filter(
                models.UserExerciseHistory.user_id == current_user.id,
                models.UserExerciseHistory.exercise_id.in_(ex_ids),
            )
            .order_by(models.UserExerciseHistory.created_at.desc())
            .all()
        )
        last_answer_by_id = {}
        for h in history_rows:
            if h.exercise_id not in last_answer_by_id:
                last_answer_by_id[h.exercise_id] = h
        for ex_data in ex_list:
            h = last_answer_by_id.get(ex_data["id"])
            if h:
                ex_data["last_result"] = {
                    "is_correct": h.is_correct,
                    "correct_answer": ex_data["correct_answer"],
                    "explanation": ex_data["explanation"],
                    "user_answer": h.user_answer,
                    "xp_earned": 0,
                    "diacritic_hint": False,
                }

    # Use cached explanation if available
    cached = topic.explanation_ru if lang == "ru" else topic.explanation_en
    if cached:
        explanation = cached
    else:
        try:
            explanation = await mistral.simple_prompt(
                system=prompts.TOPIC_EXPLANATION_PROMPT.format(
                    native_language=lang,
                    level=current_user.level,
                    topic_title=title,
                ),
                user=f"Объясни тему: {title}",
                temperature=0.6,
                max_tokens=1500,
            )
            # Save to DB so it's not regenerated next time
            if lang == "ru":
                topic.explanation_ru = explanation
            else:
                topic.explanation_en = explanation
            db.commit()
        except Exception:
            explanation = f"**{title}**\n\nAI временно недоступен. Используйте упражнения для изучения темы."

    return {
        "topic_slug": slug,
        "topic_title": title,
        "explanation": explanation,
        "exercises": ex_list,
    }


@router.post("/{slug}/lesson/next")
async def next_example(
    slug: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    topic = db.query(models.Topic).filter(models.Topic.slug == slug).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    lang = current_user.native_language
    title = topic.title_ru if lang == "ru" else topic.title_en

    try:
        example = await mistral.simple_prompt(
            system="You are a Polish language teacher. Give a short, practical example.",
            user=prompts.TOPIC_EXAMPLE_PROMPT.format(
                level=current_user.level,
                native_language=lang,
                topic_title=title,
            ),
            temperature=0.8,
            max_tokens=500,
        )
    except Exception:
        example = "AI временно недоступен."

    return {"example": example}


@router.post("/exercises/{exercise_id}/report")
def report_exercise(
    exercise_id: int,
    body: schemas.ExerciseReportCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    exercise = db.query(models.Exercise).filter(models.Exercise.id == exercise_id).first()
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    snapshot = json.dumps({
        "type": exercise.type,
        "question": exercise.question,
        "correct_answer": exercise.correct_answer,
        "options": json.loads(exercise.options) if exercise.options else None,
        "explanation": exercise.explanation,
    }, ensure_ascii=False)

    report = models.ExerciseReport(
        exercise_id=exercise_id,
        user_id=current_user.id,
        comment=body.comment,
        exercise_snapshot=snapshot,
    )
    db.add(report)
    exercise.is_flagged = True
    db.commit()
    return {"ok": True}


@router.post("/{slug}/complete")
def complete_topic(
    slug: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    topic = db.query(models.Topic).filter(models.Topic.slug == slug).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    progress = db.query(models.UserTopicProgress).filter(
        models.UserTopicProgress.user_id == current_user.id,
        models.UserTopicProgress.topic_id == topic.id,
    ).first()

    if not progress:
        progress = models.UserTopicProgress(
            user_id=current_user.id, topic_id=topic.id
        )
        db.add(progress)

    progress.status = "done"
    progress.score = max(progress.score, 0.7)
    db.commit()

    xp = add_xp(current_user, db, XP_COMPLETE_TOPIC)
    new_achievements = check_achievements(current_user, db)
    update_daily_activity(current_user.id, db, xp_earned=xp)
    db.commit()

    return {
        "ok": True,
        "xp_earned": xp,
        "new_achievements": [a.slug for a in new_achievements],
    }
