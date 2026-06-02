from pydantic import BaseModel, field_validator
from typing import Optional, List, Any
from datetime import datetime, date


# Auth
class RegisterRequest(BaseModel):
    username: str
    password: str
    native_language: str = "ru"

    @field_validator("username")
    @classmethod
    def username_valid(cls, v):
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Username must be at least 3 characters")
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Username must contain only letters, digits, _ or -")
        return v

    @field_validator("password")
    @classmethod
    def password_valid(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def strip_username(cls, v):
        return v.strip()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    username: str
    native_language: str
    target_language: str
    level: str
    xp: int
    streak_days: int
    onboarding_done: bool
    created_at: datetime
    is_admin: bool = False

    class Config:
        from_attributes = True


# Onboarding
class OnboardingSettings(BaseModel):
    native_language: str
    target_language: str = "pl"


class PlacementTestQuestion(BaseModel):
    id: int
    type: str
    question: str
    options: Optional[List[str]] = None
    level: str


class PlacementTestAnswer(BaseModel):
    question_id: int
    answer: str


class PlacementTestSubmit(BaseModel):
    answers: List[PlacementTestAnswer]


class PlacementTestResult(BaseModel):
    level: str
    correct_count: int
    total: int
    message: str


# Topics
class TopicResponse(BaseModel):
    id: int
    slug: str
    title_ru: str
    title_en: str
    description_ru: Optional[str]
    description_en: Optional[str]
    level_required: str
    order_index: Optional[int]
    status: Optional[str] = "locked"
    score: Optional[float] = 0.0

    class Config:
        from_attributes = True


class LessonResponse(BaseModel):
    topic_slug: str
    topic_title: str
    explanation: str
    exercises: List[Any] = []


# Vocabulary
class VocabResponse(BaseModel):
    id: int
    polish: str
    translation_ru: str
    translation_en: str
    example_sentence: Optional[str]
    level: str
    ease_factor: Optional[float] = 2.5
    interval_days: Optional[int] = 1
    next_review: Optional[date] = None
    repetitions: Optional[int] = 0

    class Config:
        from_attributes = True


class VocabReviewRequest(BaseModel):
    quality: int  # 0=don't know, 3=hard, 5=know


# Training
class ExerciseResponse(BaseModel):
    id: int
    type: str
    question: str
    correct_answer: str
    options: Optional[List[str]] = None
    hint: Optional[str] = None
    explanation: Optional[str] = None
    topic_id: Optional[int] = None
    source: Optional[str] = None

    class Config:
        from_attributes = True


class AnswerRequest(BaseModel):
    exercise_id: Optional[int] = None
    daily_exercise_id: Optional[int] = None
    vocab_id: Optional[int] = None
    user_answer: str
    time_spent_sec: Optional[int] = None
    quality: Optional[int] = None  # SM-2: 0=don't know, 3=hard, 5=know (for flashcards)
    hint_used: bool = False  # word hint was used — reduce XP by 1


class AnswerResponse(BaseModel):
    is_correct: bool
    correct_answer: str
    explanation: Optional[str] = None
    xp_earned: int = 0
    diacritic_hint: bool = False


class TrainingSessionResponse(BaseModel):
    exercises: List[Any]
    session_id: Optional[str] = None


# Chat
class ChatSessionResponse(BaseModel):
    id: int
    topic: Optional[str]
    created_at: datetime
    message_count: int

    class Config:
        from_attributes = True


class ChatMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    corrections: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class SendMessageRequest(BaseModel):
    content: str


class NewChatSessionRequest(BaseModel):
    topic: Optional[str] = None


# Exam
class ExamWritingSubmit(BaseModel):
    task_type: str
    task_description: str
    student_text: str


class ExamReadingSubmit(BaseModel):
    task_type: str = "reading"
    answers: List[str]
    questions_data: Any


# Profile
class SessionCompleteRequest(BaseModel):
    duration_seconds: int


class SessionRatingRequest(BaseModel):
    mode: Optional[str] = None
    rating: Optional[int] = None  # 1-5
    comment: Optional[str] = None
    exercise_ids: Optional[list[int]] = None


class ExplainRequest(BaseModel):
    exercise_type: str
    question: str
    correct_answer: str
    user_answer: Optional[str] = None
    is_correct: bool
    explanation: Optional[str] = None
    translation: Optional[str] = None
    level: int = 1  # 1 = brief, 2 = detailed with examples


class ProfileResponse(BaseModel):
    id: int
    username: str
    native_language: str
    level: str
    xp: int
    streak_days: int
    best_streak: int = 0
    game_level: int
    game_level_name: str
    xp_to_next_level: int
    xp_rank_start: int = 0
    progress_to_b1: float
    total_exercises: int
    total_chat_messages: int
    vocab_count: int
    total_training_seconds: int = 0
    weak_spots: List[Any] = []
    created_at: datetime

    class Config:
        from_attributes = True


class AchievementResponse(BaseModel):
    id: int
    slug: str
    title_ru: str
    title_en: str
    description_ru: Optional[str]
    description_en: Optional[str]
    icon: Optional[str]
    xp_reward: int
    earned: bool
    earned_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ContentPreferencesRequest(BaseModel):
    conversational_weight: float
    idiom_weight: float
    situational_weight: float
    grammar_weight: float
    session_length: str = "standard"
    daily_goal_minutes: int = 15
    interest_themes: Optional[List[str]] = None

    @field_validator("session_length")
    @classmethod
    def valid_session_length(cls, v):
        if v not in ("short", "standard", "long"):
            raise ValueError("session_length must be short, standard, or long")
        return v


class ContentPreferencesResponse(BaseModel):
    conversational_weight: float
    idiom_weight: float
    situational_weight: float
    grammar_weight: float
    session_length: str
    daily_goal_minutes: int
    interest_themes: Optional[Any] = None

    @field_validator("interest_themes", mode="before")
    @classmethod
    def parse_interest_themes(cls, v):
        if isinstance(v, str):
            try:
                import json
                return json.loads(v)
            except Exception:
                return []
        return v

    class Config:
        from_attributes = True


class ProfileSettingsUpdate(BaseModel):
    native_language: Optional[str] = None


class ExerciseReportCreate(BaseModel):
    comment: Optional[str] = None


class GeneratedExerciseReportCreate(BaseModel):
    daily_exercise_id: Optional[int] = None
    exercise_id: Optional[int] = None
    comment: Optional[str] = None
