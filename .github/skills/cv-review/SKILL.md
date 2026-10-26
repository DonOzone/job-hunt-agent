---
name: cv-review
description: Review, reword and tailor the user's CV for a specific job or role, and import/export it in the house Word format. Use when asked to improve, update, tailor, review or rewrite a CV/resume, or to convert it to/from Word.
---

# CV review & rewrite

**Honesty rules (non-negotiable)**
- Never add a skill, tool, employer, title, date or number the user has not confirmed. Missing keywords go in the
  report as "add only if true".
- Never inflate scope: "contributed to" / "helped" must NOT become "led" / "owned". Ask what the user actually did.
- Keep "Label: text" bullets and the user's own strong summary; suggest, don't overwrite.

**Format** (see `examples/sample_cv.md`): `# NAME`, `**Headline**`, contact line, `## SECTION` (uppercase),
`### EMPLOYER | City`, `_Role | Dates_`, optional `#### Area`, `- bullets`. HTML comments are notes, never exported.

1. Baseline: if `cv_path` isn't a `.md`, run `jobhunt cv-import "<file.docx|pdf>"` (sets `cv_path`, keeps original).
   `jobhunt doctor` shows format issues (e.g. unfilled `[placeholders]`).
2. Review for a target: `jobhunt cv-review <job-rank-or-id>` or `jobhunt cv-review --role "platform engineer"`
   (`--mine` = only jobs the user added). Outputs in `workspace/cv-review/`: report, draft `.md`, draft `.docx`.
3. Walk the user through the report in this order: ATS score → missing keywords (ask: "do you have X?") → buried
   skills to surface → weak bullets → bullets needing a number (ask for the real figure).
4. Apply only the confirmed changes to a copy (e.g. `me/cv/<company>.md`), keep ≤ 2 pages (≤ 1 page for < 5 yrs),
   then `jobhunt cv-export me/cv/<company>.md` (`--a4` outside North America).
5. Log what changed: `jobhunt journal log "CV tailored for <job>: ..." --kind progress`.
