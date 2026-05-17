"""
Tutor Agent
-----------
The core learning loop. For each module:
  1. Generate practice exercises calibrated to the student's level
  2. Build a textbook-chapter-quality lesson that teaches EVERYTHING needed
     to solve those exercises (plan → parallel section writes → coverage audit)
  3. Evaluate answers and provide constructive feedback
  4. Decide whether to advance or run a targeted remediation pass — which
     reuses the same deep-lesson machinery, focused on the missed concepts.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from backend.llm_client import chat, chat_json


# ──────────────────────────────────────────────────────────────
# DEEP LESSON GENERATION
# ──────────────────────────────────────────────────────────────
# We trade single-call speed for chapter-quality depth. Pipeline:
#
#   1. PLAN     — one chat_json call. Builds an outline tied to the exercises
#                 the student will face. Each section declares which concepts
#                 it teaches and which exercise IDs it prepares for.
#   2. WRITE    — one chat call per section, run in parallel. Each section
#                 gets a generous max_tokens budget and explicit instructions
#                 to include worked examples and pitfalls.
#   3. AUDIT    — one chat_json call. Maps each exercise to the section(s)
#                 that prepare for it. If anything is uncovered, we generate
#                 a gap-fill addendum and append it.
#
# The same pipeline runs for first-time lessons and remediation; remediation
# just passes `focus_concepts` and `round_number`, which the planner uses
# to bias every section toward those gaps.

LESSON_PLAN_SYSTEM = """
You are an instructional designer building a textbook-chapter-quality lesson
outline for a {job_title} candidate.

NON-NEGOTIABLE REQUIREMENT: by the end of the lesson, the student must be
able to solve EVERY one of the practice exercises listed below. Plan
backwards from those exercises. For each exercise, identify what the student
must know — vocabulary, definitions, mental models, procedures, formulas,
common patterns — and make sure a section teaches it.

Structure the outline so it teaches GROUND UP:
  • First sections cover prerequisites and fundamentals (definitions, mental
    models, the "why this exists" framing).
  • Middle sections cover core concepts with worked examples.
  • Later sections cover applied/scenario work that mirrors the exercises.
  • Final section is a recap that maps concepts back to exercise types.

{remediation_note}

Output VALID JSON ONLY, no markdown, no commentary:
{{
  "title": "string",
  "learning_objectives": ["After this lesson, the student will be able to ..."],
  "prerequisites_assumed": ["thing the student should already know"],
  "sections": [
    {{
      "id": "s1",
      "title": "string",
      "purpose": "one-sentence why this section exists",
      "covers_concepts": ["concept name", "concept name"],
      "prepares_for_exercises": ["e1"],
      "worked_examples_to_include": ["short description of example 1"],
      "common_pitfalls_to_address": ["pitfall description"],
      "target_word_count": 600
    }}
  ],
  "exercise_coverage_map": {{
    "e1": ["s1", "s3"]
  }}
}}

Rules:
  • Produce 5-7 sections for a first-time lesson, 4-6 for remediation.
  • EVERY exercise ID below MUST appear in exercise_coverage_map and in at
    least one section's prepares_for_exercises list.
  • target_word_count is 400-900 per section; bigger for complex sections.
  • Section ids are s1, s2, s3, ... in order.
"""


SECTION_WRITER_SYSTEM = """
You are an expert tutor writing ONE section of a textbook-chapter-style lesson
for a {job_title} candidate.

You are given:
  • The full lesson outline (so you know what other sections will cover)
  • The specific section you must write
  • The practice exercises the section is meant to prepare for

Write THIS section only — do not write other sections.

REQUIRED elements for the section:
  1. A 1-2 sentence opener explaining what the student will learn and why it
     matters for the {job_title} role.
  2. Each listed concept gets a clear definition + at least one concrete
     example. Use {job_title}-flavored examples wherever possible.
  3. Every "worked_examples_to_include" entry must appear as a FULLY worked
     example showing each step of reasoning, not just the final answer.
  4. Every "common_pitfalls_to_address" entry must be called out explicitly
     with the wrong approach + the right approach.
  5. End with a one-sentence pointer to the next section (or to the practice
     exercises if this is the final section).

Format:
  • Markdown.
  • Use ### for the section heading (the section title verbatim).
  • Use #### for subsection headings as needed.
  • DO NOT use # or ## — those are reserved for the lesson-level headers.
  • Use fenced code blocks for code/SQL/JSON/etc. Use **bold** for
    vocabulary the student should memorize.
  • Aim for the given target word count, +/- 25%. Do not pad; do not truncate.

You're writing for a learner who has NEVER seen this material before. Define
every piece of jargon the first time it appears. Show your work in examples.
"""


COVERAGE_AUDIT_SYSTEM = """
You are an instructional designer auditing a lesson against its practice
exercises.

For each exercise, identify which lesson section(s) prepare the student to
answer it, and whether the coverage is sufficient. A section is "sufficient"
if a student who carefully read it would have the vocabulary, mental models,
procedures, and worked examples needed to attempt the exercise.

Output VALID JSON ONLY:
{
  "coverage": [
    {
      "exercise_id": "e1",
      "covered_by_sections": ["section title or s-id"],
      "sufficient": true,
      "missing_concepts": []
    }
  ],
  "gap_addendum_needed": false,
  "gap_addendum_topic": "",
  "gap_addendum_concepts": []
}

Set gap_addendum_needed=true only if at least one exercise has sufficient=false.
gap_addendum_topic should describe what the addendum should teach (one
sentence). gap_addendum_concepts should list the specific concepts that need
to be added.
"""


GAP_ADDENDUM_SYSTEM = """
You are an expert tutor writing a "Gap Fill" addendum to a lesson for a
{job_title} candidate.

The lesson covered most of what's needed for the exercises, but the audit
found these concepts were under-covered. Write a concise but thorough
section that teaches them — definitions, mental models, at least one fully
worked example per concept, and any common pitfalls.

Format: markdown, starting with `### Appendix: Filling the Gaps`.
Aim for 400-800 words. No padding.
"""


def _exercise_brief(exercise: dict) -> str:
    """Render an exercise for inclusion in planner / auditor prompts."""
    return (
        f"[id={exercise.get('id', '?')}] "
        f"(type={exercise.get('type', '?')}, skill={exercise.get('skill_tested', '?')})\n"
        f"Q: {exercise.get('question', '')}\n"
        f"Ideal-answer cue: {exercise.get('sample_answer', '')[:300]}"
    )


def _extract_json(raw: str) -> dict:
    """Tolerant JSON parser — strips markdown fences and finds the JSON body."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            return json.loads(match.group())
        raise


def _plan_lesson(
    module: dict,
    exercises: list[dict],
    job_title: str,
    mastery_score: float,
    *,
    remediation: bool,
    focus_concepts: list[str] | None,
    recent_mistakes: list[str] | None,
    round_number: int,
) -> dict:
    """Phase 1: produce a lesson outline tied to the exercises."""
    if remediation:
        bullet_focus = (
            "\n".join(f"  - {c}" for c in focus_concepts) if focus_concepts else "  - (general weak spots)"
        )
        bullet_mistakes = (
            "\n".join(f"  - {m}" for m in (recent_mistakes or [])[:5]) or "  - (none recorded)"
        )
        rem_note = (
            f"This is REMEDIATION round {round_number}. The student has already seen the\n"
            f"main lesson and failed practice exercises. Build the outline so it teaches\n"
            f"the missed concepts from the ground up using a fresh angle — analogies,\n"
            f"slow walk-throughs, and very explicit worked examples.\n\n"
            f"Concepts the student is still weak on:\n{bullet_focus}\n\n"
            f"Specific mistakes from the last round:\n{bullet_mistakes}\n\n"
            f"At least 60% of the sections should focus on these concepts."
        )
    else:
        rem_note = (
            "This is the student's FIRST lesson on this topic. Teach it ground-up.\n"
            "Do not assume domain familiarity beyond the prerequisites you list."
        )

    system = LESSON_PLAN_SYSTEM.format(job_title=job_title, remediation_note=rem_note)

    exercises_block = "\n\n".join(_exercise_brief(e) for e in exercises)

    user = (
        f"Topic: {module['topic']}\n"
        f"Module description: {module.get('description', '')}\n"
        f"Key concepts in the module: {', '.join(module.get('key_concepts', []))}\n"
        f"Difficulty: {module.get('difficulty', 'intermediate')}\n"
        f"Student mastery so far: {mastery_score}/100\n\n"
        f"Practice exercises the student will face after this lesson "
        f"(plan the lesson so they can solve every one):\n\n"
        f"{exercises_block}"
    )

    raw = chat_json(
        [{"role": "user", "content": user}],
        system=system,
        temperature=0.4,
        max_tokens=2500,
    )
    return _extract_json(raw)


def _write_section(
    section: dict,
    outline_summary: str,
    exercises: list[dict],
    job_title: str,
) -> tuple[str, str]:
    """Phase 2: write a single section. Returns (section_id, markdown)."""
    relevant_ex_ids = set(section.get("prepares_for_exercises") or [])
    relevant_exercises = [e for e in exercises if e.get("id") in relevant_ex_ids]
    ex_block = (
        "\n\n".join(_exercise_brief(e) for e in relevant_exercises)
        if relevant_exercises
        else "(this section is foundational; it does not directly prepare for a specific exercise)"
    )

    target = int(section.get("target_word_count") or 600)

    user = (
        f"Outline summary (so you can cross-reference, but only WRITE the one section below):\n"
        f"{outline_summary}\n\n"
        f"───────────────────────────────────\n"
        f"Write THIS section:\n"
        f"  id: {section.get('id', '?')}\n"
        f"  title: {section.get('title', '?')}\n"
        f"  purpose: {section.get('purpose', '')}\n"
        f"  covers_concepts: {section.get('covers_concepts') or []}\n"
        f"  worked_examples_to_include: {section.get('worked_examples_to_include') or []}\n"
        f"  common_pitfalls_to_address: {section.get('common_pitfalls_to_address') or []}\n"
        f"  target_word_count: {target}\n\n"
        f"Exercises this section prepares for:\n{ex_block}"
    )

    system = SECTION_WRITER_SYSTEM.format(job_title=job_title)

    # Generous token budget: ~1.5 words per token at the high end, plus headroom.
    max_tokens = max(1200, int(target * 2.2))

    body = chat(
        [{"role": "user", "content": user}],
        system=system,
        temperature=0.55,
        max_tokens=max_tokens,
    )
    return section.get("id", "?"), body.strip()


def _outline_summary(outline: dict) -> str:
    """Compact summary of the outline for section-writer prompts."""
    lines = [f"Title: {outline.get('title', '')}"]
    objs = outline.get("learning_objectives") or []
    if objs:
        lines.append("Objectives: " + "; ".join(objs))
    for s in outline.get("sections", []):
        lines.append(
            f"  {s.get('id', '?')}. {s.get('title', '')} — "
            f"{s.get('purpose', '')}"
        )
    return "\n".join(lines)


def _audit_coverage(lesson_markdown: str, exercises: list[dict]) -> dict:
    """Phase 3: check that each exercise is sufficiently covered."""
    ex_block = "\n\n".join(_exercise_brief(e) for e in exercises)
    user = (
        f"LESSON (markdown):\n\n{lesson_markdown}\n\n"
        f"───────────────────────────────────\n"
        f"EXERCISES THE LESSON MUST PREPARE FOR:\n\n{ex_block}"
    )
    raw = chat_json(
        [{"role": "user", "content": user}],
        system=COVERAGE_AUDIT_SYSTEM,
        temperature=0.2,
        max_tokens=1500,
    )
    return _extract_json(raw)


def _write_gap_addendum(
    job_title: str,
    gap_topic: str,
    gap_concepts: list[str],
) -> str:
    """Phase 4 (conditional): fill in missing coverage."""
    user = (
        f"Topic to cover in this addendum: {gap_topic}\n"
        f"Concepts that need to be added: {', '.join(gap_concepts) or '(see topic)'}\n\n"
        "Write the addendum now."
    )
    return chat(
        [{"role": "user", "content": user}],
        system=GAP_ADDENDUM_SYSTEM.format(job_title=job_title),
        temperature=0.5,
        max_tokens=2000,
    ).strip()


def generate_deep_lesson(
    module: dict,
    exercises: list[dict],
    job_title: str,
    mastery_score: float,
    *,
    remediation: bool = False,
    focus_concepts: list[str] | None = None,
    recent_mistakes: list[str] | None = None,
    round_number: int = 0,
    max_parallel_sections: int = 4,
) -> str:
    """
    Build a textbook-chapter-quality lesson that teaches EVERYTHING needed for
    the given exercises.

    See module docstring for the pipeline. Returns a single markdown string.
    """
    # ── Phase 1: PLAN ──────────────────────────────────────────────
    outline = _plan_lesson(
        module=module,
        exercises=exercises,
        job_title=job_title,
        mastery_score=mastery_score,
        remediation=remediation,
        focus_concepts=focus_concepts,
        recent_mistakes=recent_mistakes,
        round_number=round_number,
    )
    sections = outline.get("sections") or []
    if not sections:
        # Degraded path — return a single-call lesson so the user still gets something.
        return generate_lesson(
            module=module,
            job_title=job_title,
            mastery_score=mastery_score,
            recent_mistakes=recent_mistakes,
        )

    summary = _outline_summary(outline)

    # ── Phase 2: WRITE sections in parallel ────────────────────────
    written: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max_parallel_sections) as pool:
        futures = {
            pool.submit(_write_section, s, summary, exercises, job_title): s
            for s in sections
        }
        for fut in as_completed(futures):
            s = futures[fut]
            try:
                sec_id, body = fut.result()
                written[sec_id] = body
            except Exception as exc:  # pragma: no cover - degraded path
                written[s.get("id", "?")] = (
                    f"### {s.get('title', 'Section')}\n\n"
                    f"_(This section failed to generate: {exc}.)_\n"
                )

    # Assemble in outline order.
    parts: list[str] = []
    parts.append(f"# {outline.get('title', module.get('topic', 'Lesson'))}")
    if outline.get("learning_objectives"):
        parts.append("## What you'll be able to do after this lesson\n")
        for obj in outline["learning_objectives"]:
            parts.append(f"- {obj}")
        parts.append("")
    if outline.get("prerequisites_assumed"):
        parts.append("## Prerequisites assumed\n")
        for p in outline["prerequisites_assumed"]:
            parts.append(f"- {p}")
        parts.append("")
    for s in sections:
        parts.append(written.get(s.get("id", "?"), ""))
        parts.append("")
    lesson_markdown = "\n".join(parts).strip() + "\n"

    # ── Phase 3 + 4: AUDIT + (optional) gap addendum ───────────────
    try:
        audit = _audit_coverage(lesson_markdown, exercises)
    except Exception:
        audit = {"gap_addendum_needed": False}

    if audit.get("gap_addendum_needed"):
        try:
            addendum = _write_gap_addendum(
                job_title=job_title,
                gap_topic=audit.get("gap_addendum_topic", "concepts under-covered above"),
                gap_concepts=audit.get("gap_addendum_concepts") or [],
            )
            lesson_markdown = lesson_markdown.rstrip() + "\n\n" + addendum + "\n"
        except Exception:
            pass  # If addendum fails, ship the base lesson anyway.

    return lesson_markdown


# ──────────────────────────────────────────────────────────────
# BACKWARDS-COMPATIBLE WRAPPERS
# ──────────────────────────────────────────────────────────────
# Old callers (tests, /sessions/start path before the rewrite) can still call
# generate_lesson() and generate_remediation_lesson(); both now defer to
# generate_deep_lesson() when exercises are available. When they're not, we
# fall back to a single-call lesson so the module remains usable in isolation.

def generate_lesson(
    module: dict,
    job_title: str,
    mastery_score: float,
    recent_mistakes: list[str] | None = None,
    exercises: list[dict] | None = None,
) -> str:
    """
    Generate a personalized lesson for a curriculum module.

    If `exercises` is provided, runs the full deep-lesson pipeline (plan →
    parallel section writes → coverage audit). Otherwise falls back to the
    legacy single-call shape so the module is still useful standalone.
    """
    if exercises:
        return generate_deep_lesson(
            module=module,
            exercises=exercises,
            job_title=job_title,
            mastery_score=mastery_score,
            recent_mistakes=recent_mistakes,
        )

    # Legacy single-call path (no exercises to align to).
    level_instruction = (
        "This is a first introduction — start from fundamentals."
        if mastery_score < 20 else
        "The student has some exposure — skip basic definitions, focus on depth and nuance."
        if mastery_score < 60 else
        "The student is fairly strong here — focus on edge cases, best practices, and advanced patterns."
    )

    mistake_context = ""
    if recent_mistakes:
        mistake_context = (
            f"\n\nThe student previously struggled with:\n"
            + "\n".join(f"- {m}" for m in recent_mistakes[:5])
            + "\nMake sure to address these areas clearly."
        )

    system = f"""
You are an expert tutor preparing a candidate for a {job_title} role.
Write clear, engaging lessons that connect concepts directly to real job tasks.
Use concrete examples relevant to the {job_title} role.
Format your lesson in markdown with clear sections.
Keep it focused — aim for a 10-15 minute read.
{level_instruction}
"""

    messages = [
        {
            "role": "user",
            "content": (
                f"Teach me about: **{module['topic']}**\n\n"
                f"Description: {module['description']}\n"
                f"Key concepts to cover: {', '.join(module.get('key_concepts', []))}\n"
                f"Difficulty level: {module.get('difficulty', 'intermediate')}"
                f"{mistake_context}"
            ),
        }
    ]
    return chat(messages, system=system, temperature=0.6, max_tokens=3000)


def generate_remediation_lesson(
    module: dict,
    job_title: str,
    focus_concepts: list[str],
    recent_mistakes: list[str],
    round_number: int,
    exercises: list[dict] | None = None,
    mastery_score: float = 0.0,
) -> str:
    """
    Generate a *deep-dive* remediation lesson focused on missed concepts.

    Prefers the full deep-lesson pipeline when exercises are available so
    each section is tied to the practice the student is about to attempt.
    """
    if exercises:
        return generate_deep_lesson(
            module=module,
            exercises=exercises,
            job_title=job_title,
            mastery_score=mastery_score,
            remediation=True,
            focus_concepts=focus_concepts,
            recent_mistakes=recent_mistakes,
            round_number=round_number,
        )

    # Legacy single-call remediation (kept for test_pipeline.py / smoke tests).
    angle = {
        1: "Use analogies, worked examples, and step-by-step walk-throughs.",
        2: "Slow down dramatically; use very concrete, simple examples first.",
        3: "Focus only on the minimum needed; one end-to-end worked example.",
    }.get(round_number, "Take a fresh angle on the material.")

    system = (
        f"You are an expert tutor for a {job_title} candidate running a "
        f"TARGETED REMEDIATION lesson. {angle} Format in markdown."
    )
    focus_block = "\n".join(f"- {c}" for c in focus_concepts) or "- (general weak spots)"
    mistake_block = "\n".join(f"- {m}" for m in recent_mistakes[:5]) or "- (none)"
    user = (
        f"Topic: **{module['topic']}**\n"
        f"Description: {module.get('description', '')}\n\n"
        f"Concepts still weak:\n{focus_block}\n\n"
        f"Recent mistakes:\n{mistake_block}\n\n"
        "Write a focused remediation lesson."
    )
    return chat([{"role": "user", "content": user}], system=system, temperature=0.6, max_tokens=3000)


# ──────────────────────────────────────────────────────────────
# EXERCISE GENERATION
# ──────────────────────────────────────────────────────────────

EXERCISE_SYSTEM = """
You are a tutor generating practice exercises.
Make exercises realistic — they should mirror tasks the student will face on the job.
Vary the format: some conceptual, some applied, some scenario-based.

Output valid JSON only:
{
  "exercises": [
    {
      "id": "e1",
      "question": "string (the full question text)",
      "type": "conceptual | applied | scenario",
      "skill_tested": "string",
      "hint": "string (optional hint, shown only if student asks)",
      "sample_answer": "string (ideal answer, NOT shown to student)"
    }
  ]
}
"""


def generate_exercises(
    module: dict,
    job_title: str,
    mastery_score: float,
    num_exercises: int = 3,
    focus_concepts: list[str] | None = None,
) -> dict:
    """
    Generate practice exercises for a module, calibrated to the student's level.

    If `focus_concepts` is provided, the exercises target those specific concepts
    (used during remediation rounds).
    """
    difficulty_note = (
        "Make exercises straightforward and foundational."
        if mastery_score < 30 else
        "Mix foundational and challenging exercises."
        if mastery_score < 70 else
        "Make exercises challenging — edge cases, trade-offs, real-world scenarios."
    )

    focus_note = ""
    if focus_concepts:
        focus_note = (
            "\n\nIMPORTANT: This is a remediation round. The student previously "
            "struggled with the following concepts — every exercise should test one "
            "of these directly, in a different scenario than they've seen before:\n"
            + "\n".join(f"- {c}" for c in focus_concepts)
        )

    messages = [
        {
            "role": "user",
            "content": (
                f"Generate {num_exercises} practice exercises on: {module['topic']}\n\n"
                f"For a {job_title} role.\n"
                f"Key concepts: {', '.join(module.get('key_concepts', []))}\n"
                f"Student mastery so far: {mastery_score}/100\n"
                f"{difficulty_note}"
                f"{focus_note}"
            ),
        }
    ]

    raw = chat_json(messages, system=EXERCISE_SYSTEM, temperature=0.7, max_tokens=2500)
    return json.loads(raw)


# ──────────────────────────────────────────────────────────────
# ANSWER EVALUATION
# ──────────────────────────────────────────────────────────────

FEEDBACK_SYSTEM = """
You are a supportive tutor evaluating a student's exercise answer.
Be honest but encouraging. Explain clearly what they got right and what needs work.
Always end with a concrete tip for improvement.

Output valid JSON only:
{
  "result": "correct | partial | incorrect",
  "score": 0-100,
  "feedback": "string (2-4 sentences of constructive feedback)",
  "what_was_good": "string (always find something positive)",
  "what_to_improve": "string (specific, actionable)",
  "follow_up_tip": "string (one thing to study or practice next)",
  "missed_concept": "string (the specific concept the student got wrong, in 2-5 words; empty string if they got it right)"
}
"""


def evaluate_answer(exercise: dict, student_answer: str, job_title: str) -> dict:
    """Evaluate a student's answer to an exercise."""
    messages = [
        {
            "role": "user",
            "content": (
                f"Evaluate this student answer for a {job_title} candidate.\n\n"
                f"Question: {exercise['question']}\n\n"
                f"Sample ideal answer: {exercise.get('sample_answer', 'N/A')}\n\n"
                f"Student's answer: {student_answer}\n\n"
                f"Skill being tested: {exercise.get('skill_tested', 'general')}"
            ),
        }
    ]
    raw = chat_json(messages, system=FEEDBACK_SYSTEM, temperature=0.3, max_tokens=1200)
    return json.loads(raw)


# ──────────────────────────────────────────────────────────────
# IN-LESSON CHATBOT
# ──────────────────────────────────────────────────────────────
# The student can ask questions while reading a lesson or while attempting
# a practice exercise. We use two different system prompts depending on
# context:
#
#   • lesson mode   — friendly tutor anchored to the lesson markdown. Will
#                     pull explicitly from the lesson where possible, can
#                     connect to the job role for context, and gently
#                     redirects truly off-topic questions back to the
#                     lesson.
#   • practice mode — Socratic tutor. Has access to the sample answer for
#                     the current exercise but MUST NEVER reveal it. Asks
#                     leading questions, points the student to relevant
#                     parts of the lesson, and only confirms an answer is
#                     correct after the student has produced it themselves.

LESSON_CHAT_SYSTEM = """
You are an in-lesson tutor for a student preparing for a {job_title} role.
You can see the full lesson the student is reading, plus a short history of
the conversation. The student is asking you questions about that lesson.

How to answer:
  • Anchor every answer in the lesson content where possible. Refer to the
    section that covers the concept ("As the section on X explains, ..."),
    and quote or paraphrase the relevant part.
  • If the question is about the lesson but the lesson didn't cover it,
    answer concisely from {job_title}-relevant general knowledge and tell
    the student "the lesson doesn't go into this in depth, but here's the
    short version."
  • If the question is totally unrelated to the lesson or the {job_title}
    role (e.g. "what's the weather"), politely redirect: "Let's stay
    focused on {topic} — what part of the lesson is unclear?"
  • Be concise. 2-5 sentences for simple clarifications. Use bullets or
    a short code example only if the question really needs them.
  • Use markdown. Use **bold** for terms, fenced code blocks for code.

Tone: warm, encouraging, never condescending. Treat the student like a
curious adult.
"""


PRACTICE_CHAT_SYSTEM = """
You are a Socratic tutor for a student preparing for a {job_title} role.
The student is currently working on a practice exercise. You have access
to the lesson the student just read, the exercise question, AND the ideal
sample answer — but you MUST NOT reveal the sample answer or any major
part of it, ever, even if the student asks directly.

Your job is to help the student arrive at the answer themselves through:
  • Targeted questions ("What does the lesson say about X? How might that
    apply here?")
  • Hints that surface a small next step, not the full path
  • Pointers back to the relevant section of the lesson
  • Asking the student to walk you through their reasoning

If the student asks "what's the answer?" or "just tell me", you respond
with something like: "I can't give it away — but here's a hint: ..."

If the student gives you a candidate answer in chat, you may evaluate
their reasoning (point out what's right, point out gaps, ask follow-up
questions) but DO NOT confirm correctness as a final verdict — that's the
job of the Submit Answer flow. Encourage them to submit when they think
they've got it.

Be concise. 2-4 sentences per turn unless walking through reasoning.
Use markdown for emphasis and code blocks for code.
"""


def _format_chat_history(history: list[dict], max_turns: int = 10) -> list[dict]:
    """
    Turn the persisted history into messages the LLM can consume. We trim to
    the last `max_turns` turns to keep context size manageable; older context
    is still visible to the student in the UI but the model only sees the
    recent ones.
    """
    trimmed = history[-max_turns:]
    msgs: list[dict] = []
    for m in trimmed:
        role = m.get("role")
        content = m.get("content") or ""
        if role in ("user", "assistant") and content.strip():
            msgs.append({"role": role, "content": content})
    return msgs


def chat_with_student(
    *,
    student_message: str,
    history: list[dict],
    lesson_text: str,
    module: dict,
    job_title: str,
    mode: str = "lesson",
    current_exercise: dict | None = None,
) -> str:
    """
    Generate one assistant reply for the in-lesson chatbot.

    Args:
        student_message:  The new message the student just sent.
        history:          Prior turns ([{role: "user"|"assistant", content: str}, ...]).
                          Does NOT include `student_message` — it's passed separately.
        lesson_text:      Full markdown of the lesson the student is reading.
        module:           Module dict (topic, description, key_concepts).
        job_title:        Target role, for context.
        mode:             "lesson" or "practice". Picks the system prompt.
        current_exercise: For practice mode — the exercise the student is on
                          ({question, sample_answer, skill_tested, hint}).
                          Required for practice mode; ignored otherwise.

    Returns:
        The assistant's reply as a markdown string.
    """
    topic = module.get("topic", "this topic")

    if mode == "practice":
        sys_prompt = PRACTICE_CHAT_SYSTEM.format(job_title=job_title)
        ex = current_exercise or {}
        context_block = (
            f"LESSON (for your reference — quote/paraphrase as needed):\n"
            f"---\n{lesson_text}\n---\n\n"
            f"CURRENT EXERCISE the student is attempting:\n"
            f"Question: {ex.get('question', '(no current exercise)')}\n"
            f"Skill tested: {ex.get('skill_tested', '?')}\n"
            f"Hint (you may share if asked): {ex.get('hint', '(none)')}\n"
            f"Sample answer (NEVER REVEAL — for your reasoning only): "
            f"{ex.get('sample_answer', '(none)')}\n"
        )
    else:
        sys_prompt = LESSON_CHAT_SYSTEM.format(job_title=job_title, topic=topic)
        context_block = (
            f"LESSON the student is reading (anchor your answers here):\n"
            f"---\n{lesson_text}\n---\n\n"
            f"Topic: {topic}\n"
            f"Module description: {module.get('description', '')}\n"
            f"Key concepts: {', '.join(module.get('key_concepts', []))}"
        )

    # The context goes into a leading "system" turn alongside the system prompt
    # so the model treats it as ground truth rather than something the student
    # said. We send it as part of the system message for simplicity.
    full_system = sys_prompt + "\n\n" + context_block

    messages = _format_chat_history(history)
    messages.append({"role": "user", "content": student_message})

    return chat(messages, system=full_system, temperature=0.5, max_tokens=1200).strip()


# ──────────────────────────────────────────────────────────────
# ADAPTIVE ROUTING
# ──────────────────────────────────────────────────────────────

# After this many remediation rounds on the same module, we let the student
# move on regardless. Prevents getting stuck in a loop on a single topic forever.
MAX_REMEDIATION_ROUNDS = 3


def should_advance(
    mastery_score: float,
    session_results: list[str],
    remediation_round: int = 0,
) -> tuple[bool, str]:
    """
    Decide whether to advance to the next module, run a remediation pass,
    or (after enough rounds) move on anyway.
    """
    if not session_results:
        return False, "No exercises completed yet."

    correct = session_results.count("correct")
    partial = session_results.count("partial")
    total = len(session_results)

    weighted_score = (correct * 1.0 + partial * 0.5) / total
    pct = round(weighted_score * 100)

    if mastery_score >= 75 and weighted_score >= 0.7:
        return True, f"Great work! You scored {pct}% this session."
    if mastery_score >= 60 and weighted_score >= 0.8:
        return True, "Strong performance — moving to the next topic."

    if remediation_round >= MAX_REMEDIATION_ROUNDS:
        return True, (
            f"You've worked through this topic {remediation_round + 1} times. "
            f"Let's keep momentum and move forward — we'll circle back later if needed."
        )

    return False, (
        f"Let's reinforce this topic. You got {correct}/{total} fully correct. "
        f"I'll build a deeper, focused lesson on the parts that tripped you up, "
        f"plus fresh exercises so you can show me you've got it."
    )


def extract_focus_concepts(attempts: list[dict]) -> tuple[list[str], list[str]]:
    """
    Given a list of attempt dicts, return (focus_concepts, mistake_descriptions)
    for use by remediation.
    """
    seen: set[str] = set()
    focus: list[str] = []
    mistakes: list[str] = []

    for a in attempts:
        if a.get("result") == "correct":
            continue

        concept = (a.get("missed_concept") or "").strip()
        if not concept:
            concept = (a.get("skill_tested") or "").strip()

        if concept and concept.lower() not in seen:
            seen.add(concept.lower())
            focus.append(concept)

        feedback = (a.get("feedback") or "").strip()
        if feedback:
            mistakes.append(feedback[:300])

    return focus, mistakes
