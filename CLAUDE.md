# Claude Code - job-hunt-agent

Read @AGENTS.md before executing commands or editing files. It is the shared source
of truth for safety rules, person isolation, command execution and skill selection.

For each request, read the matching `.github/skills/<skill>/SKILL.md` from the
table in `AGENTS.md`; these are workflow instructions, not installed slash commands.
Use the terminal tool to run `uv run jobhunt ...` from this repository's root,
inspect the actual result and report failures rather than claiming success.

Installation, authentication and example prompts: [docs/platforms.md](docs/platforms.md).
