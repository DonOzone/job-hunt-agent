---
name: interview-prep
description: Build and run interview preparation for found or applied jobs - research checklist, technical and behavioural questions, STAR stories and mock interviews. Use when the user has an interview or wants to prepare.
---

# Interview preparation

1. Generate packs: `jobhunt interview-prep <job>` (or top 3 by default) → `workspace/interview-prep/*.md`.
   Packs include seniority signal, CV strengths/gaps, research checklist, per-skill technical questions,
   system design for senior roles, behavioural questions chosen from the posting's language, STAR story slots,
   questions to ask, and a 5-day practice schedule.
2. Mock interview mode: ask one question at a time from the pack, wait for the answer, then give feedback on
   structure (STAR), specificity, metrics and length (aim for ~2 minutes). Suggest a stronger version.
3. For gaps, coach an honest "learning story": what you know, how you'd ramp up, evidence of learning fast.
4. Log practice and feedback: `jobhunt journal log "Mock: weak on system design trade-offs" --kind learning`.
5. After the real interview: `jobhunt track update <app-id> interview --note "..." --next "Thank-you email" --due 1`.
