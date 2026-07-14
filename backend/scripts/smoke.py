"""Post-restart invariant smoke check. PASSIVE by design: reads the API and the DB but
never creates sessions or calls Mistral, so it's free to run after every restart.

    cd backend && python3 scripts/smoke.py    # SYSTEM python3 (venv lacks PyJWT); exits 1 on FAIL
Checks (the exact failure modes we shipped at least once):
  - /health answers
  - /training/stats has all expected fields
  - per-level UNSEEN pool reserve for active users (pool ran dry → 11/20 sessions)
  - recent served session batches are full-length (short-session regressions)
  - Mistral failure count over 24h (rate limits / timeouts)
  - error/practice queues are readable and sane
"""
import json
import os
import sqlite3
import sys
import urllib.request
from datetime import datetime, timedelta

BASE = "http://localhost:8000"
DB = os.path.join(os.path.dirname(__file__), "..", "politrain.db")
FAILS: list = []
WARNS: list = []


def check(name, ok, detail="", warn_only=False):
    tag = "OK " if ok else ("WARN" if warn_only else "FAIL")
    print(f"[{tag}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        (WARNS if warn_only else FAILS).append(name)


def http_json(path, token=None):
    req = urllib.request.Request(BASE + path)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def make_token(user_id=2):
    import jwt  # PyJWT from the venv
    secret = None
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    for line in open(env_path):
        if line.startswith("SECRET_KEY="):
            secret = line.split("=", 1)[1].strip()
    from datetime import timezone
    exp = datetime.now(timezone.utc) + timedelta(minutes=10)
    return jwt.encode({"sub": str(user_id), "exp": exp}, secret, algorithm="HS256")


def main():
    # 1. health — retry: startup migrations take a few seconds after a restart
    import time
    last_err = None
    for attempt in range(5):
        try:
            h = http_json("/health")
            check("health", h.get("status") == "healthy")
            break
        except Exception as e:
            last_err = e
            time.sleep(3)
    else:
        check("health", False, str(last_err))
        finish()  # nothing else will work

    token = make_token()

    # 2. stats shape
    try:
        s = http_json("/api/v1/training/stats", token)
        need = {"total_exercises", "correct", "errors", "accuracy", "today_done", "today_total", "practice_due"}
        missing = need - set(s)
        check("stats fields", not missing, f"missing: {missing}" if missing else
              f"errors={s['errors']} practice_due={s['practice_due']}")
    except Exception as e:
        check("stats fields", False, str(e))

    conn = sqlite3.connect(DB)
    c = conn.cursor()

    # 3. unseen pool reserve per active user/level (this is what starved sessions)
    c.execute("SELECT DISTINCT user_id FROM daily_exercises WHERE completed_at >= datetime('now','-14 days')")
    active = [r[0] for r in c.fetchall()]
    order = ["A0", "A1", "A2", "B1", "B2"]
    for uid in active:
        c.execute("SELECT level FROM users WHERE id=?", (uid,))
        row = c.fetchone()
        if not row:
            continue
        lvl = row[0]
        nxt = order[min(order.index(lvl) + 1, len(order) - 1)] if lvl in order else lvl
        for level in {lvl, nxt}:
            c.execute("""SELECT COUNT(*) FROM exercise_pool p WHERE p.level=? AND p.is_active=1
                         AND p.id NOT IN (SELECT pool_exercise_id FROM daily_exercises
                                          WHERE user_id=? AND pool_exercise_id IS NOT NULL)""",
                      (level, uid))
            unseen = c.fetchone()[0]
            check(f"pool reserve u{uid}/{level}", unseen >= 20,
                  f"unseen={unseen} (target ≥40, nightly job tops up)", warn_only=True)

    # 4. recent session batches full-length (grouped by generation second)
    c.execute("""SELECT source, substr(generated_at,1,16) g, COUNT(*) FROM daily_exercises
                 WHERE source='bonus' AND generated_at >= datetime('now','-2 days')
                 GROUP BY user_id, g HAVING COUNT(*) >= 5 ORDER BY g DESC LIMIT 5""")
    for src, g, n in c.fetchall():
        check(f"bonus batch {g}", n >= 15, f"served {n} (expect ~20)", warn_only=True)

    # 5. Mistral failures 24h
    c.execute("SELECT COUNT(*) FROM mistral_call_logs WHERE success=0 AND created_at >= datetime('now','-1 day')")
    fails = c.fetchone()[0]
    check("mistral failures 24h", fails <= 3, f"{fails} failed calls", warn_only=fails <= 10)

    # 6. queues readable
    c.execute("SELECT COUNT(*) FROM generated_exercise_reports WHERE is_resolved=0")
    check("open reports", True, str(c.fetchone()[0]))
    c.execute("SELECT COUNT(*) FROM admin_feedback WHERE is_resolved=0")
    check("open feedback", True, str(c.fetchone()[0]))

    conn.close()
    finish()


def finish():
    print()
    if FAILS:
        print(f"SMOKE FAILED: {FAILS}")
        sys.exit(1)
    print(f"SMOKE OK ({len(WARNS)} warnings)" if WARNS else "SMOKE OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
