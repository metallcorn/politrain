"""Seed ~70 achievements across meaningful dimensions (user 2026-08-05: «под сотню ачивок»).
Idempotent by slug. Titles/descriptions in RU (+ EN mirror). Run: python3 scripts/seed_achievements.py

condition_type values (checked in services/gamification.check_achievements):
  xp | streak | vocab_count(=used_words) | exercises_done | training_seconds |
  chat_messages | level_reached | all_level_topics(via slug alltopics_<level>) | first_lesson
"""
import os
import sqlite3

DB = os.path.join(os.path.dirname(__file__), "..", "politrain.db")


def _fmt_time(sec):
    h = sec // 3600
    return f"{h} ч"


ACH = []  # (slug, title_ru, title_en, desc_ru, icon, xp_reward, condition_type, condition_value)

# --- XP milestones ---
for val, icon in [(1000, "⭐"), (2500, "✨"), (5000, "🌟"), (10000, "💫"), (25000, "🔥"),
                  (50000, "🏅"), (75000, "🎖"), (100000, "🏆"), (150000, "👑"), (250000, "💎"), (500000, "🌈")]:
    ACH.append((f"xp_{val}", f"{val:,} XP".replace(",", " "), f"{val} XP",
                f"Набери {val:,} опыта".replace(",", " "), icon, 50, "xp", val))

# --- Streaks ---
for val, icon in [(3, "🔥"), (7, "📅"), (14, "🗓"), (30, "🌙"), (50, "💪"), (75, "🚀"),
                  (100, "💯"), (150, "⚡"), (200, "🏔"), (365, "🎂")]:
    ACH.append((f"streak_{val}", f"Серия {val}", f"{val}-day streak",
                f"Занимайся {val} дней подряд", icon, 100, "streak", val))

# --- Words used correctly ---
for val, icon in [(50, "🌱"), (100, "🌿"), (200, "📗"), (350, "📘"), (500, "📚"), (750, "📖"),
                  (1000, "🎓"), (1500, "🧠"), (2000, "💡"), (3000, "🗣"), (4000, "📜"), (5000, "🏛")]:
    ACH.append((f"words_{val}", f"{val} слов", f"{val} words",
                f"Правильно используй {val} разных слов", icon, 80, "vocab_count", val))

# --- Exercises done ---
for val, icon in [(10, "✅"), (50, "📝"), (100, "🎯"), (250, "🎲"), (500, "🏹"), (1000, "🎪"),
                  (1500, "⚙️"), (2500, "🛠"), (4000, "🏗"), (6000, "🚂"), (8000, "🛰"), (10000, "🌍")]:
    ACH.append((f"ex_{val}", f"{val} заданий", f"{val} exercises",
                f"Выполни {val} упражнений", icon, 60, "exercises_done", val))

# --- Training time ---
for sec, icon in [(3600, "⏱"), (10800, "⏲"), (18000, "🕐"), (36000, "🕓"), (54000, "🕘"),
                  (90000, "⌛"), (144000, "🧭"), (216000, "🌗"), (360000, "🏅")]:
    ACH.append((f"time_{sec}", f"{_fmt_time(sec)} практики", f"{_fmt_time(sec)} of practice",
                f"Позанимайся суммарно {_fmt_time(sec)}", icon, 70, "training_seconds", sec))

# --- Chat ---
for val, icon in [(10, "💬"), (25, "🗨"), (50, "🎙"), (100, "📣"), (250, "🎧"), (500, "🌐")]:
    ACH.append((f"chat_{val}", f"{val} реплик в чате", f"{val} chat messages",
                f"Напиши {val} сообщений собеседнику", icon, 50, "chat_messages", val))

# --- Level reached (auto-promotion) ---
for idx, lv, icon in [(1, "A1", "🥉"), (2, "A2", "🥈"), (3, "B1", "🥇"), (4, "B2", "🏆")]:
    ACH.append((f"level_{lv.lower()}", f"Уровень {lv}", f"Reached {lv}",
                f"Достигни уровня {lv}", icon, 200, "level_reached", idx))

# --- All topics of a level done ---
for lv, icon in [("a0", "🔰"), ("a1", "📗"), ("a2", "📘"), ("b1", "📙"), ("b2", "📕")]:
    ACH.append((f"alltopics_{lv}", f"Все темы {lv.upper()}", f"All {lv.upper()} topics",
                f"Освой все темы уровня {lv.upper()}", icon, 150, "all_level_topics", 0))

# --- keep the classic first lesson ---
ACH.append(("first_lesson", "Первый шаг", "First step", "Заверши первую тему", "👣", 20, "first_lesson", 1))


def main():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    ins = upd = 0
    for slug, tr, te, dr, icon, xp, ctype, cval in ACH:
        c.execute("SELECT id FROM achievements WHERE slug=?", (slug,))
        if c.fetchone():
            c.execute("UPDATE achievements SET title_ru=?, title_en=?, description_ru=?, icon=?, "
                      "xp_reward=?, condition_type=?, condition_value=? WHERE slug=?",
                      (tr, te, dr, icon, xp, ctype, cval, slug))
            upd += 1
        else:
            c.execute("INSERT INTO achievements (slug,title_ru,title_en,description_ru,description_en,"
                      "icon,xp_reward,condition_type,condition_value) VALUES (?,?,?,?,?,?,?,?,?)",
                      (slug, tr, te, dr, dr, icon, xp, ctype, cval))
            ins += 1
    conn.commit()
    c.execute("SELECT COUNT(*) FROM achievements")
    print(f"achievements inserted={ins} updated={upd}; total={c.fetchone()[0]}")
    conn.close()


if __name__ == "__main__":
    main()
