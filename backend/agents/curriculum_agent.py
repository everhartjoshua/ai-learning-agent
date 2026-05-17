"""
Curriculum Agent
----------------
Takes a raw job description and produces a structured learning curriculum:
- Required and nice-to-have skills
- Ordered learning modules with prerequisites
- Success criteria for the role
"""

import json
from backend.llm_client import chat_json, chat


CURRICULUM_SYSTEM = """
You are an expert curriculum designer and career coach.
Given a job description, produce a comprehensive, structured learning curriculum
that would prepare a candidate to succeed in this role.

Your output must be valid JSON with this exact shape:
{
  "job_title": "string",
  "required_skills": ["skill1", "skill2", ...],
  "nice_to_have_skills": ["skill1", "skill2", ...],
  "modules": [
    {
      "index": 0,
      "topic": "string",
      "description": "string (2-3 sentences explaining what this module covers)",
      "prerequisites": ["topic names that must come before this"],
      "estimated_hours": 2,
      "difficulty": "beginner | intermediate | advanced",
      "key_concepts": ["concept1", "concept2", "concept3"]
    }
  ],
  "success_criteria": "string describing what mastery of this curriculum looks like"
}

Rules:
- Order modules logically: fundamentals before advanced topics
- Keep modules focused: one cohesive concept per module
- Aim for 6-12 modules total for a typical role
- estimated_hours should be realistic (1-8 hours per module)
- prerequisites must reference exact topic strings from other modules
"""


def generate_curriculum(job_description: str) -> dict:
    """
    Parse a job description and return a structured curriculum dict.

    Args:
        job_description: Raw text of the job posting

    Returns:
        dict with keys: job_title, required_skills, nice_to_have_skills,
                        modules, success_criteria
    """
    messages = [
        {
            "role": "user",
            "content": f"Generate a learning curriculum for this job description:\n\n{job_description}"
        }
    ]

    raw = chat_json(messages, system=CURRICULUM_SYSTEM)

    try:
        curriculum = json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON from response if model added extra text
        import re
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            curriculum = json.loads(match.group())
        else:
            raise ValueError(f"Could not parse curriculum JSON from model response:\n{raw}")

    # Ensure modules have sequential indexes
    for i, module in enumerate(curriculum.get("modules", [])):
        module["index"] = i

    return curriculum


def explain_curriculum(curriculum: dict) -> str:
    """
    Generate a friendly plain-language summary of the curriculum
    to show the student when they enroll.
    """
    messages = [
        {
            "role": "user",
            "content": (
                f"Here is a learning curriculum for the role of {curriculum['job_title']}:\n\n"
                f"{json.dumps(curriculum, indent=2)}\n\n"
                "Write a warm, encouraging 2-3 paragraph summary for a student who just enrolled. "
                "Explain what they'll learn, roughly how long it will take, and what they'll be "
                "able to do when they complete it. Don't use bullet points."
            )
        }
    ]
    return chat(messages, temperature=0.7)
