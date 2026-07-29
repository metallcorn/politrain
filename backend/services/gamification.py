from datetime import date, timedelta
from sqlalchemy.orm import Session
import models

XP_CORRECT = 10
XP_INCORRECT = 2
XP_VOCAB = 5        # SRS vocab flashcards in daily/bonus mode
XP_VOCAB_NEW = 2    # vocab session: new or error word answered correctly
XP_VOCAB_REVIEW = 1 # vocab session: review word answered correctly
XP_COMPLETE_TOPIC = 50
XP_COMPLETE_SESSION = 30
XP_CHAT_MESSAGE = 5

# 25 XP-ranks — designed for years of play (~300-500 XP/day at consistent pace)
XP_RANKS = [
    (0,      "Новичок I"),
    (200,    "Новичок II"),
    (500,    "Новичок III"),
    (900,    "Ученик I"),
    (1400,   "Ученик II"),
    (2000,   "Ученик III"),
    (2800,   "Ученик IV"),
    (3800,   "Практикант I"),
    (5000,   "Практикант II"),
    (6500,   "Практикант III"),
    (8500,   "Практикант IV"),
    (11000,  "Знаток I"),
    (14000,  "Знаток II"),
    (18000,  "Знаток III"),
    (23000,  "Знаток IV"),
    (29000,  "Мастер I"),
    (36000,  "Мастер II"),
    (44000,  "Мастер III"),
    (53000,  "Мастер IV"),
    (63000,  "Мастер V"),
    (74000,  "Эксперт I"),
    (86000,  "Эксперт II"),
    (99000,  "Эксперт III"),
    (113000, "Эксперт IV"),
    (128000, "Эксперт V"),
]


def get_game_level(xp: int) -> tuple[int, str, int, int]:
    rank_num = 1
    rank_name = XP_RANKS[0][1]
    rank_start = XP_RANKS[0][0]
    xp_to_next = XP_RANKS[1][0]

    for i, (threshold, name) in enumerate(XP_RANKS):
        if xp >= threshold:
            rank_num = i + 1
            rank_name = name
            rank_start = threshold
            if i + 1 < len(XP_RANKS):
                xp_to_next = XP_RANKS[i + 1][0] - xp
            else:
                xp_to_next = 0

    return rank_num, rank_name, max(0, xp_to_next), rank_start


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

    # Track personal best streak
    best = getattr(user, 'best_streak', None) or 0
    if user.streak_days > best:
        user.best_streak = user.streak_days

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


# Levels that count toward the "progress to B1" bar. B2 (added later) must NOT dilute it —
# the old formula used ALL topics as the denominator, so adding topics dropped the bar even
# though the user learned nothing (2026-07-29: +6 B1 topics knocked ~79% down to ~65%).
_TO_B1_LEVELS = ("A0", "A1", "A2", "B1")

def calculate_b1_progress(user_id: int, db: Session) -> float:
    """Honest, responsive progress through the A0..B1 curriculum. Denominator capped at B1
    (future B2 topics don't count). PARTIAL credit by score so the bar moves as a topic
    improves, not only when it flips to 'done' — a topic at 0.6 contributes 0.6, done = 1.0."""
    topic_ids = [t[0] for t in db.query(models.Topic.id).filter(
        models.Topic.level_required.in_(_TO_B1_LEVELS)
    ).all()]
    total = len(topic_ids)
    if total == 0:
        return 0.0
    by_topic = {
        p.topic_id: p for p in db.query(models.UserTopicProgress).filter(
            models.UserTopicProgress.user_id == user_id,
            models.UserTopicProgress.topic_id.in_(topic_ids),
        ).all()
    }
    credit = 0.0
    for tid in topic_ids:
        p = by_topic.get(tid)
        if not p:
            continue
        # done → full; otherwise partial credit = score, capped below 1 so only real
        # completion reaches 100%
        credit += 1.0 if p.status == "done" else min(p.score or 0.0, 0.95)
    return round((credit / total) * 100, 1)
