# Copilot instructions — job-hunt-agent

This repo is a Python CLI (`jobhunt`, source in `src/jobhunt/`) that acts as a personal job-hunt agent.
Agent skills live in `.github/skills/*/SKILL.md` — load the matching skill before acting. Full rules: `AGENTS.md`.

- Setup: `uv sync --all-extras && uv run playwright install chromium` (pip/venv is also supported; see README).
- Tests: `uv run pytest -q`  •  Lint: `uv run ruff check src tests`
- Personal data lives in `config/profile.yaml`, `config/sites.yaml`, `.env`, `me/` and `workspace/` (all git-ignored).
  Never commit them or print secrets/webhook URLs.
- Catalogs (skills, courses, principles, quiz and interview banks) are YAML in `src/jobhunt/data/`.
- New job sources: add a function `(site: dict) -> list[Job]` in `src/jobhunt/sources/` and register it in
  `SOURCES`; prefer official APIs, respect robots.txt/ToS, and add a mocked test in `tests/test_apply_sources.py`.
- Applying is human-in-the-loop: never submit an application or fabricate answers without the user's consent.
- CVs: markdown baseline in the house format (`examples/sample_cv.md`); never invent skills or inflate roles.
- Use `job-application` for a given job's CV and cover letter, with evidence and change review.
- For different people, use `--person <id>` on every command: profiles/CVs in `me/profiles/<id>/`,
  state and browser logins in `workspace/people/<id>/`. `--profile` alone does not isolate state.
  Fill explicit contacts with `cv-import --populate-profile` or `profile-from-cv`, then review them.
  Detailed workflow diagrams: `docs/workflows.md`.
