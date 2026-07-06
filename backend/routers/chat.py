import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from auth import get_current_user
import models
import schemas
import prompts
from services import mistral
from services.i18n import lang_name, ui
from services.gamification import add_xp, XP_CHAT_MESSAGE, check_achievements, update_daily_activity, update_streak

router = APIRouter(prefix="/chat", tags=["chat"])

# Role-play scenarios: the AI stays in `role` (English — Mistral-facing), opens with
# `opening` (Polish — in-scene), `title` is user-facing and per-language (en fallback).
SCENARIOS = {
    "cafe":       {"title": {"ru": "В кафе", "en": "At the café"},
                   "role": "a waiter in a Polish café",
                   "opening": "Dzień dobry! Zapraszam. Co podać do picia?"},
    "doctor":     {"title": {"ru": "У врача", "en": "At the doctor's"},
                   "role": "a general practitioner seeing a patient",
                   "opening": "Dzień dobry, proszę usiąść. Co Panu/Pani dolega?"},
    "airport":    {"title": {"ru": "В аэропорту", "en": "At the airport"},
                   "role": "a check-in desk agent at the airport",
                   "opening": "Dzień dobry! Poproszę paszport i bilet. Dokąd Pan/Pani leci?"},
    "shop":       {"title": {"ru": "В магазине одежды", "en": "In a clothes shop"},
                   "role": "a shop assistant in a clothes shop",
                   "opening": "Dzień dobry! W czym mogę pomóc?"},
    "hotel":      {"title": {"ru": "В отеле", "en": "At the hotel"},
                   "role": "a receptionist at a hotel front desk",
                   "opening": "Dzień dobry! Witamy w hotelu. Ma Pan/Pani rezerwację?"},
    "directions": {"title": {"ru": "Спросить дорогу", "en": "Asking for directions"},
                   "role": "a passer-by on a street in a Polish city",
                   "opening": "Słucham? W czym mogę pomóc?"},
}


def _scenario_title(scenario_key: str, lang: str) -> str | None:
    sc = SCENARIOS.get(scenario_key)
    if not sc:
        return None
    titles = sc["title"]
    return titles.get((lang or "").lower(), titles["en"])


@router.get("/scenarios")
def get_scenarios(current_user: models.User = Depends(get_current_user)):
    return {"scenarios": [
        {"id": k, "title": _scenario_title(k, current_user.native_language)}
        for k in SCENARIOS
    ]}


@router.post("/session/{session_id}/debrief")
async def debrief_dialogue(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """End-of-dialogue review: gentle corrections of the learner's Polish (role-play sessions)."""
    session = db.query(models.ChatSession).filter(
        models.ChatSession.id == session_id,
        models.ChatSession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    user_msgs = db.query(models.ChatMessage).filter(
        models.ChatMessage.session_id == session_id,
        models.ChatMessage.role == "user",
    ).order_by(models.ChatMessage.created_at).all()
    if not user_msgs:
        return {"text": ui("debrief_no_messages", current_user.native_language)}

    title = (_scenario_title(session.scenario, current_user.native_language)
             or session.topic or ui("dialogue_fallback_title", current_user.native_language))
    joined = "\n".join(f"- {m.content}" for m in user_msgs)
    try:
        text = await mistral.simple_prompt(
            system="You are a kind Polish language teacher. Reply in the user's native language, markdown.",
            user=prompts.DIALOGUE_DEBRIEF_PROMPT.format(
                title=title, user_messages=joined,
                native_language=lang_name(current_user.native_language),
            ),
            temperature=0.4, max_tokens=700, timeout=40.0, retries=1,
            purpose="dialogue_debrief", user_id=current_user.id,
        )
    except Exception:
        text = ui("debrief_failed", current_user.native_language)
    session.ended_at = datetime.utcnow()
    db.commit()
    return {"text": text}


@router.post("/session", response_model=schemas.ChatSessionResponse)
def create_session(
    body: schemas.NewChatSessionRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    scenario = body.scenario if body.scenario in SCENARIOS else None
    topic = _scenario_title(scenario, current_user.native_language) if scenario else body.topic
    session = models.ChatSession(user_id=current_user.id, topic=topic, scenario=scenario)
    db.add(session)
    db.commit()
    db.refresh(session)
    # Seed the opening line so the user steps into an already-started scene
    if scenario:
        db.add(models.ChatMessage(
            session_id=session.id, role="assistant", content=SCENARIOS[scenario]["opening"],
        ))
        session.message_count += 1
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
        "scenario": session.scenario,
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
    ) or "none"

    if session.scenario and session.scenario in SCENARIOS:
        sc = SCENARIOS[session.scenario]
        system = prompts.CHAT_ROLEPLAY_PROMPT.format(
            role=sc["role"], title=_scenario_title(session.scenario, current_user.native_language),
            level=current_user.level, native_language=lang_name(current_user.native_language),
        )
    else:
        system = prompts.CHAT_SYSTEM_PROMPT.format(
            level=current_user.level,
            native_language=lang_name(current_user.native_language),
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
    return {"topics": ui("chat_topics", current_user.native_language)}
