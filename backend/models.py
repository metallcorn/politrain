from sqlalchemy import (
    Column, Integer, String, Text, Boolean, Float, Date, DateTime,
    ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    native_language = Column(String(5), nullable=False, default="ru")
    target_language = Column(String(5), nullable=False, default="pl")
    level = Column(String(5), nullable=False, default="A0")
    xp = Column(Integer, default=0)
    streak_days = Column(Integer, default=0)
    last_activity = Column(Date, nullable=True)
    onboarding_done = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    total_training_seconds = Column(Integer, default=0)
    best_streak = Column(Integer, default=0)

    topic_progress = relationship("UserTopicProgress", back_populates="user", cascade="all, delete-orphan")
    vocabulary = relationship("UserVocabulary", back_populates="user", cascade="all, delete-orphan")
    exercise_history = relationship("UserExerciseHistory", back_populates="user", cascade="all, delete-orphan")
    chat_sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")
    achievements = relationship("UserAchievement", back_populates="user", cascade="all, delete-orphan")
    daily_activity = relationship("DailyActivity", back_populates="user", cascade="all, delete-orphan")
    content_preferences = relationship("UserContentPreferences", back_populates="user", uselist=False, cascade="all, delete-orphan")
    daily_exercises = relationship("DailyExercise", back_populates="user", cascade="all, delete-orphan")


class Topic(Base):
    __tablename__ = "topics"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    title_ru = Column(String(200), nullable=False)
    title_en = Column(String(200), nullable=False)
    description_ru = Column(Text, nullable=True)
    description_en = Column(Text, nullable=True)
    explanation_ru = Column(Text, nullable=True)
    explanation_en = Column(Text, nullable=True)
    level_required = Column(String(5), nullable=False)
    order_index = Column(Integer, nullable=True)
    parent_id = Column(Integer, ForeignKey("topics.id"), nullable=True)

    children = relationship("Topic", back_populates="parent")
    parent = relationship("Topic", back_populates="children", remote_side=[id])
    exercises = relationship("Exercise", back_populates="topic")
    vocabulary = relationship("Vocabulary", back_populates="topic")
    user_progress = relationship("UserTopicProgress", back_populates="topic")


class UserTopicProgress(Base):
    __tablename__ = "user_topic_progress"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=False)
    status = Column(String(20), default="locked")  # locked|available|in_progress|done|needs_review
    score = Column(Float, default=0.0)
    attempts = Column(Integer, default=0)
    last_practiced = Column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint("user_id", "topic_id"),)

    user = relationship("User", back_populates="topic_progress")
    topic = relationship("Topic", back_populates="user_progress")


class Vocabulary(Base):
    __tablename__ = "vocabulary"

    id = Column(Integer, primary_key=True, index=True)
    polish = Column(String(200), nullable=False)
    translation_ru = Column(String(200), nullable=False)
    translation_en = Column(String(200), nullable=False)
    example_sentence = Column(Text, nullable=True)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=True)
    level = Column(String(5), nullable=False)

    topic = relationship("Topic", back_populates="vocabulary")
    user_vocabulary = relationship("UserVocabulary", back_populates="vocab")


class UserVocabulary(Base):
    __tablename__ = "user_vocabulary"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    vocab_id = Column(Integer, ForeignKey("vocabulary.id"), nullable=False)
    ease_factor = Column(Float, default=2.5)
    interval_days = Column(Integer, default=1)
    next_review = Column(Date, nullable=True)
    repetitions = Column(Integer, default=0)
    correct_streak = Column(Integer, default=0)
    last_reviewed = Column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint("user_id", "vocab_id"),)

    user = relationship("User", back_populates="vocabulary")
    vocab = relationship("Vocabulary", back_populates="user_vocabulary")


class Exercise(Base):
    __tablename__ = "exercises"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(30), nullable=False)  # fill_blank|translate|order_words|multiple_choice|write|flashcard
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=True)
    level = Column(String(5), nullable=False)
    question = Column(Text, nullable=False)
    correct_answer = Column(Text, nullable=False)
    options = Column(Text, nullable=True)  # JSON array
    hint = Column(Text, nullable=True)
    explanation = Column(Text, nullable=True)
    content_type = Column(String(30), nullable=True)  # conversational|idiom|situational|grammar
    translation = Column(Text, nullable=True)
    is_flagged = Column(Boolean, default=False)

    topic = relationship("Topic", back_populates="exercises")
    history = relationship("UserExerciseHistory", back_populates="exercise")
    reports = relationship("ExerciseReport", back_populates="exercise")


class UserExerciseHistory(Base):
    __tablename__ = "user_exercise_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    exercise_id = Column(Integer, ForeignKey("exercises.id"), nullable=True)
    is_correct = Column(Boolean, nullable=True)
    user_answer = Column(Text, nullable=True)
    time_spent_sec = Column(Integer, nullable=True)
    content_hash = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=func.now())

    user = relationship("User", back_populates="exercise_history")
    exercise = relationship("Exercise", back_populates="history")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=func.now())
    ended_at = Column(DateTime, nullable=True)
    message_count = Column(Integer, default=0)
    topic = Column(String(200), nullable=True)

    user = relationship("User", back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False)
    role = Column(String(10), nullable=False)  # user|assistant
    content = Column(Text, nullable=False)
    corrections = Column(Text, nullable=True)  # JSON
    created_at = Column(DateTime, default=func.now())

    session = relationship("ChatSession", back_populates="messages")


class Achievement(Base):
    __tablename__ = "achievements"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(100), unique=True, nullable=False)
    title_ru = Column(String(200), nullable=False)
    title_en = Column(String(200), nullable=False)
    description_ru = Column(Text, nullable=True)
    description_en = Column(Text, nullable=True)
    icon = Column(String(50), nullable=True)
    xp_reward = Column(Integer, default=0)
    condition_type = Column(String(50), nullable=True)
    condition_value = Column(Integer, nullable=True)

    user_achievements = relationship("UserAchievement", back_populates="achievement")


class AIExplanationCache(Base):
    __tablename__ = "ai_explanation_cache"

    id = Column(Integer, primary_key=True, index=True)
    cache_key = Column(String(64), unique=True, nullable=False, index=True)
    level = Column(Integer, nullable=False, default=1)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now())


class UserKnownExpression(Base):
    __tablename__ = "user_known_expressions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    expression = Column(String(300), nullable=False)  # Polish idiom/expression
    meaning = Column(String(300), nullable=True)       # Translation in user's native language
    drilled_at = Column(DateTime, nullable=True)       # null = not yet turned into an exercise
    created_at = Column(DateTime, default=func.now())


class UserAchievement(Base):
    __tablename__ = "user_achievements"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    achievement_id = Column(Integer, ForeignKey("achievements.id"), nullable=False)
    earned_at = Column(DateTime, default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "achievement_id"),)

    user = relationship("User", back_populates="achievements")
    achievement = relationship("Achievement", back_populates="user_achievements")


class DailyActivity(Base):
    __tablename__ = "daily_activity"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False)
    xp_earned = Column(Integer, default=0)
    exercises_done = Column(Integer, default=0)
    chat_messages = Column(Integer, default=0)
    minutes_spent = Column(Integer, default=0)

    __table_args__ = (UniqueConstraint("user_id", "date"),)

    user = relationship("User", back_populates="daily_activity")


class ExercisePool(Base):
    """Shared pool of AI-generated exercises across all users."""
    __tablename__ = "exercise_pool"

    id = Column(Integer, primary_key=True, index=True)
    exercise_type = Column(String(30), nullable=False)
    level = Column(String(5), nullable=False)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=True)
    content = Column(Text, nullable=False)       # JSON, same structure as DailyExercise.content
    question_norm = Column(String(500), nullable=False, unique=True)  # normalized question for global dedup
    content_type = Column(String(30), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    report_count = Column(Integer, nullable=False, default=0)
    use_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=func.now())


class DailyExercise(Base):
    __tablename__ = "daily_exercises"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False)
    exercise_type = Column(String(30), nullable=False)
    content = Column(Text, nullable=False)  # JSON
    source = Column(String(10), nullable=False)  # new|weak|review
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=True)
    content_type = Column(String(30), nullable=True)
    pool_exercise_id = Column(Integer, ForeignKey("exercise_pool.id"), nullable=True)
    is_completed = Column(Boolean, default=False)
    is_correct = Column(Boolean, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    generated_at = Column(DateTime, default=func.now())
    next_review = Column(Date, nullable=True)
    srs_interval_days = Column(Integer, default=0)
    srs_repetitions = Column(Integer, default=0)

    user = relationship("User", back_populates="daily_exercises")


class UserContentPreferences(Base):
    __tablename__ = "user_content_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    conversational_weight = Column(Float, default=0.25)
    idiom_weight = Column(Float, default=0.25)
    situational_weight = Column(Float, default=0.25)
    grammar_weight = Column(Float, default=0.25)
    session_length = Column(String(10), default="standard")
    daily_goal_minutes = Column(Integer, default=15)
    interest_themes = Column(Text, nullable=True)  # JSON list of theme keys
    updated_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="content_preferences")


class ExerciseReport(Base):
    __tablename__ = "exercise_reports"

    id = Column(Integer, primary_key=True, index=True)
    exercise_id = Column(Integer, ForeignKey("exercises.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    comment = Column(Text, nullable=True)
    exercise_snapshot = Column(Text, nullable=False)  # JSON: question + correct_answer + options
    created_at = Column(DateTime, default=func.now())

    exercise = relationship("Exercise", back_populates="reports")
    user = relationship("User")


class AdminFeedback(Base):
    """General feedback from admin user — captures URL and page snapshot."""
    __tablename__ = "admin_feedback"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    comment = Column(Text, nullable=False)
    url = Column(String(500), nullable=True)
    page_snapshot = Column(Text, nullable=True)  # visible text from the page
    is_resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())

    user = relationship("User")


class SessionRating(Base):
    """User rating for a completed training session."""
    __tablename__ = "session_ratings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    mode = Column(String(20), nullable=True)
    rating = Column(Integer, nullable=True)  # 1-5, nullable if user skipped
    comment = Column(Text, nullable=True)
    exercise_ids = Column(Text, nullable=True)  # JSON array of daily_exercise_ids
    created_at = Column(DateTime, default=func.now())

    user = relationship("User")


class GeneratedExerciseReport(Base):
    """Reports for AI-generated exercises (daily/bonus pool, not static DB exercises)."""
    __tablename__ = "generated_exercise_reports"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    daily_exercise_id = Column(Integer, ForeignKey("daily_exercises.id"), nullable=True)
    level = Column(String(5), nullable=True)
    exercise_snapshot = Column(Text, nullable=False)  # JSON: full exercise content
    comment = Column(Text, nullable=True)
    is_resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())

    user = relationship("User")


class MistralCallLog(Base):
    """Logs every Mistral API call for cost tracking."""
    __tablename__ = "mistral_call_logs"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=func.now())
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    model = Column(String(50), nullable=False)
    purpose = Column(String(50), nullable=True)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    success = Column(Boolean, default=True)
    duration_ms = Column(Integer, default=0)
