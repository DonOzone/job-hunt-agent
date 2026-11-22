# Local runtime setup

Use a persistent, user-writable location for the skill and its supporting
files. Ask before installing dependencies or creating personal data.
The bundled application is readable Python source, not an executable, hosted
service or MCP server. No administrator privileges or Git checkout are needed.
Python dependencies require internet access to install.

From this skill's `scripts/app/` directory:

```text
uv sync --locked
uv run jobhunt --help
uv run jobhunt --person candidate init
uv run jobhunt --person candidate doctor
```

Replace `candidate` with the confirmed person's ID. New named profiles are
blank; `doctor` failing until contacts/preferences are filled is expected.
With consent, run `uv run jobhunt --person candidate cv-import "<CV>" --populate-profile`,
then review extracted contacts, target roles, work rights and preferences.
Keep `--person candidate` on every subsequent command.

Use Python 3.10+ and `python -m venv .venv` followed by
`python -m pip install .` in the activated environment if uv is unavailable.
On Windows activate `.venv\Scripts\Activate.ps1`; on macOS/Linux use
`. .venv/bin/activate`. Then use `jobhunt` instead of `uv run jobhunt`.

Only for PDF input or the assisted browser:

```text
uv sync --locked --all-extras
uv run playwright install chromium
```

For pip, install `".[all]"` and run `playwright install chromium`.
Browser installation downloads a browser separately; it is not in the ZIP.
Keep the user's application review and submission approvals enabled.

`config/`, `me/` and `workspace/` are relative to the application root.
`JOBHUNT_HOME` relocates workspace state only, not profiles or CVs. Never run
from an unrelated project. Never share this installation's personal folders.
Do not overwrite this folder with an update: back up personal data locally
and migrate it intentionally to the new version.

For project-local discovery by Claude Code, Codex, Gemini CLI or Copilot, run
`uv run jobhunt agent-install <platform>` from the application root and open
the assistant there. It installs only an entry skill, not an assistant or
model credentials. See `scripts/app/docs/platforms.md` relative to the outer
skill for full instructions. If a marketplace only streams SKILL.md and
does not expose supporting files, use the downloadable local release first;
MCP connectivity alone does not grant access to a local terminal or runtime.
