import json
from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from auth import get_current_user
import models
import schemas
from services.gamification import get_game_level, calculate_b1_progress

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=schemas.ProfileResponse)
def get_profile(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    level, level_name, xp_to_next, rank_start = get_game_level(current_user.xp)
    b1_progress = calculate_b1_progress(current_user.id, db)

    curriculum_exercises = db.query(models.UserExerciseHistory).filter(
        models.UserExerciseHistory.user_id == current_user.id
    ).count()
    ai_exercises = db.query(models.DailyExercise).filter(
        models.DailyExercise.user_id == current_user.id,
        models.DailyExercise.is_completed == True,
        models.DailyExercise.source.in_(["new", "bonus", "review"]),
    ).count()
    total_exercises = curriculum_exercises + ai_exercises

    total_chat = db.query(models.ChatMessage).join(models.ChatSession).filter(
        models.ChatSession.user_id == current_user.id,
        models.ChatMessage.role == "user",
    ).count()

    vocab_count = db.query(models.UserVocabulary).filter(
        models.UserVocabulary.user_id == current_user.id,
        models.UserVocabulary.correct_streak >= 1,
    ).count()

    weak_spots = db.query(models.UserTopicProgress).filter(
        models.UserTopicProgress.user_id == current_user.id,
        models.UserTopicProgress.score < 0.6,
        models.UserTopicProgress.attempts > 0,
    ).order_by(models.UserTopicProgress.score).limit(3).all()

    weak_list = []
    for ws in weak_spots:
        topic = ws.topic
        weak_list.append({
            "topic_slug": topic.slug,
            "title_ru": topic.title_ru,
            "title_en": topic.title_en,
            "score": round(ws.score * 100, 1),
        })

    return schemas.ProfileResponse(
        id=current_user.id,
        username=current_user.username,
        native_language=current_user.native_language,
        level=current_user.level,
        xp=current_user.xp,
        streak_days=current_user.streak_days,
        best_streak=getattr(current_user, 'best_streak', None) or 0,
        game_level=level,
        game_level_name=level_name,
        xp_to_next_level=xp_to_next,
        xp_rank_start=rank_start,
        progress_to_b1=b1_progress,
        total_exercises=total_exercises,
        total_chat_messages=total_chat,
        vocab_count=vocab_count,
        total_training_seconds=current_user.total_training_seconds or 0,
        weak_spots=weak_list,
        created_at=current_user.created_at,
    )


@router.get("/achievements", response_model=List[schemas.AchievementResponse])
def get_achievements(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    all_achievements = db.query(models.Achievement).all()
    earned_map = {ua.achievement_id: ua.earned_at for ua in current_user.achievements}

    result = []
    for ach in all_achievements:
        result.append(schemas.AchievementResponse(
            id=ach.id,
            slug=ach.slug,
            title_ru=ach.title_ru,
            title_en=ach.title_en,
            description_ru=ach.description_ru,
            description_en=ach.description_en,
            icon=ach.icon,
            xp_reward=ach.xp_reward,
            earned=ach.id in earned_map,
            earned_at=earned_map.get(ach.id),
        ))
    return result


@router.get("/activity")
def get_activity(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    activity = db.query(models.DailyActivity).filter(
        models.DailyActivity.user_id == current_user.id
    ).order_by(models.DailyActivity.date.desc()).limit(365).all()

    return {
        "activity": [
            {
                "date": a.date.isoformat(),
                "xp_earned": a.xp_earned,
                "exercises_done": a.exercises_done,
                "chat_messages": a.chat_messages,
                "minutes_spent": a.minutes_spent,
            }
            for a in activity
        ]
    }


@router.get("/dashboard")
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    today = date.today()

    # --- today ---
    today_done = db.query(func.count(models.DailyExercise.id)).filter(
        models.DailyExercise.user_id == current_user.id,
        models.DailyExercise.date == today,
        models.DailyExercise.is_completed == True,
        models.DailyExercise.source.notin_(["bonus", "vocab", "practice"]),
    ).scalar() or 0

    today_correct = db.query(func.count(models.DailyExercise.id)).filter(
        models.DailyExercise.user_id == current_user.id,
        models.DailyExercise.date == today,
        models.DailyExercise.is_completed == True,
        models.DailyExercise.is_correct == True,
        models.DailyExercise.source.notin_(["bonus", "vocab", "practice"]),
    ).scalar() or 0

    today_act = db.query(models.DailyActivity).filter(
        models.DailyActivity.user_id == current_user.id,
        models.DailyActivity.date == today,
    ).first()
    today_minutes = today_act.minutes_spent if today_act else 0

    prefs = db.query(models.UserContentPreferences).filter_by(user_id=current_user.id).first()
    sl = prefs.session_length if prefs else "standard"
    today_goal = {"short": 10, "standard": 20, "long": 25}.get(sl, 20)

    # Cap goal at actual daily exercises created (user can't score higher than what was generated)
    daily_total_created = db.query(func.count(models.DailyExercise.id)).filter(
        models.DailyExercise.user_id == current_user.id,
        models.DailyExercise.date == today,
        models.DailyExercise.source.notin_(["bonus", "vocab", "practice"]),
    ).scalar() or 0
    if daily_total_created > 0:
        today_goal = min(today_goal, daily_total_created)

    # --- week (last 7 days) ---
    week_start = today - timedelta(days=6)
    week_rows = db.query(models.DailyActivity).filter(
        models.DailyActivity.user_id == current_user.id,
        models.DailyActivity.date >= week_start,
    ).all()
    week_map = {r.date: r for r in week_rows}
    day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    week = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        r = week_map.get(d)
        week.append({
            "date": d.isoformat(),
            "day": day_names[d.weekday()],
            "exercises": r.exercises_done if r else 0,
            "xp": r.xp_earned if r else 0,
            "minutes": r.minutes_spent if r else 0,
            "is_today": d == today,
        })

    # --- month (last 30 days) ---
    month_start = today - timedelta(days=29)
    month_rows = db.query(models.DailyActivity).filter(
        models.DailyActivity.user_id == current_user.id,
        models.DailyActivity.date >= month_start,
    ).all()
    month_map = {r.date: r for r in month_rows}
    month = []
    for i in range(30):
        d = month_start + timedelta(days=i)
        r = month_map.get(d)
        month.append({
            "date": d.isoformat(),
            "exercises": r.exercises_done if r else 0,
            "xp": r.xp_earned if r else 0,
        })

    # --- source breakdown (last 30 days) ---
    source_rows = db.query(
        models.DailyExercise.source,
        func.count(models.DailyExercise.id),
    ).filter(
        models.DailyExercise.user_id == current_user.id,
        models.DailyExercise.date >= month_start,
        models.DailyExercise.is_completed == True,
    ).group_by(models.DailyExercise.source).all()

    buckets = {"daily": 0, "bonus": 0, "vocab": 0, "topic": 0, "practice": 0}
    for src, cnt in source_rows:
        if src in ("weak", "new", "review", "review_ai", "topic_d"):
            buckets["daily"] += cnt
        elif src == "bonus":
            buckets["bonus"] += cnt
        elif src == "vocab":
            buckets["vocab"] += cnt
        elif src == "topic":
            buckets["topic"] += cnt
        elif src == "practice":
            buckets["practice"] += cnt

    labels = {
        "daily": "Дневная", "bonus": "Бонус",
        "vocab": "Словарь", "topic": "Темы", "practice": "Повторение",
    }
    total_src = max(sum(buckets.values()), 1)
    by_source = [
        {"label": labels[k], "count": v, "pct": round(v / total_src * 100), "key": k}
        for k, v in buckets.items() if v > 0
    ]
    by_source.sort(key=lambda x: -x["count"])

    return {
        "today": {
            "exercises": today_done,
            "correct": today_correct,
            "minutes": today_minutes,
            "goal": today_goal,
            "xp_today": today_act.xp_earned if today_act else 0,
        },
        "week": week,
        "month": month,
        "by_source": by_source,
        "totals": {
            "streak_days": current_user.streak_days,
            "best_streak": getattr(current_user, 'best_streak', None) or 0,
            "xp": current_user.xp,
            "total_time_seconds": current_user.total_training_seconds or 0,
        },
    }


@router.get("/leaderboard")
def get_leaderboard(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    today = date.today()

    # Today's XP for users who practiced (xp_earned > 0)
    activity_rows = db.query(
        models.DailyActivity.user_id,
        models.DailyActivity.xp_earned,
    ).filter(
        models.DailyActivity.date == today,
        models.DailyActivity.xp_earned > 0,
    ).all()

    scores = {row.user_id: row.xp_earned for row in activity_rows}
    # Always include current user even if 0 XP today
    if current_user.id not in scores:
        scores[current_user.id] = 0

    user_rows = db.query(models.User.id, models.User.username).filter(
        models.User.id.in_(scores.keys())
    ).all()
    user_map = {u.id: u.username for u in user_rows}

    sorted_ids = sorted(scores.keys(), key=lambda uid: (-scores[uid], uid))
    my_rank = sorted_ids.index(current_user.id) + 1

    window_start = max(0, my_rank - 1 - 5)
    window_end = min(len(sorted_ids), my_rank - 1 + 6)

    entries = [
        {
            "rank": i + 1 + window_start,
            "username": user_map.get(uid, "?"),
            "xp_today": scores[uid],
            "is_current_user": uid == current_user.id,
        }
        for i, uid in enumerate(sorted_ids[window_start:window_end])
    ]

    return {
        "entries": entries,
        "my_rank": my_rank,
        "total_users": len(sorted_ids),
    }


@router.get("/weak-spots")
def get_weak_spots(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    weak = db.query(models.UserTopicProgress).filter(
        models.UserTopicProgress.user_id == current_user.id,
        models.UserTopicProgress.score < 0.6,
        models.UserTopicProgress.attempts > 0,
    ).order_by(models.UserTopicProgress.score).limit(5).all()

    result = []
    for ws in weak:
        result.append({
            "topic_slug": ws.topic.slug,
            "title_ru": ws.topic.title_ru,
            "title_en": ws.topic.title_en,
            "score": round(ws.score * 100, 1),
            "attempts": ws.attempts,
        })
    return {"weak_spots": result}


@router.put("/settings")
def update_settings(
    body: schemas.ProfileSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if body.native_language:
        current_user.native_language = body.native_language
    db.commit()
    return {"ok": True}


@router.get("/content-preferences", response_model=schemas.ContentPreferencesResponse)
def get_content_preferences(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    prefs = current_user.content_preferences
    if not prefs:
        prefs = models.UserContentPreferences(user_id=current_user.id)
        db.add(prefs)
        db.commit()
        db.refresh(prefs)
    return prefs


@router.put("/content-preferences", response_model=schemas.ContentPreferencesResponse)
def update_content_preferences(
    body: schemas.ContentPreferencesRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    total = body.conversational_weight + body.idiom_weight + body.situational_weight + body.grammar_weight
    if abs(total - 1.0) > 0.01:
        raise HTTPException(status_code=400, detail="Weights must sum to 1.0")

    prefs = current_user.content_preferences
    if not prefs:
        prefs = models.UserContentPreferences(user_id=current_user.id)
        db.add(prefs)

    prefs.conversational_weight = body.conversational_weight
    prefs.idiom_weight = body.idiom_weight
    prefs.situational_weight = body.situational_weight
    prefs.grammar_weight = body.grammar_weight
    prefs.session_length = body.session_length
    prefs.daily_goal_minutes = body.daily_goal_minutes
    if body.interest_themes is not None:
        prefs.interest_themes = json.dumps(body.interest_themes, ensure_ascii=False)
    prefs.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(prefs)
    return prefs
