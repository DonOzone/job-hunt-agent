---
name: prepare-application
description: Build a complete application kit for a job the user selected (fit check, tailored CV, cover letter, form answers, interview prep, checklist), then hand off to the apply assistant. Use when the user says "help me apply to this job" or picks a job.
---

# Prepare an application for a selected job

1. Let the user choose: `jobhunt pick` (interactive) or use the rank/ID they gave.
2. `jobhunt prepare <job>` — runs the fit gates first (blocked jobs need the user's OK → `--force`), then writes
   `workspace/applications/<job>/`: fit report, CV review + tailored draft (.md/.docx; `--no-docx` to skip),
   cover letter, form answers, interview prep, questions to ask, checklist. Memory decision → `preparing`.
3. Review the kit with the user: confirm every CV change and every form answer (salary, visa, notice period come from
   `profile.yaml → answers`; never guess them). Replace any `[placeholder]` with real facts.
4. Apply: `jobhunt prepare <job> --apply` or `jobhunt apply <job>` (see the `apply-job` skill). The user submits.
5. Afterwards: `jobhunt track add <job> applied`, `jobhunt memory decide <job> applied`,
   `jobhunt interview-prep <job>`, and `jobhunt track followups --days 7`.
