"""Nightly pool replenishment: keep every active user's UNSEEN pool reserve topped up.

Why: the pool refilled only as a side effect of live session generation, and an active
user consumed it faster than it refilled — daytime requests then hit Mistral live
(slow, short sessions 11-17/20, fallback-to-small quality; feedback #145/#146).
This job pre-generates during the night so daytime sessions are instant and full.

Run by politrain-pool.timer (04:30, after the DB backup). Manual run:
    cd backend && env $(cat ../.env | grep -v '^#' | xargs) venv/bin/python3 scripts/replenish_pool.py
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import SessionLocal  # noqa: E402
import models  # noqa: E402
from services.generation import (  # noqa: E402
    _generate_exercises, _validate_batch, _save_to_pool,
    _select_topics_for_generation, _select_interest_themes, _next_level,
)

RESERVE_TARGET = 40   # unseen active entries per (user, level) we aim to keep
BATCH_RAW = 24        # raw items to request per generation round (~14-18 survive)
MAX_ROUNDS = 3        # per (user, level) per night — cost guard


def _unseen_count(db, user_id: int, level: str) -> int:
    seen_sq = db.query(models.DailyExercise.pool_exercise_id).filter(
        models.DailyExercise.user_id == user_id,
        models.DailyExercise.pool_exercise_id.isnot(None),
    ).subquery()
    return db.query(models.ExercisePool).filter(
        models.ExercisePool.level == level,
        models.ExercisePool.is_active == True,  # noqa: E712
        models.ExercisePool.id.notin_(seen_sq.select()),
    ).count()


async def replenish():
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=14)
        active_ids = {
            row[0] for row in db.query(models.DailyExercise.user_id).filter(
                models.DailyExercise.completed_at >= cutoff,
            ).distinct().all()
        }
        users = db.query(models.User).filter(models.User.id.in_(active_ids)).all() if active_ids else []
        print(f"[replenish] active users: {[u.id for u in users]}")
        for user in users:
            # daily draws at user.level, bonus at the next level — keep both stocked
            for level in {user.level, _next_level(user.level)}:
                for round_no in range(MAX_ROUNDS):
                    unseen = _unseen_count(db, user.id, level)
                    if unseen >= RESERVE_TARGET:
                        print(f"[replenish] user={user.id} level={level} reserve={unseen} ok")
                        break
                    print(f"[replenish] user={user.id} level={level} reserve={unseen} < {RESERVE_TARGET} → generating (round {round_no + 1})")
                    topics = _select_topics_for_generation(user, db)
                    themes = _select_interest_themes(user.content_preferences)
                    raw = await _generate_exercises(
                        user, BATCH_RAW, themes, level=level, topics=topics or None, db=db,
                    )
                    validated = _validate_batch(raw, user, db, label=f"replenish:{level}")
                    topic_ids = {t.slug: t.id for t in (topics or [])}
                    saved = 0
                    for item in validated:
                        if _save_to_pool(item, level, topic_ids.get(item.get("topic_slug")), db):
                            saved += 1
                    db.commit()
                    print(f"[replenish] user={user.id} level={level} saved={saved}")
    finally:
        db.close()


if __name__ == "__main__":
    if not os.environ.get("MISTRAL_API_KEY"):
        print("[replenish] MISTRAL_API_KEY not set — aborting", file=sys.stderr)
        sys.exit(1)
    asyncio.run(replenish())
    print("[replenish] done")
