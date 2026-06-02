import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from auth import get_current_user
import models
import schemas
import prompts
from services import mistral
from services.gamification import add_xp, XP_CHAT_MESSAGE, check_achievements, update_daily_activity, update_streak

router = APIRouter(prefix="/chat", tags=["chat"])

CHAT_TOPICS = [
    "Расскажи о своём дне",
    "Опиши свой город",
    "Что ты делал на выходных?",
    "Поговорим о еде",
    "Твои планы на будущее",
    "Свободная тема",
]


@router.post("/session", response_model=schemas.ChatSessionResponse)
def create_session(
    body: schemas.NewChatSessionRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    session = models.ChatSession(user_id=current_user.id, topic=body.topic)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/sessions", response_model=List[schemas.ChatSessionResponse])
def list_sessions(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    sessions = db.query(models.ChatSession).filter(
        models.ChatSession.user_id == current_user.id
    ).order_by(models.ChatSession.created_at.desc()).limit(20).all()
    return sessions


@router.get("/session/{session_id}")
def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    session = db.query(models.ChatSession).filter(
        models.ChatSession.id == session_id,
        models.ChatSession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = db.query(models.ChatMessage).filter(
        models.ChatMessage.session_id == session_id
    ).order_by(models.ChatMessage.created_at).all()

    return {
        "id": session.id,
        "topic": session.topic,
        "created_at": session.created_at,
        "message_count": session.message_count,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "corrections": m.corrections,
                "created_at": m.created_at,
            }
            for m in messages
        ],
    }


@router.post("/session/{session_id}/message")
async def send_message(
    session_id: int,
    body: schemas.SendMessageRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    session = db.query(models.ChatSession).filter(
        models.ChatSession.id == session_id,
        models.ChatSession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Save user message
    user_msg = models.ChatMessage(
        session_id=session_id, role="user", content=body.content
    )
    db.add(user_msg)
    session.message_count += 1

    # Build history for context (last 20 messages)
    history = db.query(models.ChatMessage).filter(
        models.ChatMessage.session_id == session_id
    ).order_by(models.ChatMessage.created_at.desc()).limit(20).all()
    history.reverse()

    # Weak spots
    weak_topics = db.query(models.Topic).join(models.UserTopicProgress).filter(
        models.UserTopicProgress.user_id == current_user.id,
        models.UserTopicProgress.score < 0.6,
    ).limit(3).all()
    weak_spots = ", ".join(
        t.title_ru if current_user.native_language == "ru" else t.title_en
        for t in weak_topics
    ) or "нет"

    system = prompts.CHAT_SYSTEM_PROMPT.format(
        level=current_user.level,
        native_language=current_user.native_language,
        weak_spots=weak_spots,
    )

    messages = [{"role": "system", "content": system}]
    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": body.content})

    try:
        ai_response = await mistral.chat_completion(messages, temperature=0.8, max_tokens=600)
    except Exception:
        ai_response = "Przepraszam, mam chwilowe problemy techniczne. Spróbuj ponownie za chwilę."

    # Save assistant message
    ai_msg = models.ChatMessage(
        session_id=session_id, role="assistant", content=ai_response
    )
    db.add(ai_msg)
    session.message_count += 1

    xp = add_xp(current_user, db, XP_CHAT_MESSAGE)
    update_streak(current_user, db)
    update_daily_activity(current_user.id, db, xp_earned=xp, chat_messages=1)
    check_achievements(current_user, db)
    db.commit()

    return {
        "user_message": {"role": "user", "content": body.content},
        "assistant_message": {"role": "assistant", "content": ai_response},
        "xp_earned": xp,
    }


@router.get("/topics")
def get_chat_topics(current_user: models.User = Depends(get_current_user)):
    return {"topics": CHAT_TOPICS}
