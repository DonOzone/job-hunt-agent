---
name: apply-job
description: Help the user apply to a specific job using the Playwright apply assistant and record it in the tracker. Use when asked to apply, fill an application form, or submit an application.
---

# Assisted application (human in the loop)

Rules: never submit without the user's explicit consent; never invent answers (experience, visa, salary);
never automate sites whose terms forbid it (LinkedIn, Indeed, Glassdoor) — tell the user to apply manually and
log it with `jobhunt track add <job> applied`.

1. Check fit first: `jobhunt fit <job-id-or-rank>` (gates + score). If a gate fails, tell the user why.
2. Prefer `jobhunt prepare <job>` (see `prepare-application`) so a tailored CV, cover letter and answers exist;
   upload the tailored `.docx` from `workspace/applications/<job>/` when the form asks for a CV.
3. Run `jobhunt apply <job-id-or-rank>`. A visible browser opens, profile fields + CV are pre-filled, a screenshot
   is saved to `workspace/screenshots/`, and the user is pinged with what still needs their input.
   Saved answers for recurring questions live in `profile.yaml` → `answers`.
4. The user reviews and submits, then confirms with `y` (or `s` to skip). `--auto-submit` only clicks submit when
   every required field is filled — use it only when the user asks.
5. After applying, the user is notified of the expected ATS flow and "room for growth" skills. Suggest
   `jobhunt interview-prep <job>` and set a reminder: `jobhunt track followups --days 7`.
6. MCP alternative: if the Playwright MCP server is available you may drive the form with `browser_*` tools,
   but still record every step with `jobhunt track add/update`.
