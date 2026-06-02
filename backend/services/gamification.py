from datetime import date, timedelta
from sqlalchemy.orm import Session
import models

XP_CORRECT = 10
XP_INCORRECT = 2
XP_COMPLETE_TOPIC = 50
XP_COMPLETE_SESSION = 30
XP_CHAT_MESSAGE = 5

GAME_LEVELS = [
    (0, "Новичок"),
    (200, "Ученик"),
    (500, "Студент"),
    (1000, "Знаток"),
    (2000, "Полиглот"),
    (4000, "Мастер"),
    (8000, "Эксперт"),
    (15000, "Легенда"),
]


def get_game_level(xp: int) -> tuple[int, str, int]:
    level = 1
    level_name = GAME_LEVELS[0][1]
    xp_to_next = GAME_LEVELS[1][0]

    for i, (threshold, name) in enumerate(GAME_LEVELS):
        if xp >= threshold:
            level = i + 1
            level_name = name
            if i + 1 < len(GAME_LEVELS):
                xp_to_next = GAME_LEVELS[i + 1][0] - xp
            else:
                xp_to_next = 0

    return level, level_name, max(0, xp_to_next)


def add_xp(user: models.User, db: Session, amount: int) -> int:
    user.xp += amount
    db.add(user)
    return amount


def update_streak(user: models.User, db: Session) -> int:
    today = date.today()
    yesterday = today - timedelta(days=1)

    if user.last_activity == today:
        return user.streak_days

    if user.last_activity == yesterday:
        user.streak_days += 1
        streak_bonus = XP_CORRECT * 2 * user.streak_days
        user.xp += streak_bonus
    elif user.last_activity is None or user.last_activity < yesterday:
        user.streak_days = 1

    user.last_activity = today
    db.add(user)
    return user.streak_days


def update_daily_activity(user_id: int, db: Session, **kwargs):
    today = date.today()
    activity = db.query(models.DailyActivity).filter(
        models.DailyActivity.user_id == user_id,
        models.DailyActivity.date == today,
    ).first()

    if not activity:
        activity = models.DailyActivity(user_id=user_id, date=today)
        db.add(activity)

    for key, val in kwargs.items():
        current = getattr(activity, key, 0) or 0
        setattr(activity, key, current + val)

    db.commit()


def check_achievements(user: models.User, db: Session) -> list[models.Achievement]:
    earned = []
    all_achievements = db.query(models.Achievement).all()
    user_achievement_ids = {ua.achievement_id for ua in user.achievements}

    for ach in all_achievements:
        if ach.id in user_achievement_ids:
            continue

        unlocked = False

        if ach.condition_type == "streak":
            unlocked = user.streak_days >= ach.condition_value
        elif ach.condition_type == "xp":
            unlocked = user.xp >= ach.condition_value
        elif ach.condition_type == "vocab_count":
            count = db.query(models.UserVocabulary).filter(
                models.UserVocabulary.user_id == user.id
            ).count()
            unlocked = count >= ach.condition_value
        elif ach.condition_type == "chat_messages":
            count = db.query(models.ChatMessage).join(models.ChatSession).filter(
                models.ChatSession.user_id == user.id,
                models.ChatMessage.role == "user",
            ).count()
            unlocked = count >= ach.condition_value
        elif ach.condition_type == "first_lesson":
            count = db.query(models.UserTopicProgress).filter(
                models.UserTopicProgress.user_id == user.id,
                models.UserTopicProgress.status == "done",
            ).count()
            unlocked = count >= 1
        elif ach.condition_type == "training_seconds":
            seconds = getattr(user, 'total_training_seconds', 0) or 0
            unlocked = seconds >= ach.condition_value
        elif ach.condition_type == "all_level_topics":
            level = ach.slug.split("_")[1].upper() if "_" in ach.slug else None
            if level:
                total = db.query(models.Topic).filter(models.Topic.level_required == level).count()
                done = db.query(models.UserTopicProgress).join(models.Topic).filter(
                    models.UserTopicProgress.user_id == user.id,
                    models.UserTopicProgress.status == "done",
                    models.Topic.level_required == level,
                ).count()
                unlocked = total > 0 and done >= total

        if unlocked:
            ua = models.UserAchievement(user_id=user.id, achievement_id=ach.id)
            db.add(ua)
            user.xp += ach.xp_reward
            earned.append(ach)

    if earned:
        db.commit()
    return earned


def calculate_b1_progress(user_id: int, db: Session) -> float:
    total = db.query(models.Topic).count()
    if total == 0:
        return 0.0
    done = db.query(models.UserTopicProgress).filter(
        models.UserTopicProgress.user_id == user_id,
        models.UserTopicProgress.status == "done",
    ).count()
    return round((done / total) * 100, 1)
