"""
FastAPI Backend
---------------
REST API endpoints for the learning agent.
Run with: uvicorn backend.api.main:app --reload
"""

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import desc
from pydantic import BaseModel
from datetime import datetime

from backend.db.models import (
    get_db, init_db, Student, Curriculum, Enrollment,
    LearningSession, ExerciseAttempt, ChatMessage
)
from backend.agents import curriculum_agent, assessment_agent, tutor_agent

app = FastAPI(title="Learning Agent API", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


# ─────────────────────────────────────────
# Pydantic request/response models
# ─────────────────────────────────────────

class StudentCreate(BaseModel):
    name: str
    email: str

class CurriculumCreate(BaseModel):
    job_description: str

class EnrollRequest(BaseModel):
    student_id: int
    curriculum_id: int

class DiagnosticAnswers(BaseModel):
    enrollment_id: int
    answers: list[dict]  # [{"question_id": "q1", "answer": "..."}]

class ExerciseAnswerRequest(BaseModel):
    session_id: int
    exercise_id: str
    question: str
    sample_answer: str
    skill_tested: str
    student_answer: str


class ChatRequest(BaseModel):
    message: str
    mode: str = "lesson"           # "lesson" or "practice"
    exercise_id: str | None = None # which exercise the student was looking at (practice mode)


# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────

def _serialize_session(session: LearningSession, module: dict, db: Session | None = None) -> dict:
    """Convert a LearningSession to the JSON shape the frontend expects.

    When `db` is passed we also embed the chat history so the frontend doesn't
    need a second round-trip on session load / resume.
    """
    chat_messages: list[dict] = []
    if db is not None:
        rows = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
            .all()
        )
        chat_messages = [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "mode": m.mode,
                "exercise_id": m.exercise_id,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in rows
        ]

    return {
        "session_id": session.id,
        "module": module,
        "module_index": session.module_index,
        "lesson": session.lesson_text or "",
        "exercises": session.exercises_list,
        "current_exercise_index": session.current_exercise_index or 0,
        "remediation_round": session.remediation_round or 0,
        "focus_concepts": session.focus_concepts,
        "chat_messages": chat_messages,
        "is_resumed": True,
    }


# ─────────────────────────────────────────
# Students
# ─────────────────────────────────────────

@app.post("/students")
def create_or_get_student(data: StudentCreate, db: Session = Depends(get_db)):
    """Create or return an existing student by email. Idempotent sign-in/register."""
    existing = db.query(Student).filter(Student.email == data.email).first()
    if existing:
        return {"id": existing.id, "name": existing.name, "email": existing.email}
    student = Student(name=data.name, email=data.email)
    db.add(student)
    db.commit()
    db.refresh(student)
    return {"id": student.id, "name": student.name, "email": student.email}


@app.get("/students/{student_id}")
def get_student(student_id: int, db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(404, "Student not found")
    return {
        "id": student.id,
        "name": student.name,
        "email": student.email,
        "enrollments": [
            {
                "id": e.id,
                "curriculum_id": e.curriculum_id,
                "job_title": e.curriculum.job_title,
                "job_readiness_score": e.job_readiness_score,
                "current_module": e.current_module_index,
                "enrolled_at": e.enrolled_at.isoformat() if e.enrolled_at else None,
                "last_active_at": e.last_active_at.isoformat() if e.last_active_at else None,
            }
            for e in student.enrollments
        ]
    }


# ─────────────────────────────────────────
# Curriculum
# ─────────────────────────────────────────

@app.post("/curricula")
def create_curriculum(data: CurriculumCreate, db: Session = Depends(get_db)):
    """Parse a job description and generate a curriculum."""
    result = curriculum_agent.generate_curriculum(data.job_description)

    curriculum = Curriculum(
        job_title=result["job_title"],
        job_description=data.job_description,
    )
    curriculum.modules = result["modules"]
    curriculum.required_skills = result["required_skills"]

    db.add(curriculum)
    db.commit()
    db.refresh(curriculum)

    return {
        "id": curriculum.id,
        "job_title": curriculum.job_title,
        "modules": curriculum.modules,
        "required_skills": curriculum.required_skills,
        "summary": curriculum_agent.explain_curriculum(result),
    }


@app.get("/curricula/{curriculum_id}")
def get_curriculum(curriculum_id: int, db: Session = Depends(get_db)):
    c = db.query(Curriculum).filter(Curriculum.id == curriculum_id).first()
    if not c:
        raise HTTPException(404, "Curriculum not found")
    return {
        "id": c.id,
        "job_title": c.job_title,
        "modules": c.modules,
        "required_skills": c.required_skills,
    }


# ─────────────────────────────────────────
# Enrollment + Assessment
# ─────────────────────────────────────────

@app.post("/enroll")
def enroll_student(data: EnrollRequest, db: Session = Depends(get_db)):
    """Enroll a student in a curriculum and generate a diagnostic quiz."""
    student = db.query(Student).filter(Student.id == data.student_id).first()
    curriculum = db.query(Curriculum).filter(Curriculum.id == data.curriculum_id).first()

    if not student or not curriculum:
        raise HTTPException(404, "Student or curriculum not found")

    enrollment = Enrollment(
        student_id=student.id,
        curriculum_id=curriculum.id,
    )
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)

    curriculum_dict = {
        "job_title": curriculum.job_title,
        "required_skills": curriculum.required_skills,
        "modules": curriculum.modules,
    }
    diagnostic = assessment_agent.generate_diagnostic(curriculum_dict, num_questions=5)

    return {
        "enrollment_id": enrollment.id,
        "message": "Welcome! Let's assess your current knowledge before we begin.",
        "diagnostic_questions": diagnostic["questions"],
    }


@app.post("/diagnostic/submit")
def submit_diagnostic(data: DiagnosticAnswers, db: Session = Depends(get_db)):
    """Score diagnostic answers and set the student's starting point."""
    enrollment = db.query(Enrollment).filter(Enrollment.id == data.enrollment_id).first()
    if not enrollment:
        raise HTTPException(404, "Enrollment not found")

    curriculum = enrollment.curriculum
    curriculum_dict = {
        "job_title": curriculum.job_title,
        "required_skills": curriculum.required_skills,
        "modules": curriculum.modules,
    }

    diagnostic = assessment_agent.generate_diagnostic(curriculum_dict, num_questions=5)
    questions = diagnostic["questions"]

    assessment = assessment_agent.evaluate_diagnostic(questions, data.answers)

    start_module = assessment_agent.determine_start_module(assessment, curriculum_dict)
    enrollment.current_module_index = start_module

    initial_scores = {}
    for result in assessment.get("results", []):
        skill = result.get("skill_tested")
        if skill:
            initial_scores[skill] = result.get("score", 0)
    enrollment.mastery_scores = initial_scores
    enrollment.job_readiness_score = enrollment.compute_job_readiness()

    db.commit()

    return {
        "assessment": assessment["overall_assessment"],
        "starting_module": start_module,
        "starting_topic": curriculum.modules[start_module]["topic"] if curriculum.modules else "N/A",
        "job_readiness_score": enrollment.job_readiness_score,
    }


# ─────────────────────────────────────────
# Learning sessions
# ─────────────────────────────────────────

@app.post("/sessions/start")
def start_session(enrollment_id: int, db: Session = Depends(get_db)):
    """
    Start (or resume) a learning session for the student's current module.

    If an in-progress (not completed) session already exists for the current
    module, we return its stored lesson + exercises — this is what fixes the
    "lessons disappear after logout" bug.
    """
    enrollment = db.query(Enrollment).filter(Enrollment.id == enrollment_id).first()
    if not enrollment:
        raise HTTPException(404, "Enrollment not found")

    curriculum = enrollment.curriculum
    modules = curriculum.modules
    module_index = enrollment.current_module_index

    if module_index >= len(modules):
        return {"status": "complete", "message": "You have completed all modules! 🎉"}

    module = modules[module_index]

    # ── Try to resume an open session for this module ───────────────────
    open_session = (
        db.query(LearningSession)
        .filter(
            LearningSession.enrollment_id == enrollment.id,
            LearningSession.module_index == module_index,
            LearningSession.completed.is_(False),
        )
        .order_by(desc(LearningSession.started_at))
        .first()
    )
    if open_session and open_session.lesson_text and open_session.exercises_list:
        return _serialize_session(open_session, module, db)

    # ── Otherwise, generate fresh content and persist it ───────────────
    # IMPORTANT: we generate exercises FIRST so the deep-lesson pipeline can
    # plan its outline backwards from the exercises the student will face —
    # that's what guarantees the lesson teaches everything needed to solve them.
    mastery = enrollment.mastery_scores.get(module["topic"], 0)

    exercises_data = tutor_agent.generate_exercises(
        module=module,
        job_title=curriculum.job_title,
        mastery_score=mastery,
        num_exercises=3,
    )
    exercises_list = exercises_data["exercises"]

    lesson = tutor_agent.generate_deep_lesson(
        module=module,
        exercises=exercises_list,
        job_title=curriculum.job_title,
        mastery_score=mastery,
    )

    session = LearningSession(
        student_id=enrollment.student_id,
        enrollment_id=enrollment.id,
        topic=module["topic"],
        module_index=module_index,
        lesson_text=lesson,
        current_exercise_index=0,
        completed=False,
        remediation_round=0,
    )
    session.exercises_list = exercises_list
    session.focus_concepts = []
    db.add(session)
    db.commit()
    db.refresh(session)

    return {
        "session_id": session.id,
        "module": module,
        "module_index": module_index,
        "lesson": lesson,
        "exercises": session.exercises_list,
        "current_exercise_index": 0,
        "remediation_round": 0,
        "focus_concepts": [],
        "chat_messages": [],   # brand-new session, no chat yet
        "mastery_before": mastery,
        "is_resumed": False,
    }


@app.post("/sessions/answer")
def submit_answer(data: ExerciseAnswerRequest, db: Session = Depends(get_db)):
    """Submit an answer to an exercise and get feedback."""
    session = db.query(LearningSession).filter(LearningSession.id == data.session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")

    enrollment = db.query(Enrollment).filter(Enrollment.id == session.enrollment_id).first()
    curriculum = enrollment.curriculum

    exercise = {
        "id": data.exercise_id,
        "question": data.question,
        "sample_answer": data.sample_answer,
        "skill_tested": data.skill_tested,
    }

    evaluation = tutor_agent.evaluate_answer(
        exercise=exercise,
        student_answer=data.student_answer,
        job_title=curriculum.job_title,
    )

    # Record the attempt (stash the LLM-identified missed_concept inside feedback
    # so we can recover it later when building remediation).
    attempt = ExerciseAttempt(
        session_id=session.id,
        question=data.question,
        student_answer=data.student_answer,
        result=evaluation["result"],
        feedback=evaluation.get("feedback", ""),
        skill_tested=data.skill_tested,
    )
    db.add(attempt)

    session.exercises_attempted = (session.exercises_attempted or 0) + 1
    if evaluation["result"] == "correct":
        session.exercises_correct = (session.exercises_correct or 0) + 1

    # Advance the persisted cursor so a logout/reload picks up where they left off.
    session.current_exercise_index = (session.current_exercise_index or 0) + 1

    enrollment.update_mastery(data.skill_tested, evaluation["result"])
    enrollment.job_readiness_score = enrollment.compute_job_readiness()
    enrollment.last_active_at = datetime.utcnow()
    db.commit()

    return {
        "result": evaluation["result"],
        "score": evaluation["score"],
        "feedback": evaluation["feedback"],
        "what_was_good": evaluation.get("what_was_good"),
        "what_to_improve": evaluation.get("what_to_improve"),
        "follow_up_tip": evaluation.get("follow_up_tip"),
        "missed_concept": evaluation.get("missed_concept", ""),
        "new_mastery_score": enrollment.mastery_scores.get(data.skill_tested, 0),
        "job_readiness_score": enrollment.job_readiness_score,
        "current_exercise_index": session.current_exercise_index,
    }


@app.post("/sessions/complete")
def complete_session(session_id: int, db: Session = Depends(get_db)):
    """
    End a session and decide whether to:
      • advance to the next module, or
      • run a targeted remediation pass on the same module.

    When remediation is needed, we create a NEW LearningSession for the same
    module with a fresh deep-dive lesson + new exercises focused on the
    concepts the student got wrong. The frontend can then call
    /sessions/start (or /sessions/{id}) to pick it up.
    """
    session = db.query(LearningSession).filter(LearningSession.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")

    session.ended_at = datetime.utcnow()
    session.completed = True
    enrollment = db.query(Enrollment).filter(Enrollment.id == session.enrollment_id).first()
    curriculum = enrollment.curriculum

    attempts = db.query(ExerciseAttempt).filter(ExerciseAttempt.session_id == session_id).all()
    results = [a.result for a in attempts if a.result]

    module = curriculum.modules[session.module_index]
    mastery = enrollment.mastery_scores.get(module["topic"], 0)

    advance, reason = tutor_agent.should_advance(
        mastery_score=mastery,
        session_results=results,
        remediation_round=session.remediation_round or 0,
    )

    remediation_session_id = None
    next_module = None

    if advance:
        enrollment.current_module_index += 1
        if enrollment.current_module_index < len(curriculum.modules):
            next_module = curriculum.modules[enrollment.current_module_index]["topic"]
    else:
        # ── Spin up a remediation session ──────────────────────────────
        # We need rich attempt data (including the LLM's missed_concept) to
        # focus the next lesson. We re-evaluate from the attempt rows.
        attempt_dicts = []
        for a in attempts:
            attempt_dicts.append({
                "result": a.result,
                "skill_tested": a.skill_tested,
                "feedback": a.feedback,
                # Earlier feedback didn't include missed_concept — fall back to skill.
                "missed_concept": a.skill_tested or "",
            })
        focus_concepts, mistakes = tutor_agent.extract_focus_concepts(attempt_dicts)

        new_round = (session.remediation_round or 0) + 1

        # Same ordering as /sessions/start: exercises first, then deep lesson
        # planned backwards from them. For remediation, both are biased toward
        # the concepts the student got wrong.
        remediation_exercises = tutor_agent.generate_exercises(
            module=module,
            job_title=curriculum.job_title,
            mastery_score=mastery,
            num_exercises=3,
            focus_concepts=focus_concepts,
        )
        remediation_exercises_list = remediation_exercises["exercises"]

        remediation_lesson = tutor_agent.generate_deep_lesson(
            module=module,
            exercises=remediation_exercises_list,
            job_title=curriculum.job_title,
            mastery_score=mastery,
            remediation=True,
            focus_concepts=focus_concepts,
            recent_mistakes=mistakes,
            round_number=new_round,
        )

        rem = LearningSession(
            student_id=enrollment.student_id,
            enrollment_id=enrollment.id,
            topic=module["topic"],
            module_index=session.module_index,
            lesson_text=remediation_lesson,
            current_exercise_index=0,
            completed=False,
            remediation_round=new_round,
        )
        rem.exercises_list = remediation_exercises_list
        rem.focus_concepts = focus_concepts
        db.add(rem)
        db.commit()
        db.refresh(rem)
        remediation_session_id = rem.id

    db.commit()

    return {
        "advance": advance,
        "reason": reason,
        "mastery_score": mastery,
        "job_readiness_score": enrollment.job_readiness_score,
        "next_module": next_module,
        "course_complete": enrollment.current_module_index >= len(curriculum.modules),
        "remediation_session_id": remediation_session_id,
        "remediation_round": (session.remediation_round or 0) + (0 if advance else 1),
        "focus_concepts": session.focus_concepts if advance else (
            tutor_agent.extract_focus_concepts([{
                "result": a.result, "skill_tested": a.skill_tested,
                "feedback": a.feedback, "missed_concept": a.skill_tested or "",
            } for a in attempts])[0]
        ),
    }


@app.get("/sessions/{session_id}")
def get_session(session_id: int, db: Session = Depends(get_db)):
    """Fetch a stored session (for resuming after logout/reload)."""
    session = db.query(LearningSession).filter(LearningSession.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    enrollment = db.query(Enrollment).filter(Enrollment.id == session.enrollment_id).first()
    module = enrollment.curriculum.modules[session.module_index]
    return _serialize_session(session, module, db)


# ─────────────────────────────────────────
# In-lesson chatbot
# ─────────────────────────────────────────

@app.post("/sessions/{session_id}/chat")
def chat_in_session(session_id: int, data: ChatRequest, db: Session = Depends(get_db)):
    """
    Send a message to the in-lesson chatbot for this session.

    The user turn and assistant reply are both persisted as ChatMessage rows
    so the conversation survives logout/reload. On the practice tab the bot
    runs in Socratic mode and is forbidden from revealing the exercise's
    sample answer (the system prompt enforces this).
    """
    session = db.query(LearningSession).filter(LearningSession.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    if not (data.message or "").strip():
        raise HTTPException(400, "Empty message.")

    mode = data.mode if data.mode in ("lesson", "practice") else "lesson"

    enrollment = db.query(Enrollment).filter(Enrollment.id == session.enrollment_id).first()
    curriculum = enrollment.curriculum
    module = curriculum.modules[session.module_index]

    # Pull the conversation history for THIS mode only. That keeps the two
    # threads (reading vs. practicing) from leaking into each other.
    history_rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session.id, ChatMessage.mode == mode)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        .all()
    )
    history = [{"role": m.role, "content": m.content} for m in history_rows]

    # For practice mode, look up the current exercise (server-side, so the
    # frontend can't trick the bot into seeing a different exercise's answer).
    current_exercise: dict | None = None
    if mode == "practice":
        exercises = session.exercises_list or []
        # Prefer the exercise the frontend named; fall back to the persisted cursor.
        if data.exercise_id:
            current_exercise = next(
                (e for e in exercises if e.get("id") == data.exercise_id), None
            )
        if current_exercise is None:
            idx = session.current_exercise_index or 0
            if 0 <= idx < len(exercises):
                current_exercise = exercises[idx]

    # Persist the student's turn before calling the LLM. That way if the LLM
    # call fails, we don't lose what they typed.
    user_row = ChatMessage(
        session_id=session.id,
        role="user",
        content=data.message.strip(),
        mode=mode,
        exercise_id=(current_exercise or {}).get("id") if mode == "practice" else None,
    )
    db.add(user_row)
    db.commit()
    db.refresh(user_row)

    try:
        reply = tutor_agent.chat_with_student(
            student_message=data.message.strip(),
            history=history,
            lesson_text=session.lesson_text or "",
            module=module,
            job_title=curriculum.job_title,
            mode=mode,
            current_exercise=current_exercise,
        )
    except Exception as exc:
        # Don't lose the user's message — surface a graceful assistant turn.
        reply = (
            "Sorry — I hit an error answering that question. "
            f"Please try rephrasing, or check the backend logs. ({type(exc).__name__})"
        )

    assistant_row = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=reply,
        mode=mode,
        exercise_id=(current_exercise or {}).get("id") if mode == "practice" else None,
    )
    db.add(assistant_row)
    db.commit()
    db.refresh(assistant_row)

    return {
        "user_message": {
            "id": user_row.id,
            "role": "user",
            "content": user_row.content,
            "mode": user_row.mode,
            "exercise_id": user_row.exercise_id,
            "created_at": user_row.created_at.isoformat() if user_row.created_at else None,
        },
        "assistant_message": {
            "id": assistant_row.id,
            "role": "assistant",
            "content": assistant_row.content,
            "mode": assistant_row.mode,
            "exercise_id": assistant_row.exercise_id,
            "created_at": assistant_row.created_at.isoformat() if assistant_row.created_at else None,
        },
    }


@app.get("/sessions/{session_id}/chat")
def get_chat_history(session_id: int, db: Session = Depends(get_db)):
    """Return the full chat history for a session (both modes, in order)."""
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        .all()
    )
    return {
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "mode": m.mode,
                "exercise_id": m.exercise_id,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in rows
        ]
    }


# ─────────────────────────────────────────
# Progress
# ─────────────────────────────────────────

@app.get("/progress/{enrollment_id}")
def get_progress(enrollment_id: int, db: Session = Depends(get_db)):
    """Get full progress report for an enrollment."""
    enrollment = db.query(Enrollment).filter(Enrollment.id == enrollment_id).first()
    if not enrollment:
        raise HTTPException(404, "Enrollment not found")

    curriculum = enrollment.curriculum
    modules = curriculum.modules
    mastery = enrollment.mastery_scores

    module_progress = []
    for i, module in enumerate(modules):
        status = (
            "complete" if i < enrollment.current_module_index else
            "current" if i == enrollment.current_module_index else
            "locked"
        )
        module_progress.append({
            "index": i,
            "topic": module["topic"],
            "status": status,
            "mastery": mastery.get(module["topic"], 0),
            "difficulty": module.get("difficulty"),
        })

    return {
        "student": enrollment.student.name,
        "job_title": curriculum.job_title,
        "job_readiness_score": enrollment.job_readiness_score,
        "modules": module_progress,
        "mastery_by_skill": mastery,
        "required_skills": curriculum.required_skills,
    }
