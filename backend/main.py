from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv

load_dotenv()

from database import engine, Base
import models

Base.metadata.create_all(bind=engine)

# Add columns not covered by create_all (ALTER TABLE is idempotent via try/except)
def _migrate():
    with engine.connect() as conn:
        for sql in [
            "ALTER TABLE topics ADD COLUMN explanation_ru TEXT",
            "ALTER TABLE topics ADD COLUMN explanation_en TEXT",
            "ALTER TABLE chat_sessions ADD COLUMN scenario VARCHAR(50)",
            "ALTER TABLE exercises ADD COLUMN is_flagged INTEGER DEFAULT 0",
            "ALTER TABLE user_content_preferences ADD COLUMN interest_themes TEXT",
            "ALTER TABLE users ADD COLUMN total_training_seconds INTEGER DEFAULT 0",
            "INSERT OR IGNORE INTO achievements (slug,title_ru,title_en,description_ru,icon,xp_reward,condition_type,condition_value) VALUES ('time_1h','Первый час','First Hour','Провёл 1 час за обучением','⏱',30,'training_seconds',3600)",
            "INSERT OR IGNORE INTO achievements (slug,title_ru,title_en,description_ru,icon,xp_reward,condition_type,condition_value) VALUES ('time_5h','Пять часов','Five Hours','Провёл 5 часов за обучением','🕐',100,'training_seconds',18000)",
            "INSERT OR IGNORE INTO achievements (slug,title_ru,title_en,description_ru,icon,xp_reward,condition_type,condition_value) VALUES ('time_marathon','Марафон','Marathon','Провёл 10 часов за обучением','🏆',200,'training_seconds',36000)",
            "ALTER TABLE daily_exercises ADD COLUMN next_review DATE",
            "ALTER TABLE daily_exercises ADD COLUMN srs_interval_days INTEGER DEFAULT 0",
            "ALTER TABLE daily_exercises ADD COLUMN srs_repetitions INTEGER DEFAULT 0",
            "CREATE TABLE IF NOT EXISTS session_ratings (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id), mode VARCHAR(20), rating INTEGER, comment TEXT, exercise_ids TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
            "CREATE TABLE IF NOT EXISTS mistral_call_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, user_id INTEGER REFERENCES users(id), model VARCHAR(50) NOT NULL, purpose VARCHAR(50), input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0, success INTEGER DEFAULT 1, duration_ms INTEGER DEFAULT 0)",
            "CREATE INDEX IF NOT EXISTS idx_mistral_call_logs_created_at ON mistral_call_logs(created_at)",
            "CREATE TABLE IF NOT EXISTS exercise_pool (id INTEGER PRIMARY KEY AUTOINCREMENT, exercise_type VARCHAR(30) NOT NULL, level VARCHAR(5) NOT NULL, topic_id INTEGER REFERENCES topics(id), content TEXT NOT NULL, question_norm TEXT NOT NULL, content_type VARCHAR(30), is_active INTEGER NOT NULL DEFAULT 1, report_count INTEGER NOT NULL DEFAULT 0, use_count INTEGER NOT NULL DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_pool_question_norm ON exercise_pool(question_norm)",
            "CREATE INDEX IF NOT EXISTS idx_pool_level_active ON exercise_pool(level, is_active)",
            "CREATE INDEX IF NOT EXISTS idx_pool_topic_active ON exercise_pool(topic_id, is_active)",
            "ALTER TABLE daily_exercises ADD COLUMN pool_exercise_id INTEGER REFERENCES exercise_pool(id)",
            "CREATE INDEX IF NOT EXISTS idx_de_pool_user ON daily_exercises(pool_exercise_id, user_id)",
            "ALTER TABLE generated_exercise_reports ADD COLUMN daily_exercise_id INTEGER REFERENCES daily_exercises(id)",
            "ALTER TABLE users ADD COLUMN best_streak INTEGER DEFAULT 0",
            "UPDATE users SET best_streak = streak_days WHERE best_streak = 0 AND streak_days > 0",
            "ALTER TABLE mistral_call_logs ADD COLUMN error_message TEXT",
            "ALTER TABLE user_content_preferences ADD COLUMN recent_themes TEXT",
            "ALTER TABLE daily_exercises ADD COLUMN user_answer TEXT",
        ]:
            try:
                conn.execute(__import__('sqlalchemy').text(sql))
                conn.commit()
            except Exception:
                pass  # Column already exists

_migrate()

from routers import auth, onboarding, topics, vocabulary, training, chat, exam, profile, stt_tts, admin

app = FastAPI(title="Politrain API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"

app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(onboarding.router, prefix=API_PREFIX)
app.include_router(topics.router, prefix=API_PREFIX)
app.include_router(vocabulary.router, prefix=API_PREFIX)
app.include_router(training.router, prefix=API_PREFIX)
app.include_router(chat.router, prefix=API_PREFIX)
app.include_router(exam.router, prefix=API_PREFIX)
app.include_router(profile.router, prefix=API_PREFIX)
app.include_router(stt_tts.router, prefix=API_PREFIX)
app.include_router(admin.router, prefix=API_PREFIX)


@app.get("/")
def root():
    return {"status": "ok", "app": "Politrain API"}


@app.get("/health")
def health():
    return {"status": "healthy"}
