"""
Learning Agent - Streamlit Frontend
------------------------------------
Run with: streamlit run frontend/app.py
Make sure the FastAPI backend is running: uvicorn backend.api.main:app --reload
"""

import streamlit as st
import httpx

API_BASE = "http://localhost:8000"

st.set_page_config(
    page_title="AI Learning Agent",
    page_icon="🎓",
    layout="wide",
)

# ─────────────────────────────────────────
# Session state initialization
# ─────────────────────────────────────────
DEFAULTS = {
    "student_id": None,
    "enrollment_id": None,
    "session_id": None,
    "page": "home",
    "diagnostic_questions": [],
    "diagnostic_answers": {},
    "diagnostic_result": None,
    "current_exercises": [],
    "current_lesson": "",
    "current_module": None,
    "exercise_index": 0,
    "remediation_round": 0,
    "focus_concepts": [],
    "session_results": [],
    "last_feedback": None,        # persisted feedback panel between reruns
    "completion_summary": None,   # set when /sessions/complete returns
    "chat_messages": [],          # all chat turns for the current session
}
for key, default in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default


def api(method: str, path: str, **kwargs):
    """Simple API helper."""
    try:
        response = httpx.request(method, f"{API_BASE}{path}", timeout=120, **kwargs)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        st.error(f"API error: {e.response.text}")
        return None
    except httpx.ConnectError:
        st.error("⚠️ Cannot reach the backend. Is it running? → `uvicorn backend.api.main:app --reload`")
        return None


def reset_session_state(keep_login: bool = False):
    """Wipe session-specific state. Optionally keep the logged-in student."""
    keep = {}
    if keep_login:
        keep = {
            "student_id": st.session_state.get("student_id"),
            "enrollment_id": st.session_state.get("enrollment_id"),
        }
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    for key, default in DEFAULTS.items():
        st.session_state[key] = default
    for k, v in keep.items():
        st.session_state[k] = v


def load_session_into_state(session_data: dict):
    """Pull a /sessions/start (or resume) response into session_state."""
    st.session_state.session_id = session_data["session_id"]
    st.session_state.current_module = session_data["module"]
    st.session_state.current_lesson = session_data["lesson"]
    st.session_state.current_exercises = session_data["exercises"]
    st.session_state.exercise_index = session_data.get("current_exercise_index", 0)
    st.session_state.remediation_round = session_data.get("remediation_round", 0)
    st.session_state.focus_concepts = session_data.get("focus_concepts", [])
    st.session_state.session_results = []
    st.session_state.last_feedback = None
    st.session_state.completion_summary = None
    st.session_state.chat_messages = session_data.get("chat_messages", []) or []


def render_chat_panel(mode: str, *, exercise_id: str | None = None):
    """
    Render the in-lesson chatbot panel for the given mode.
    mode: "lesson"   — answers from the lesson content
          "practice" — Socratic mode, won't reveal exercise answers
    """
    label = "💬 Ask a question about this lesson" if mode == "lesson" else "💬 Get a hint from your tutor"
    blurb = (
        "Anything unclear? Ask away — answers are grounded in this lesson."
        if mode == "lesson"
        else "Stuck? I'll give you hints and ask leading questions, but I won't reveal the answer."
    )

    # Filter persisted messages by mode so the two threads stay separate.
    msgs = [m for m in (st.session_state.chat_messages or []) if m.get("mode") == mode]

    with st.expander(label, expanded=False):
        st.caption(blurb)
        # Render the history.
        if msgs:
            for m in msgs:
                with st.chat_message("assistant" if m["role"] == "assistant" else "user"):
                    st.markdown(m["content"])
        else:
            st.markdown(
                "_No messages yet — type a question below._"
                if mode == "lesson"
                else "_Stuck on the current exercise? Ask for a hint._"
            )

        # Input form. We can't use st.chat_input inside an expander (Streamlit
        # pins it to the bottom of the page), so we use a form with a text
        # input + submit button. Form-scoped key uses session_id + mode so the
        # input clears between sessions/modes naturally.
        form_key = f"chat_form_{st.session_state.session_id}_{mode}"
        input_key = f"chat_input_{st.session_state.session_id}_{mode}"
        with st.form(form_key, clear_on_submit=True):
            user_msg = st.text_input(
                "Your question",
                key=input_key,
                placeholder=(
                    "e.g. Can you give me another example of X?"
                    if mode == "lesson"
                    else "e.g. I'm stuck — where in the lesson should I look?"
                ),
                label_visibility="collapsed",
            )
            sent = st.form_submit_button("Send", use_container_width=True)

        if sent and user_msg.strip():
            payload = {"message": user_msg.strip(), "mode": mode}
            if mode == "practice" and exercise_id:
                payload["exercise_id"] = exercise_id

            with st.spinner("Tutor is thinking..."):
                resp = api(
                    "POST",
                    f"/sessions/{st.session_state.session_id}/chat",
                    json=payload,
                )
            if resp:
                # Append both turns to session_state so they show on the next rerun.
                st.session_state.chat_messages = (
                    (st.session_state.chat_messages or [])
                    + [resp["user_message"], resp["assistant_message"]]
                )
                st.rerun()


# ─────────────────────────────────────────
# Sidebar - navigation & student info
# ─────────────────────────────────────────
with st.sidebar:
    st.title("🎓 AI Learning Agent")
    st.divider()

    if st.session_state.student_id:
        student = api("GET", f"/students/{st.session_state.student_id}")
        if student:
            st.success(f"👋 {student['name']}")
            for e in student.get("enrollments", []):
                st.metric(
                    label=f"📋 {e['job_title']}",
                    value=f"{e['job_readiness_score']:.0f}% ready",
                )

        if st.button("📖 Continue Learning", use_container_width=True, type="primary"):
            # Drop any in-memory session so we re-fetch from backend (which may
            # resume an existing one).
            st.session_state.session_id = None
            st.session_state.last_feedback = None
            st.session_state.completion_summary = None
            st.session_state.page = "learning"
            st.rerun()

        if st.button("📈 View Progress", use_container_width=True):
            st.session_state.page = "progress"
            st.rerun()

        if st.button("🏠 Home", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()

        st.divider()
        if st.button("← Log Out", use_container_width=True):
            reset_session_state(keep_login=False)
            st.rerun()
    else:
        st.info("Sign in or create an account to begin.")


# ─────────────────────────────────────────
# Page: Home / Login
# ─────────────────────────────────────────
if st.session_state.page == "home" and not st.session_state.student_id:
    st.title("Welcome to your AI Learning Agent")
    st.markdown(
        "Paste a job description, and this agent will build a personalized curriculum, "
        "assess your knowledge, and guide you step by step toward being job-ready."
    )
    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Sign In")
        email = st.text_input("Email", key="login_email")
        name = st.text_input("Name", key="login_name")
        if st.button("Sign In / Register", use_container_width=True, type="primary"):
            if email and name:
                result = api("POST", "/students", json={"name": name, "email": email})
                if result:
                    st.session_state.student_id = result["id"]

                    # Returning student? Resume their most-recent enrollment.
                    student = api("GET", f"/students/{result['id']}")
                    if student and student.get("enrollments"):
                        latest = sorted(
                            student["enrollments"],
                            key=lambda e: e.get("last_active_at") or "",
                            reverse=True,
                        )[0]
                        st.session_state.enrollment_id = latest["id"]
                        st.session_state.page = "learning"
                    else:
                        st.session_state.page = "enroll"
                    st.rerun()
            else:
                st.warning("Please enter your name and email.")

    with col2:
        st.subheader("How it works")
        st.markdown("""
        1. **Paste a job description** → AI extracts the skills you need
        2. **Take a quick diagnostic** → We find your knowledge gaps
        3. **Get a personalized curriculum** → Lessons tailored to your level
        4. **Practice with AI exercises** → Get instant, specific feedback
        5. **Stuck on something?** → The agent dives deeper and re-teaches with a fresh angle
        6. **Track your job-readiness** → See your progress toward the role
        """)


# ─────────────────────────────────────────
# Page: Home (signed-in landing)
# ─────────────────────────────────────────
elif st.session_state.page == "home" and st.session_state.student_id:
    st.title("Welcome back!")
    student = api("GET", f"/students/{st.session_state.student_id}")
    if student and student.get("enrollments"):
        st.markdown("Pick up where you left off, or start a new curriculum.")
        for e in student["enrollments"]:
            col_a, col_b = st.columns([3, 1])
            with col_a:
                st.markdown(f"**{e['job_title']}** — {e['job_readiness_score']:.0f}% ready")
            with col_b:
                if st.button("Resume", key=f"resume_{e['id']}"):
                    st.session_state.enrollment_id = e["id"]
                    st.session_state.session_id = None
                    st.session_state.page = "learning"
                    st.rerun()
        st.divider()
    if st.button("➕ Start a new curriculum"):
        st.session_state.page = "enroll"
        st.rerun()


# ─────────────────────────────────────────
# Page: Enroll (paste JD)
# ─────────────────────────────────────────
elif st.session_state.page == "enroll":
    st.title("📋 Set Your Target Role")
    st.markdown("Paste a job description below. The AI will extract the skills and build your curriculum.")

    jd = st.text_area(
        "Job Description",
        height=300,
        placeholder="Paste the full job description here...",
    )

    if st.button("Generate My Curriculum →", use_container_width=True, type="primary"):
        if not jd.strip():
            st.warning("Please paste a job description first.")
        else:
            with st.spinner("Analyzing job description and building your curriculum... (this may take 30-60 seconds)"):
                curriculum = api("POST", "/curricula", json={"job_description": jd})

            if curriculum:
                st.success(f"✅ Curriculum created for: **{curriculum['job_title']}**")
                st.markdown(curriculum.get("summary", ""))

                with st.expander("📚 View your learning modules"):
                    for m in curriculum["modules"]:
                        st.markdown(f"**{m['index']+1}. {m['topic']}** ({m['difficulty']}) — ~{m['estimated_hours']}h")
                        st.markdown(f"  {m['description']}")

                with st.spinner("Enrolling you and generating diagnostic quiz..."):
                    enrollment = api("POST", "/enroll", json={
                        "student_id": st.session_state.student_id,
                        "curriculum_id": curriculum["id"],
                    })

                if enrollment:
                    st.session_state.enrollment_id = enrollment["enrollment_id"]
                    st.session_state.diagnostic_questions = enrollment["diagnostic_questions"]
                    st.session_state.page = "diagnostic"
                    st.rerun()


# ─────────────────────────────────────────
# Page: Diagnostic Quiz
# ─────────────────────────────────────────
elif st.session_state.page == "diagnostic":
    st.title("🔍 Knowledge Assessment")
    st.markdown(
        "Answer these questions honestly — there are no wrong answers here. "
        "This helps us personalize your curriculum to your current level."
    )
    st.divider()

    questions = st.session_state.diagnostic_questions

    with st.form("diagnostic_form"):
        for q in questions:
            st.markdown(f"**{q['question']}**")
            st.caption(f"Skill: {q['skill_tested']} · {q['difficulty']}")
            st.text_area(
                label="Your answer",
                key=f"diag_{q['id']}",
                height=100,
                label_visibility="collapsed",
                placeholder="Type your answer here (or 'I don't know' if unsure)...",
            )
            st.divider()

        submitted = st.form_submit_button("Submit Assessment →", use_container_width=True, type="primary")

    if submitted:
        answers = [
            {"question_id": q["id"], "answer": st.session_state.get(f"diag_{q['id']}", "")}
            for q in questions
        ]

        with st.spinner("Evaluating your answers..."):
            result = api("POST", "/diagnostic/submit", json={
                "enrollment_id": st.session_state.enrollment_id,
                "answers": answers,
            })

        if result:
            st.session_state.diagnostic_result = result
            st.session_state.page = "diagnostic_results"
            st.rerun()


# ─────────────────────────────────────────
# Page: Diagnostic Results
# ─────────────────────────────────────────
elif st.session_state.page == "diagnostic_results":
    result = st.session_state.get("diagnostic_result", {}) or {}
    assessment = result.get("assessment", {})

    st.title("📊 Your Assessment Results")

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Job Readiness", f"{result.get('job_readiness_score', 0):.0f}%")
    with col2:
        st.metric(
            "Starting Module",
            f"#{result.get('starting_module', 0) + 1}: {result.get('starting_topic', '')}",
        )

    st.markdown(f"### Summary\n{assessment.get('summary', '')}")

    col3, col4 = st.columns(2)
    with col3:
        st.markdown("**✅ Your strengths**")
        for s in assessment.get("strengths", []):
            st.markdown(f"- {s}")
    with col4:
        st.markdown("**📌 Areas to develop**")
        for g in assessment.get("gaps", []):
            st.markdown(f"- {g}")

    if st.button("Start Learning →", use_container_width=True, type="primary"):
        st.session_state.page = "learning"
        st.rerun()


# ─────────────────────────────────────────
# Page: Learning (lesson + exercises)
# ─────────────────────────────────────────
elif st.session_state.page == "learning":
    if not st.session_state.enrollment_id:
        st.warning("Please enroll in a curriculum first.")
        if st.button("Go to enrollment"):
            st.session_state.page = "enroll"
            st.rerun()
        st.stop()

    if not st.session_state.session_id:
        with st.spinner(
            "Building your ground-up lesson — generating practice exercises, "
            "planning a chapter-style outline, writing each section, and "
            "auditing coverage. This usually takes 1-3 minutes; on a local "
            "Ollama setup it can take longer."
        ):
            session_data = api(
                "POST", f"/sessions/start?enrollment_id={st.session_state.enrollment_id}"
            )

        if session_data is None:
            st.stop()

        if session_data.get("status") == "complete":
            st.balloons()
            st.title("🎉 Curriculum Complete!")
            st.success("You've completed all modules. You're ready for the job!")
            if st.button("← Back to Home"):
                st.session_state.page = "home"
                st.rerun()
            st.stop()

        load_session_into_state(session_data)
        if session_data.get("is_resumed"):
            st.info("📂 Picking up where you left off.")

    module = st.session_state.current_module
    exercises = st.session_state.current_exercises
    ex_idx = st.session_state.exercise_index
    rem_round = st.session_state.remediation_round or 0
    focus = st.session_state.focus_concepts or []

    # Banner: remediation context
    if rem_round > 0:
        st.warning(
            f"🔁 **Deep-dive round {rem_round}** on **{module['topic']}** — focusing on: "
            + (", ".join(focus) if focus else "the areas that gave you trouble")
        )

    # Show completion summary (set when /sessions/complete fired)
    if st.session_state.completion_summary:
        summary = st.session_state.completion_summary
        st.divider()
        if summary.get("advance"):
            st.success(f"🚀 {summary['reason']}")
            if summary.get("next_module"):
                st.info(f"Next up: **{summary['next_module']}**")
            if summary.get("course_complete"):
                st.balloons()
                st.success("🎉 You've completed the entire curriculum!")
            if st.button("Continue →", use_container_width=True, type="primary", key="continue_btn"):
                st.session_state.session_id = None
                st.session_state.completion_summary = None
                st.rerun()
        else:
            st.warning(f"🔄 {summary['reason']}")
            if summary.get("focus_concepts"):
                st.markdown(
                    "**The agent will now teach these in more depth:** "
                    + ", ".join(summary["focus_concepts"])
                )
            if summary.get("remediation_session_id"):
                if st.button(
                    "📖 Start deeper lesson →",
                    use_container_width=True,
                    type="primary",
                    key="start_remediation",
                ):
                    with st.spinner(
                        "Loading your deeper lesson... (the backend already built "
                        "it when you finished the previous round)"
                    ):
                        rem_session = api(
                            "GET", f"/sessions/{summary['remediation_session_id']}"
                        )
                    if rem_session:
                        load_session_into_state(rem_session)
                        st.rerun()
        st.stop()

    tab_lesson, tab_exercise = st.tabs(["📖 Lesson", "✏️ Practice"])

    with tab_lesson:
        st.markdown(f"## {module['topic']}")
        st.caption(
            f"Difficulty: {module.get('difficulty', 'intermediate')} · "
            f"Est. {module.get('estimated_hours', '?')}h"
            + (f" · Deep-dive round {rem_round}" if rem_round else "")
        )
        st.markdown(st.session_state.current_lesson)
        st.info("👉 When you're ready, click the **✏️ Practice** tab above to start exercises.")

        # In-lesson chatbot (lesson mode — answers grounded in the lesson content).
        render_chat_panel("lesson")

    with tab_exercise:
        if ex_idx < len(exercises):
            exercise = exercises[ex_idx]
            st.markdown(f"**Exercise {ex_idx + 1} of {len(exercises)}**")
            st.progress(ex_idx / len(exercises))
            st.divider()

            st.markdown(f"### {exercise['question']}")
            st.caption(f"Type: {exercise.get('type', 'open')} · Skill: {exercise.get('skill_tested', '')}")

            # NOTE: Hint toggle MUST live outside the form, otherwise Streamlit
            # only updates checkbox state on form submit (which feels broken).
            hint_key = f"show_hint_{st.session_state.session_id}_{ex_idx}"
            if exercise.get("hint"):
                show_hint = st.checkbox("💡 Show hint", key=hint_key)
                if show_hint:
                    st.info(exercise["hint"])

            # Only show the answer form if we don't have feedback waiting.
            if not st.session_state.last_feedback:
                with st.form(f"exercise_form_{st.session_state.session_id}_{ex_idx}"):
                    answer = st.text_area(
                        "Your answer",
                        height=150,
                        placeholder="Type your answer here...",
                        key=f"ans_{st.session_state.session_id}_{ex_idx}",
                    )
                    submitted = st.form_submit_button(
                        "Submit Answer →", type="primary", use_container_width=True
                    )

                if submitted and answer.strip():
                    with st.spinner("Evaluating your answer..."):
                        feedback = api("POST", "/sessions/answer", json={
                            "session_id": st.session_state.session_id,
                            "exercise_id": exercise["id"],
                            "question": exercise["question"],
                            "sample_answer": exercise.get("sample_answer", ""),
                            "skill_tested": exercise.get("skill_tested", ""),
                            "student_answer": answer,
                        })

                    if feedback:
                        st.session_state.last_feedback = feedback
                        st.session_state.session_results.append(feedback["result"])
                        st.rerun()
                elif submitted:
                    st.warning("Please write an answer before submitting.")
            else:
                # Render the persisted feedback panel + next button.
                feedback = st.session_state.last_feedback
                result_color = {"correct": "success", "partial": "warning", "incorrect": "error"}
                result_emoji = {"correct": "✅", "partial": "🟡", "incorrect": "❌"}
                r = feedback["result"]

                getattr(st, result_color.get(r, "info"))(
                    f"{result_emoji.get(r, '')} **{r.title()}** — Score: {feedback['score']}/100"
                )
                st.markdown(f"**Feedback:** {feedback['feedback']}")
                if feedback.get("what_was_good"):
                    st.markdown(f"👍 {feedback['what_was_good']}")
                if feedback.get("what_to_improve"):
                    st.markdown(f"🔧 **To improve:** {feedback['what_to_improve']}")
                if feedback.get("follow_up_tip"):
                    st.markdown(f"💡 **Tip:** {feedback['follow_up_tip']}")
                st.metric("Mastery score", f"{feedback['new_mastery_score']:.0f}/100")

                is_last = ex_idx + 1 >= len(exercises)
                next_label = "Finish session →" if is_last else "Next exercise →"
                if st.button(next_label, use_container_width=True, type="primary", key="next_btn"):
                    st.session_state.last_feedback = None
                    st.session_state.exercise_index += 1

                    if st.session_state.exercise_index >= len(exercises):
                        with st.spinner(
                            "Scoring your session. If you need a deeper round, "
                            "I'll build a fresh chapter-style lesson focused on "
                            "what tripped you up — this can take a couple minutes."
                        ):
                            completion = api(
                                "POST",
                                f"/sessions/complete?session_id={st.session_state.session_id}",
                            )
                        if completion:
                            st.session_state.completion_summary = completion
                    st.rerun()
        else:
            st.info("All exercises answered. Click below to wrap up.")
            if st.button("Wrap up session", type="primary", use_container_width=True):
                with st.spinner("Wrapping up..."):
                    completion = api(
                        "POST",
                        f"/sessions/complete?session_id={st.session_state.session_id}",
                    )
                if completion:
                    st.session_state.completion_summary = completion
                    st.rerun()

        # Socratic chatbot — gives hints on the current exercise without
        # revealing the sample answer. Skipped if we're past the last exercise.
        if ex_idx < len(exercises):
            render_chat_panel(
                "practice",
                exercise_id=exercises[ex_idx].get("id"),
            )


# ─────────────────────────────────────────
# Page: Progress Dashboard
# ─────────────────────────────────────────
elif st.session_state.page == "progress":
    st.title("📈 Your Progress")

    if not st.session_state.enrollment_id:
        st.warning("You haven't enrolled in a curriculum yet.")
    else:
        progress = api("GET", f"/progress/{st.session_state.enrollment_id}")
        if progress:
            st.markdown(f"### {progress['job_title']}")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Job Readiness", f"{progress['job_readiness_score']:.0f}%")
            with col2:
                completed = sum(1 for m in progress["modules"] if m["status"] == "complete")
                st.metric("Modules Completed", f"{completed}/{len(progress['modules'])}")

            st.divider()
            st.markdown("### Module Progress")
            for m in progress["modules"]:
                status_icon = {"complete": "✅", "current": "📍", "locked": "🔒"}.get(m["status"], "")
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.markdown(f"{status_icon} **{m['topic']}** ({m['difficulty']})")
                with col_b:
                    st.markdown(f"Mastery: **{m['mastery']:.0f}/100**")
                if m["status"] != "locked":
                    st.progress(m["mastery"] / 100)

            st.divider()
            st.markdown("### Skill Mastery")
            for skill, score in progress["mastery_by_skill"].items():
                col_x, col_y = st.columns([3, 1])
                with col_x:
                    st.markdown(skill)
                with col_y:
                    st.markdown(f"**{score:.0f}/100**")
                st.progress(score / 100)

    if st.button("← Back to Learning", use_container_width=True):
        st.session_state.page = "learning"
        st.rerun()
