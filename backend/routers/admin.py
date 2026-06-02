import json
import os
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user
import models

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")


def require_admin(current_user: models.User = Depends(get_current_user)):
    if current_user.username != ADMIN_USERNAME:
        raise HTTPException(status_code=403, detail="Admin only")
    return current_user


@router.get("/reports")
def list_reports(
    resolved: bool = False,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    reports = (
        db.query(models.GeneratedExerciseReport)
        .filter(models.GeneratedExerciseReport.is_resolved == resolved)
        .order_by(models.GeneratedExerciseReport.created_at.desc())
        .all()
    )
    result = []
    for r in reports:
        try:
            snap = json.loads(r.exercise_snapshot)
        except Exception:
            snap = {}
        result.append({
            "id": r.id,
            "user_id": r.user_id,
            "level": r.level,
            "comment": r.comment,
            "is_resolved": r.is_resolved,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "exercise": snap,
        })
    return result


@router.post("/reports/{report_id}/resolve")
def resolve_report(
    report_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    report = db.query(models.GeneratedExerciseReport).filter(
        models.GeneratedExerciseReport.id == report_id
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    report.is_resolved = True
    db.commit()
    return {"ok": True}


@router.delete("/reports/{report_id}")
def delete_report(
    report_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    report = db.query(models.GeneratedExerciseReport).filter(
        models.GeneratedExerciseReport.id == report_id
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    db.delete(report)
    db.commit()
    return {"ok": True}


@router.get("/stats")
def admin_stats(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    total_users = db.query(models.User).count()
    total_reports = db.query(models.GeneratedExerciseReport).count()
    open_reports = db.query(models.GeneratedExerciseReport).filter(
        models.GeneratedExerciseReport.is_resolved == False
    ).count()
    total_exercises_done = db.query(models.DailyExercise).filter(
        models.DailyExercise.is_completed == True
    ).count()
    return {
        "total_users": total_users,
        "total_reports": total_reports,
        "open_reports": open_reports,
        "total_exercises_done": total_exercises_done,
    }


@router.get("/users")
def list_users(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    users = db.query(models.User).order_by(models.User.created_at.desc()).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "level": u.level,
            "xp": u.xp,
            "streak_days": u.streak_days,
            "native_language": u.native_language,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "onboarding_done": u.onboarding_done,
        }
        for u in users
    ]


@router.post("/feedback")
def submit_feedback(
    payload: dict,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    fb = models.AdminFeedback(
        user_id=current_admin.id,
        comment=payload.get("comment", ""),
        url=payload.get("url"),
        page_snapshot=payload.get("page_snapshot"),
    )
    db.add(fb)
    db.commit()
    return {"ok": True, "id": fb.id}


@router.get("/feedback")
def get_feedback(
    resolved: bool = False,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    items = (
        db.query(models.AdminFeedback)
        .filter(models.AdminFeedback.is_resolved == resolved)
        .order_by(models.AdminFeedback.created_at.desc())
        .all()
    )
    return [
        {
            "id": i.id,
            "comment": i.comment,
            "url": i.url,
            "page_snapshot": i.page_snapshot,
            "created_at": i.created_at.isoformat() if i.created_at else None,
            "is_resolved": i.is_resolved,
        }
        for i in items
    ]


@router.patch("/feedback/{feedback_id}/resolve")
def resolve_feedback(
    feedback_id: int,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    fb = db.query(models.AdminFeedback).filter(models.AdminFeedback.id == feedback_id).first()
    if not fb:
        raise HTTPException(status_code=404, detail="Not found")
    fb.is_resolved = True
    db.commit()
    return {"ok": True}


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"ok": True}


@router.get("/exercise-pool/stats")
def pool_stats(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    total = db.query(models.ExercisePool).count()
    active = db.query(models.ExercisePool).filter(models.ExercisePool.is_active == True).count()
    inactive = total - active

    by_level_rows = db.query(models.ExercisePool.level, func.count()).group_by(models.ExercisePool.level).all()
    by_type_rows = db.query(models.ExercisePool.exercise_type, func.count()).group_by(models.ExercisePool.exercise_type).all()

    return {
        "total": total,
        "active": active,
        "inactive": inactive,
        "by_level": {row[0]: row[1] for row in by_level_rows},
        "by_type": {row[0]: row[1] for row in by_type_rows},
    }


@router.post("/exercise-pool/{pool_id}/toggle")
def toggle_pool_exercise(
    pool_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    pool_ex = db.query(models.ExercisePool).filter(models.ExercisePool.id == pool_id).first()
    if not pool_ex:
        raise HTTPException(status_code=404, detail="Pool exercise not found")
    pool_ex.is_active = not pool_ex.is_active
    db.commit()
    return {"ok": True, "id": pool_id, "is_active": pool_ex.is_active}


# Mistral pricing per 1M tokens (USD)
_PRICE = {
    "mistral-large-latest": {"in": 2.0, "out": 6.0},
    "mistral-small-latest": {"in": 0.2, "out": 0.6},
}

def _cost(model, input_tokens, output_tokens):
    p = _PRICE.get(model, {"in": 2.0, "out": 6.0})
    return round((input_tokens * p["in"] + output_tokens * p["out"]) / 1_000_000, 6)


@router.get("/mistral-usage")
def get_mistral_usage(
    days: int = 30,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    since = date.today() - timedelta(days=days - 1)

    # By day
    day_rows = db.execute(
        __import__('sqlalchemy').text(
            "SELECT date(created_at) as d, model, "
            "SUM(input_tokens) as inp, SUM(output_tokens) as out, "
            "COUNT(*) as calls, SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) as failed "
            "FROM mistral_call_logs WHERE date(created_at) >= :since "
            "GROUP BY d, model ORDER BY d"
        ),
        {"since": since.isoformat()},
    ).fetchall()

    # Build day→model map
    day_map = {}
    for row in day_rows:
        d, model, inp, out, calls, failed = row
        if d not in day_map:
            day_map[d] = {}
        day_map[d][model] = {
            "calls": calls, "failed": failed,
            "input_tokens": inp or 0, "output_tokens": out or 0,
            "cost": _cost(model, inp or 0, out or 0),
        }

    days_list = []
    for i in range(days):
        d = (since + timedelta(days=i)).isoformat()
        days_list.append({"date": d, "models": day_map.get(d, {})})

    # By purpose
    purpose_rows = db.execute(
        __import__('sqlalchemy').text(
            "SELECT purpose, model, SUM(input_tokens) as inp, SUM(output_tokens) as out, COUNT(*) as calls "
            "FROM mistral_call_logs WHERE date(created_at) >= :since "
            "GROUP BY purpose, model ORDER BY calls DESC"
        ),
        {"since": since.isoformat()},
    ).fetchall()

    by_purpose = {}
    for row in purpose_rows:
        p, model, inp, out, calls = row
        key = p or "unknown"
        if key not in by_purpose:
            by_purpose[key] = {"calls": 0, "cost": 0.0}
        by_purpose[key]["calls"] += calls
        by_purpose[key]["cost"] = round(by_purpose[key]["cost"] + _cost(model, inp or 0, out or 0), 6)

    # By user
    user_rows = db.execute(
        __import__('sqlalchemy').text(
            "SELECT m.user_id, u.username, SUM(m.input_tokens) as inp, SUM(m.output_tokens) as out, COUNT(*) as calls "
            "FROM mistral_call_logs m LEFT JOIN users u ON u.id=m.user_id "
            "WHERE date(m.created_at) >= :since "
            "GROUP BY m.user_id ORDER BY calls DESC LIMIT 20"
        ),
        {"since": since.isoformat()},
    ).fetchall()

    by_user = [
        {
            "user_id": r[0], "username": r[1] or "system",
            "calls": r[4],
            "input_tokens": r[2] or 0, "output_tokens": r[3] or 0,
            "cost": _cost("mistral-large-latest", r[2] or 0, r[3] or 0),
        }
        for r in user_rows
    ]

    # Totals
    total_row = db.execute(
        __import__('sqlalchemy').text(
            "SELECT SUM(input_tokens), SUM(output_tokens), COUNT(*) "
            "FROM mistral_call_logs WHERE date(created_at) >= :since"
        ),
        {"since": since.isoformat()},
    ).fetchone()
    total_inp, total_out, total_calls = total_row
    total_inp, total_out, total_calls = total_inp or 0, total_out or 0, total_calls or 0

    return {
        "days": days_list,
        "by_purpose": [{"purpose": k, **v} for k, v in by_purpose.items()],
        "by_user": by_user,
        "totals": {
            "calls": total_calls,
            "input_tokens": total_inp,
            "output_tokens": total_out,
            "total_tokens": total_inp + total_out,
            "cost_usd": round(
                sum(_cost(r[1], r[2] or 0, r[3] or 0)
                    for r in db.execute(
                        __import__('sqlalchemy').text(
                            "SELECT user_id, model, SUM(input_tokens), SUM(output_tokens) "
                            "FROM mistral_call_logs WHERE date(created_at) >= :since GROUP BY model"
                        ),
                        {"since": since.isoformat()},
                    ).fetchall()),
                4,
            ),
        },
    }
