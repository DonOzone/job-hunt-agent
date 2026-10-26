---
name: skill-evaluation
description: Evaluate the user's proficiency in skills (quiz or structured self-assessment) and determine eligibility for found jobs. Use when asked to test skills, check readiness or decide whether to apply.
---

# Skill evaluation & eligibility study

1. Pick skills: the job's required skills (`jobhunt cv-match`) or the top gaps (`jobhunt gaps`).
2. Quiz: `jobhunt assess "<Skill>" -n 5` (bank: `src/jobhunt/data/question_bank.yaml`). Skills without questions
   fall back to a 0–5 self-rating with evidence (unverified claims are discounted 20%).
   You may also run a conversational quiz yourself: ask 5 graded questions, score 0–1 and record it with
   `jobhunt assess "<Skill>" --self` using the equivalent rating.
3. Eligibility: `jobhunt eligibility [job]` combines assessed proficiency (or 0.6 for CV-only skills) weighted by
   skill importance. Verdicts: Strong (≥70%, no blockers) / Stretch (≥45%) / Not yet. Blockers are heavy-weight
   skills under 40%.
4. Turn blockers into a plan: `jobhunt study-plan`, then re-assess at each check-in date and journal the result.
5. When adding questions, keep 4 options, one correct `answer` index and an optional `why`.
