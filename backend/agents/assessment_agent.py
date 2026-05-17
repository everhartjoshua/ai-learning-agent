"""
Assessment Agent
----------------
Generates diagnostic questions to probe a student's existing knowledge,
then analyzes their responses to identify skill gaps and recommended
starting points in the curriculum.
"""

import json
from backend.llm_client import chat_json, chat


DIAGNOSTIC_SYSTEM = """
You are an expert educational assessor. Your job is to probe a student's
existing knowledge on a topic WITHOUT being intimidating.

Generate diagnostic questions that:
- Range from basic recall to applied understanding
- Are clear and unambiguous
- Can be answered in 1-3 sentences (no essays)
- Reveal what the student actually knows, not just what they can look up

Output valid JSON only:
{
  "questions": [
    {
      "id": "q1",
      "question": "string",
      "skill_tested": "string (which skill from the curriculum this tests)",
      "difficulty": "basic | intermediate | advanced",
      "expected_concepts": ["concept the answer should mention"]
    }
  ]
}
"""

EVALUATION_SYSTEM = """
You are a fair, encouraging tutor evaluating a student's diagnostic answers.
For each answer, assess whether the student demonstrates understanding.

Be generous but honest. Partial credit for partially correct answers.

Output valid JSON only:
{
  "results": [
    {
      "question_id": "q1",
      "skill_tested": "string",
      "result": "correct | partial | incorrect",
      "score": 0-100,
      "notes": "brief note on what they got right/wrong"
    }
  ],
  "overall_assessment": {
    "strengths": ["skill1", "skill2"],
    "gaps": ["skill1", "skill2"],
    "recommended_start_module": 0,
    "summary": "2-3 sentence summary of the student's current level"
  }
}
"""


def generate_diagnostic(curriculum: dict, num_questions: int = 5) -> dict:
    """
    Generate diagnostic questions covering the curriculum's key skills.

    Args:
        curriculum: The curriculum dict (from curriculum_agent)
        num_questions: How many questions to generate (default 5)

    Returns:
        dict with a "questions" list
    """
    skills_summary = ", ".join(curriculum.get("required_skills", [])[:10])
    modules_summary = "\n".join(
        f"- {m['topic']}: {m['description']}"
        for m in curriculum.get("modules", [])[:6]
    )

    messages = [
        {
            "role": "user",
            "content": (
                f"Generate {num_questions} diagnostic questions for a student who wants to "
                f"become a {curriculum['job_title']}.\n\n"
                f"Key skills to assess: {skills_summary}\n\n"
                f"Curriculum modules:\n{modules_summary}\n\n"
                "Spread questions across different skills and difficulty levels."
            )
        }
    ]

    raw = chat_json(messages, system=DIAGNOSTIC_SYSTEM)
    return json.loads(raw)


def evaluate_diagnostic(questions: list[dict], answers: list[dict]) -> dict:
    """
    Evaluate a student's diagnostic answers.

    Args:
        questions: List of question dicts from generate_diagnostic
        answers:   List of {"question_id": "q1", "answer": "student's answer"} dicts

    Returns:
        dict with "results" and "overall_assessment"
    """
    qa_pairs = []
    answer_map = {a["question_id"]: a["answer"] for a in answers}

    for q in questions:
        qa_pairs.append({
            "question_id": q["id"],
            "question": q["question"],
            "skill_tested": q["skill_tested"],
            "expected_concepts": q.get("expected_concepts", []),
            "student_answer": answer_map.get(q["id"], "(no answer provided)")
        })

    messages = [
        {
            "role": "user",
            "content": (
                "Evaluate these diagnostic answers:\n\n"
                f"{json.dumps(qa_pairs, indent=2)}"
            )
        }
    ]

    raw = chat_json(messages, system=EVALUATION_SYSTEM)
    return json.loads(raw)


def determine_start_module(assessment: dict, curriculum: dict) -> int:
    """
    Given assessment results, pick the best module to start from.
    Skips modules that cover skills the student already knows well.
    """
    gaps = assessment.get("overall_assessment", {}).get("gaps", [])
    modules = curriculum.get("modules", [])

    # Find first module that addresses a gap skill
    for i, module in enumerate(modules):
        topic_lower = module["topic"].lower()
        concepts_lower = [c.lower() for c in module.get("key_concepts", [])]
        for gap in gaps:
            gap_lower = gap.lower()
            if gap_lower in topic_lower or any(gap_lower in c for c in concepts_lower):
                return i

    # Default: use the recommended index from the LLM, or 0
    return assessment.get("overall_assessment", {}).get("recommended_start_module", 0)
