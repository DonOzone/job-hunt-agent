---
name: cv-gap-analysis
description: Compare the user's CV with found jobs, rank missing skills by importance and recommend courses or certifications. Use when asked about CV fit, skill gaps, upskilling or a study plan.
---

# CV match, gaps & study plan

1. Confirm `cv_path` in `config/profile.yaml` (or pass `--cv path`). PDFs/DOCX need `pip install -e '.[docs]'`.
2. `jobhunt cv-match --top 10` — per-job matched (✅) and missing (❌) skills.
3. `jobhunt gaps --jobs 30` — gaps ranked by importance (frequency × job rank × mention depth × skill weight),
   with curated courses/certifications from `src/jobhunt/data/courses.yaml`. Report: `workspace/skill-gaps.md`.
   Decisions steer it: jobs the user shortlisted (×1.5) or is preparing/applied to (×2) count more; skipped or
   closed jobs are ignored - so record decisions with `jobhunt memory decide <job> ...`.
4. `jobhunt ramp-up` — learning path (user's own list, curated, open materials); see the `skill-ramp-up` skill.
5. `jobhunt study-plan --hours 6` — week-by-week plan with check-in assessments.
6. If a skill is missing from the taxonomy, add it to `src/jobhunt/data/skills.yaml` (use `case_sensitive: true`
   for words that are also common English, e.g. "Go"). Add good courses to `courses.yaml`.
7. Log key insight: `jobhunt journal log "Top gap is X; starting course Y" --kind learning`.
