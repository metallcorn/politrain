from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from auth import get_current_user
import models
import schemas
from services.sm2 import calculate_next_review
from services.gamification import add_xp, XP_CORRECT, XP_INCORRECT, check_achievements, update_daily_activity

router = APIRouter(prefix="/vocabulary", tags=["vocabulary"])


@router.get("", response_model=List[schemas.VocabResponse])
def list_vocabulary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    user_vocabs = db.query(models.UserVocabulary).filter(
        models.UserVocabulary.user_id == current_user.id
    ).all()

    result = []
    for uv in user_vocabs:
        result.append(schemas.VocabResponse(
            id=uv.vocab.id,
            polish=uv.vocab.polish,
            translation_ru=uv.vocab.translation_ru,
            translation_en=uv.vocab.translation_en,
            example_sentence=uv.vocab.example_sentence,
            level=uv.vocab.level,
            ease_factor=uv.ease_factor,
            interval_days=uv.interval_days,
            next_review=uv.next_review,
            repetitions=uv.repetitions,
        ))
    return result


@router.get("/due", response_model=List[schemas.VocabResponse])
def due_vocabulary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    today = date.today()
    user_vocabs = db.query(models.UserVocabulary).filter(
        models.UserVocabulary.user_id == current_user.id,
        models.UserVocabulary.next_review <= today,
    ).all()

    result = []
    for uv in user_vocabs:
        result.append(schemas.VocabResponse(
            id=uv.vocab.id,
            polish=uv.vocab.polish,
            translation_ru=uv.vocab.translation_ru,
            translation_en=uv.vocab.translation_en,
            example_sentence=uv.vocab.example_sentence,
            level=uv.vocab.level,
            ease_factor=uv.ease_factor,
            interval_days=uv.interval_days,
            next_review=uv.next_review,
            repetitions=uv.repetitions,
        ))
    return result


@router.post("/{vocab_id}/review")
def review_vocabulary(
    vocab_id: int,
    body: schemas.VocabReviewRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    uv = db.query(models.UserVocabulary).filter(
        models.UserVocabulary.user_id == current_user.id,
        models.UserVocabulary.vocab_id == vocab_id,
    ).first()

    if not uv:
        # Auto-add to user vocabulary
        vocab = db.query(models.Vocabulary).filter(models.Vocabulary.id == vocab_id).first()
        if not vocab:
            raise HTTPException(status_code=404, detail="Vocabulary not found")
        uv = models.UserVocabulary(user_id=current_user.id, vocab_id=vocab_id)
        db.add(uv)
        db.commit()
        db.refresh(uv)

    new_ef, new_interval, new_reps, next_review = calculate_next_review(
        uv.ease_factor, uv.interval_days, uv.repetitions, body.quality
    )

    uv.ease_factor = new_ef
    uv.interval_days = new_interval
    uv.repetitions = new_reps
    uv.next_review = next_review
    uv.correct_streak = uv.correct_streak + 1 if body.quality >= 3 else 0

    is_correct = body.quality >= 3
    xp = add_xp(current_user, db, XP_CORRECT if is_correct else XP_INCORRECT)
    update_daily_activity(current_user.id, db, xp_earned=xp, exercises_done=1)
    check_achievements(current_user, db)
    db.commit()

    return {
        "next_review": next_review.isoformat(),
        "interval_days": new_interval,
        "xp_earned": xp,
    }


_LEVEL_ORDER = ["A0", "A1", "A2", "B1", "B2", "C1", "C2"]

def _eligible_levels(user_level: str) -> list:
    idx = _LEVEL_ORDER.index(user_level) if user_level in _LEVEL_ORDER else 2
    return _LEVEL_ORDER[:idx + 1]


@router.get("/stats")
def vocab_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    today = date.today()
    all_uvs = db.query(models.UserVocabulary).filter(
        models.UserVocabulary.user_id == current_user.id
    ).all()
    seen_ids = {uv.vocab_id for uv in all_uvs}
    known_count = sum(1 for uv in all_uvs if (uv.correct_streak or 0) >= 1)
    # correct_streak==0 splits: practiced-and-wrong vs freshly-added-never-practiced (learn-word)
    wrong_count = sum(1 for uv in all_uvs if (uv.correct_streak or 0) == 0 and uv.last_reviewed is not None)
    to_learn_count = sum(1 for uv in all_uvs if (uv.correct_streak or 0) == 0 and uv.last_reviewed is None)
    due_count = sum(
        1 for uv in all_uvs
        if (uv.correct_streak or 0) >= 1 and uv.next_review and uv.next_review <= today
    )
    eligible_levels = _eligible_levels(current_user.level)
    # New = unseen dictionary words + words the user clicked to learn but hasn't practiced yet
    new_count = db.query(models.Vocabulary).filter(
        models.Vocabulary.level.in_(eligible_levels),
        models.Vocabulary.id.notin_(seen_ids) if seen_ids else True,
    ).count() + to_learn_count
    pending = wrong_count + due_count + new_count
    return {
        "known_count": known_count,
        "new_count": new_count,
        "wrong_count": wrong_count,
        "due_count": due_count,
        "pending": pending,
    }


class LearnWordRequest(BaseModel):
    word: str
    translation: str


@router.post("/learn-word")
def learn_word(
    req: LearnWordRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    word = req.word.strip()
    translation = req.translation.strip()
    if not word or not translation:
        raise HTTPException(status_code=400, detail="word and translation required")

    vocab = db.query(models.Vocabulary).filter(
        func.lower(models.Vocabulary.polish) == word.lower()
    ).first()

    if not vocab:
        vocab = models.Vocabulary(
            polish=word,
            translation_ru=translation,
            translation_en="",
            level=current_user.level,
        )
        db.add(vocab)
        db.flush()

    uv = db.query(models.UserVocabulary).filter_by(
        user_id=current_user.id, vocab_id=vocab.id
    ).first()
    is_new = uv is None

    if not uv:
        uv = models.UserVocabulary(
            user_id=current_user.id,
            vocab_id=vocab.id,
            ease_factor=2.5,
            interval_days=1,
            correct_streak=0,
            next_review=date.today(),
        )
        db.add(uv)

    db.commit()
    return {"ok": True, "vocab_id": vocab.id, "is_new": is_new}
