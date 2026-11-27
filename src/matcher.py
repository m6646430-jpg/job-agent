"""LLM scoring of a JD against the candidate profile, plus tailored content generation."""

SCORE_SYSTEM = (
    "You are a strict recruiting analyst. Given a candidate profile and a job "
    "description, score fit 0-100. Score >= 70 only if the candidate could "
    "credibly get an interview: required skills overlap, seniority matches, "
    "location/visa is compatible. Penalize hard requirements the candidate lacks."
)

TAILOR_SYSTEM = (
    "You write concise, specific job-application content for a candidate. "
    "Never invent experience the profile does not contain. Plain text, no markdown. "
    "Cover letters: max 180 words, name real overlaps between the profile and this JD, "
    "no generic flattery."
)


def score_job(llm, profile: str, job) -> tuple[int, str]:
    result = llm.chat_json(
        SCORE_SYSTEM,
        f"CANDIDATE PROFILE:\n{profile}\n\n"
        f"JOB: {job['title']} at {job['company']} ({job['location']})\n"
        f"DESCRIPTION:\n{job['jd_text'][:6000]}\n\n"
        'Return {"score": <0-100>, "reason": "<one sentence>"}',
    )
    return int(result.get("score", 0)), str(result.get("reason", ""))


def tailor(llm, profile: str, job, questions: list[str]) -> dict:
    """One call: cover letter + answers to the form's custom questions."""
    q_block = "\n".join(f"- {q}" for q in questions) if questions else "(none)"
    result = llm.chat_json(
        TAILOR_SYSTEM,
        f"CANDIDATE PROFILE:\n{profile}\n\n"
        f"JOB: {job['title']} at {job['company']}\n"
        f"DESCRIPTION:\n{job['jd_text'][:6000]}\n\n"
        f"CUSTOM APPLICATION QUESTIONS:\n{q_block}\n\n"
        'Return {"cover_letter": "...", "answers": {"<question text verbatim>": "<answer>"}}. '
        "Answers must be truthful to the profile; if the profile lacks the information, "
        'answer conservatively (e.g. "No" for certifications not listed).',
    )
    return {
        "cover_letter": result.get("cover_letter", ""),
        "answers": result.get("answers", {}) or {},
    }
