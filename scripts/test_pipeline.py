"""
Quick smoke test — runs the full pipeline once without the UI.
Usage: python scripts/test_pipeline.py

Make sure Ollama is running: ollama serve
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.db.models import init_db
from backend.agents import curriculum_agent, assessment_agent, tutor_agent

SAMPLE_JD = """
Job Title: Junior Python Developer

We're looking for a junior Python developer to join our backend team.

Requirements:
- 1+ years of Python experience or equivalent coursework
- Familiarity with REST APIs and HTTP concepts
- Basic understanding of SQL and relational databases
- Experience with Git and version control
- Ability to write clean, readable code with comments

Nice to have:
- Experience with FastAPI or Flask
- Familiarity with Docker
- Understanding of basic data structures and algorithms

Responsibilities:
- Build and maintain REST API endpoints
- Write unit tests for your code
- Collaborate with the team using Git
- Query and update data in PostgreSQL databases
"""


def run():
    print("=" * 60)
    print("Learning Agent — Pipeline Smoke Test")
    print("=" * 60)

    # 1. Init DB
    print("\n[1/5] Initializing database...")
    init_db()

    # 2. Generate curriculum
    print("\n[2/5] Generating curriculum from job description...")
    curriculum_data = curriculum_agent.generate_curriculum(SAMPLE_JD)
    print(f"  ✓ Job title: {curriculum_data['job_title']}")
    print(f"  ✓ Required skills: {len(curriculum_data['required_skills'])}")
    print(f"  ✓ Modules: {len(curriculum_data['modules'])}")
    for m in curriculum_data["modules"]:
        print(f"     {m['index']+1}. {m['topic']} ({m['difficulty']}, {m['estimated_hours']}h)")

    # 3. Generate diagnostic
    print("\n[3/5] Generating diagnostic questions...")
    diagnostic = assessment_agent.generate_diagnostic(curriculum_data, num_questions=3)
    questions = diagnostic["questions"]
    print(f"  ✓ Generated {len(questions)} questions")
    for q in questions:
        print(f"     [{q['difficulty']}] {q['question'][:70]}...")

    # 4. Simulate answers and evaluate
    print("\n[4/5] Simulating student answers and evaluating...")
    mock_answers = [
        {"question_id": q["id"], "answer": "I know a bit about this but not in depth."}
        for q in questions
    ]
    assessment = assessment_agent.evaluate_diagnostic(questions, mock_answers)
    overall = assessment.get("overall_assessment", {})
    print(f"  ✓ Strengths: {overall.get('strengths', [])}")
    print(f"  ✓ Gaps: {overall.get('gaps', [])}")
    print(f"  ✓ Summary: {overall.get('summary', '')[:100]}...")

    # 5. Generate a lesson and exercises for module 0
    print("\n[5/5] Generating lesson and exercises for first module...")
    first_module = curriculum_data["modules"][0]
    lesson = tutor_agent.generate_lesson(
        module=first_module,
        job_title=curriculum_data["job_title"],
        mastery_score=20,
    )
    print(f"  ✓ Lesson generated ({len(lesson)} chars)")
    print(f"  Preview: {lesson[:200]}...")

    exercises_data = tutor_agent.generate_exercises(
        module=first_module,
        job_title=curriculum_data["job_title"],
        mastery_score=20,
        num_exercises=2,
    )
    exercises = exercises_data.get("exercises", [])
    print(f"  ✓ Generated {len(exercises)} exercises")
    if exercises:
        print(f"  Sample: {exercises[0]['question'][:80]}...")

    print("\n" + "=" * 60)
    print("✅ Pipeline test complete! Everything is working.")
    print("=" * 60)
    print("\nNext steps:")
    print("  1. Start the backend:  uvicorn backend.api.main:app --reload")
    print("  2. Start the frontend: streamlit run frontend/app.py")


if __name__ == "__main__":
    run()
