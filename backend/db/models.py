"""
Database models for the learning agent.
Uses SQLite via SQLAlchemy - no server needed, stored in a local file.
"""

import json
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Float,
    DateTime, Text, ForeignKey, Boolean, inspect, text
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/student_data/learning_agent.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    enrollments = relationship("Enrollment", back_populates="student")
    sessions = relationship("LearningSession", back_populates="student")


class Curriculum(Base):
    __tablename__ = "curricula"

    id = Column(Integer, primary_key=True, index=True)
    job_title = Column(String, nullable=False)
    job_description = Column(Text, nullable=False)
    # Stored as JSON string: list of {topic, description, prerequisites, hours, difficulty}
    modules_json = Column(Text, nullable=False, default="[]")
    # Stored as JSON string: list of required skill strings
    required_skills_json = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)

    enrollments = relationship("Enrollment", back_populates="curriculum")

    @property
    def modules(self) -> list:
        return json.loads(self.modules_json)

    @modules.setter
    def modules(self, value: list):
        self.modules_json = json.dumps(value)

    @property
    def required_skills(self) -> list:
        return json.loads(self.required_skills_json)

    @required_skills.setter
    def required_skills(self, value: list):
        self.required_skills_json = json.dumps(value)


class Enrollment(Base):
    __tablename__ = "enrollments"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    curriculum_id = Column(Integer, ForeignKey("curricula.id"), nullable=False)
    current_module_index = Column(Integer, default=0)
    # JSON: {skill_name: mastery_score (0-100)}
    mastery_scores_json = Column(Text, default="{}")
    job_readiness_score = Column(Float, default=0.0)
    enrolled_at = Column(DateTime, default=datetime.utcnow)
    last_active_at = Column(DateTime, default=datetime.utcnow)

    student = relationship("Student", back_populates="enrollments")
    curriculum = relationship("Curriculum", back_populates="enrollments")

    @property
    def mastery_scores(self) -> dict:
        return json.loads(self.mastery_scores_json or "{}")

    @mastery_scores.setter
    def mastery_scores(self, value: dict):
        self.mastery_scores_json = json.dumps(value)

    def update_mastery(self, skill: str, result: str, days_since: float = 0):
        """Update mastery score for a skill using spaced repetition decay."""
        scores = self.mastery_scores
        current = scores.get(skill, 0)
        decay = 0.98 ** days_since  # small daily decay

        if result == "correct":
            new_score = min(100, current * decay + 15)
        elif result == "partial":
            new_score = min(100, current * decay + 7)
        else:
            new_score = max(0, current * decay - 3)

        scores[skill] = round(new_score, 1)
        self.mastery_scores = scores
        return new_score

    def compute_job_readiness(self) -> float:
        """Weighted average mastery across all required skills."""
        curriculum = self.curriculum
        if not curriculum:
            return 0.0
        required = curriculum.required_skills
        if not required:
            return 0.0
        scores = self.mastery_scores
        total = sum(scores.get(skill, 0) for skill in required)
        return round(total / len(required), 1)


class LearningSession(Base):
    __tablename__ = "learning_sessions"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    enrollment_id = Column(Integer, ForeignKey("enrollments.id"), nullable=False)
    topic = Column(String, nullable=False)
    module_index = Column(Integer, nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    exercises_attempted = Column(Integer, default=0)
    exercises_correct = Column(Integer, default=0)

    # NEW: persist generated content so it survives logout / page reload.
    lesson_text = Column(Text, nullable=True)
    exercises_json = Column(Text, nullable=True, default="[]")
    current_exercise_index = Column(Integer, default=0)
    completed = Column(Boolean, default=False)
    # 0 = original lesson, 1+ = remediation rounds for the same module.
    remediation_round = Column(Integer, default=0)
    # Concepts the student got wrong in the previous session for this module
    # (used to focus the remediation lesson). JSON-encoded list of strings.
    focus_concepts_json = Column(Text, nullable=True, default="[]")

    student = relationship("Student", back_populates="sessions")
    exercises = relationship("ExerciseAttempt", back_populates="session")

    @property
    def exercises_list(self) -> list:
        if not self.exercises_json:
            return []
        try:
            return json.loads(self.exercises_json)
        except (json.JSONDecodeError, TypeError):
            return []

    @exercises_list.setter
    def exercises_list(self, value: list):
        self.exercises_json = json.dumps(value or [])

    @property
    def focus_concepts(self) -> list:
        if not self.focus_concepts_json:
            return []
        try:
            return json.loads(self.focus_concepts_json)
        except (json.JSONDecodeError, TypeError):
            return []

    @focus_concepts.setter
    def focus_concepts(self, value: list):
        self.focus_concepts_json = json.dumps(value or [])


class ExerciseAttempt(Base):
    __tablename__ = "exercise_attempts"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("learning_sessions.id"), nullable=False)
    question = Column(Text, nullable=False)
    student_answer = Column(Text, nullable=True)
    result = Column(String, nullable=True)  # "correct" | "partial" | "incorrect"
    feedback = Column(Text, nullable=True)
    skill_tested = Column(String, nullable=True)
    attempted_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("LearningSession", back_populates="exercises")


class ChatMessage(Base):
    """
    Q&A turns between the student and the in-lesson chatbot.
    One row per turn (user OR assistant). Bound to a LearningSession so the
    history persists across logout/reload alongside the lesson itself.
    """
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("learning_sessions.id"), nullable=False, index=True)
    role = Column(String, nullable=False)             # "user" | "assistant"
    content = Column(Text, nullable=False)
    # Which tab the student was on when they sent this:
    #   "lesson"   — chatbot answers from the lesson content
    #   "practice" — Socratic mode; gives hints, never reveals sample_answer
    mode = Column(String, nullable=False, default="lesson")
    # For practice mode: the exercise the student was looking at. Lets us
    # show the bot the right exercise on follow-up turns even if the student
    # navigates away.
    exercise_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


# ────────────────────────────────────────────────────────────────
# Lightweight in-place migration
# ────────────────────────────────────────────────────────────────
# SQLAlchemy's create_all() only creates *missing tables*; it does NOT add
# columns to tables that already exist. For a SQLite-backed local app we
# don't want to introduce Alembic just for a few additions, so we inspect
# each table and run a plain ALTER TABLE for any column the live schema
# is missing. Safe to call repeatedly — existing data is preserved.

_EXPECTED_COLUMNS: dict[str, dict[str, str]] = {
    "learning_sessions": {
        "lesson_text": "TEXT",
        "exercises_json": "TEXT DEFAULT '[]'",
        "current_exercise_index": "INTEGER DEFAULT 0",
        "completed": "BOOLEAN DEFAULT 0",
        "remediation_round": "INTEGER DEFAULT 0",
        "focus_concepts_json": "TEXT DEFAULT '[]'",
    },
}


def _migrate_add_missing_columns() -> None:
    """Add any expected columns that don't exist yet on existing tables."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table_name, expected in _EXPECTED_COLUMNS.items():
            if table_name not in existing_tables:
                # Table will be created from scratch by create_all() — nothing to migrate.
                continue
            existing_cols = {col["name"] for col in inspector.get_columns(table_name)}
            for col_name, col_def in expected.items():
                if col_name not in existing_cols:
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}"))
                    print(f"[migration] added {table_name}.{col_name}")


def init_db():
    """Create all tables, then run additive column migrations. Safe to call repeatedly."""
    os.makedirs("data/student_data", exist_ok=True)
    Base.metadata.create_all(bind=engine)
    _migrate_add_missing_columns()
    print("Database initialized.")


def get_db():
    """FastAPI dependency: yields a DB session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
