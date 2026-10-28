# Use job-hunt-agent with an AI platform

Claude Code, OpenAI Codex (using your ChatGPT account), Gemini CLI and GitHub Copilot
can run this project's commands through their local terminal tools. They do not
replace the Python CLI: install it once, then choose an assistant below.

**Ordinary web chat is not a local terminal.** Pasting a repository URL into
claude.ai, chatgpt.com or gemini.google.com does not install this project or grant
access to your computer. Use a terminal-capable agent, or run commands yourself
and share only redacted output. This project does not ship an MCP server, hosted
API, ChatGPT Action or browser-chat connector.

## 1. Install the project once

You need Git and [uv](https://docs.astral.sh/uv/getting-started/installation/).
Alternatively, use the [pip/venv instructions](../README.md#option-b--pip--venv).
These commands work in a terminal, including PowerShell:

```bash
git clone https://github.com/DonOzone/job-hunt-agent.git
cd job-hunt-agent
uv sync --all-extras
uv run jobhunt --help
uv run jobhunt init
uv run jobhunt cv-import "path/to/My CV.docx"
uv run jobhunt doctor
```

Replace the CV path with your own. Review `config/profile.yaml`: `init` copies
sample values, and importing a CV does not confirm your roles, work rights,
salary expectations or achievements. `doctor` reports missing setup; address
its findings before searching or preparing applications.

Only if you want browser sources or assisted application forms:

```bash
uv run playwright install chromium
```

For multiple people, start with a blank named profile instead of the default:

```bash
uv run jobhunt --person jane init
uv run jobhunt --person jane cv-import "path/to/Jane CV.docx" --populate-profile
# Review me/profiles/jane/profile.yaml before continuing.
uv run jobhunt --person jane doctor
```

Replace `jane` with your chosen ID and include `--person jane` on **every**
subsequent command. Selection is not remembered between commands.
`--profile` alone does not isolate jobs, tracking or browser sessions.

## 2. Choose a platform

### One-command skill setup

From the checkout, register the job-hunt skill with all four local agents:

```bash
uv run jobhunt agent-install
```

Or install only the integration you need:

```bash
uv run jobhunt agent-install claude
uv run jobhunt agent-install codex
uv run jobhunt agent-install gemini
uv run jobhunt agent-install copilot
```

| Platform | Project-local skill installed |
|---|---|
| Claude Code | `.claude/skills/job-hunt-agent/SKILL.md` |
| ChatGPT via Codex | `.agents/skills/job-hunt-agent/SKILL.md` |
| Gemini CLI | `.gemini/skills/job-hunt-agent/SKILL.md` |
| GitHub Copilot | `.github/skills/job-hunt-agent/SKILL.md` |

Restart the assistant in this folder after installation, then ask:
**"Use the job-hunt-agent skill to check my setup and find five jobs."**
Gemini users can check discovery with `/skills list`. The entry skill includes
the shared safety rules and routes requests to the existing workflow skills.
Some assistants also discover `.agents/skills`; seeing the same skill through
an alias does not require installing it again.

The installer adds only a generated `SKILL.md` to each selected location.
It does not change other skills, assistant settings, credentials or personal
files, and does not install the assistant application itself. Re-running is
safe: identical files are left unchanged. Existing unrelated skills and symlink
destinations are refused before any skill is written.

After updating the repository, refresh generated skills explicitly:

```bash
git pull
uv sync --all-extras
uv run jobhunt agent-install --update
```

`--update` replaces only skills bearing this installer's generated header;
it will not replace unrelated files. Generated skill folders are git-ignored.
To remove an integration, delete only its `job-hunt-agent` subfolder listed
above and restart the assistant. Copilot's original workflow skills remain
available in `.github/skills/`.

The project itself requires no AI account or model API key. Your chosen platform
has its own authentication, eligibility, usage limits and possible subscription
or API charges. Install only the assistant you want. For npm-based installation
below, use Node.js 22 LTS or newer and npm.

### Claude: Claude Code

Install using one of the native options:

```bash
# macOS with Homebrew
brew install --cask claude-code
```

```powershell
# Windows
winget install Anthropic.ClaudeCode
```

For Linux and other installation methods, follow the
[official Claude Code setup](https://code.claude.com/docs/en/setup).
Then, from your `job-hunt-agent` folder:

```bash
claude
```

Complete the prompted sign-in and review the folder trust/permission prompts.
Claude Code reads [`CLAUDE.md`](../CLAUDE.md), which imports the shared
[`AGENTS.md`](../AGENTS.md). The workflow skills remain in `.github/skills/`;
the instructions tell Claude to read the relevant file explicitly.

Try:

```text
Read AGENTS.md and the job-search skill. Run uv run jobhunt doctor.
If setup is ready, execute uv run jobhunt search --top 5, then
uv run jobhunt list. Summarise the actual results; do not notify or apply.
```

### ChatGPT: OpenAI Codex CLI

For local command execution with your ChatGPT account, use **Codex CLI**, not an
ordinary ChatGPT conversation:

```bash
npm install -g @openai/codex
# Run from the job-hunt-agent folder:
codex
```

Choose **Sign in with ChatGPT**, then complete authentication using an eligible
account/plan. API-key authentication is an alternative, not a requirement of
this project. See [Codex CLI setup](https://developers.openai.com/codex/cli/)
for current platform requirements and native installers.

Codex reads [`AGENTS.md`](../AGENTS.md) in this checkout. Keep approval/sandbox
controls enabled; approve a command's network access if you want it to fetch
public job postings.

Try:

```text
Read AGENTS.md and the cv-review skill. Execute uv run jobhunt doctor,
then uv run jobhunt cv-review --role "platform engineer" if setup is ready.
Show the generated draft paths and changes needing my factual confirmation.
Do not overwrite my baseline CV or invent experience.
```

Codex web/cloud sessions have a separate filesystem. Your local git-ignored CV,
profile, `.env` and workspace do not arrive there with the repository. Prefer a
local Codex session rather than committing or uploading those files.

### Gemini: Gemini CLI

```bash
npm install -g @google/gemini-cli
# Run from the job-hunt-agent folder:
gemini
```

Choose the authentication method offered for your account (Google sign-in,
Gemini API key or Vertex AI), and review the workspace trust and shell approval
prompts. Account availability can change: Google's
[Gemini CLI repository](https://github.com/google-gemini/gemini-cli) notes that
some users have transitioned to Antigravity CLI. If Gemini CLI is not offered
for your account, follow Google's current migration guidance; these instructions
describe Gemini CLI, not a tested Antigravity integration.
See the [official installation guide](https://geminicli.com/docs/get-started/installation/).

Gemini CLI reads [`GEMINI.md`](../GEMINI.md), which imports `AGENTS.md` and
directs it to read the matching `.github/skills/<skill>/SKILL.md`.

Try:

```text
Read AGENTS.md and the skill-ramp-up skill. Execute
uv run jobhunt ramp-up --skills "Kubernetes,Terraform" --free --hours-per-week 8.
Report the generated learning-plan path and suggest my first learning task.
Do not add unverified skills to my CV.
```

### GitHub Copilot: VS Code agent mode

1. Install [VS Code](https://code.visualstudio.com/) and enable GitHub Copilot
   using the [official setup guide](https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-extension).
   Sign in to GitHub with Copilot access.
2. Open the **local `job-hunt-agent` folder**, not just a file or GitHub webpage.
3. Open Copilot Chat and select **Agent** mode with terminal tools enabled.
   Ordinary Ask mode may explain commands without executing them.
4. Keep repository custom instructions enabled. Copilot uses
   [`.github/copilot-instructions.md`](../.github/copilot-instructions.md) and
   the workflows in [`.github/skills/`](../.github/skills/).
5. Send a prompt below and review each proposed terminal command before approval.

Try:

```text
Read AGENTS.md and the application-tracking skill. Execute
uv run jobhunt track list and uv run jobhunt track followups.
Summarise pending follow-ups from the actual output. Draft only; send nothing.
```

### GitHub Copilot: terminal CLI

```bash
npm install -g @github/copilot
# Run from the job-hunt-agent folder:
copilot
```

Use `/login` if prompted, authenticate to GitHub and review the folder trust
prompt. See the [official Copilot CLI quickstart](https://docs.github.com/en/copilot/get-started/cli-quickstart).
Use the same prompts as in VS Code and keep shell permissions approval-based.
This is the current `copilot` CLI, not the older `gh copilot suggest` workflow.

GitHub's cloud coding agent runs in a different checkout, without your local
git-ignored data. Use VS Code agent mode or Copilot CLI locally for personal
job hunting; do not put CVs, profiles or browser cookies into issues or PRs.

## 3. Ask for a workflow or an exact command

Start a new assistant session in the repository root. If instructions are not
loaded automatically, explicitly ask it to read `AGENTS.md` and the matching
skill file. Skills are Markdown workflows, not portable `/jobhunt` slash commands.

This prompt works across all four local agents:

```text
Read AGENTS.md and the matching skill before acting. Work from this repository's
root and use uv run jobhunt for every CLI call. Execute the commands with your
terminal tool, inspect the output and report failures. Ask before ambiguous
choices or external actions. Do not submit applications or send messages.
```

Then give a request; replace example IDs and paths with real values:

| Request | Commands the agent should execute |
|---|---|
| Check my setup | `uv run jobhunt doctor` |
| Find five jobs without notifications | `uv run jobhunt search --top 5`, then `uv run jobhunt list` |
| Add a saved posting and check fit | `uv run jobhunt add --file "posting.txt"`, then `uv run jobhunt fit <returned-job-id>` |
| Draft a CV and cover letter for job 2 | `uv run jobhunt application 2`, then inspect the generated evidence map and CV diff |
| Check drafts before sending | `uv run jobhunt research 2`, then `uv run jobhunt review 2` |
| Plan free learning | `uv run jobhunt ramp-up --skills "Kubernetes" --free` |
| Practise for job 2 in chat | `uv run jobhunt mock-interview 2 --list`; ask one question at a time |
| See application status | `uv run jobhunt track list` |

For a named person, say: **"Use `--person jane` on every command."** For example:

```bash
uv run jobhunt --person jane application 2
uv run jobhunt --person jane review 2
```

The agent must use IDs from the selected person's actual output. Do not assume
job rank 2 and tracker application ID 2 are the same entity.

**Interactive workflows:** run `pick`, quizzes and browser-assisted `apply` in
your own terminal if the agent cannot handle interactive input or a visible
browser. In chat, prefer `add --file` over `add --paste`, and the mock-interview
`--list` / `--rate` commands described in the [README](../README.md#mock-interviews-and-i-know--i-dont-know-flashcards).
Never turn on blanket auto-approval or `--auto-submit` to work around a blocked
agent tool.

## Privacy and troubleshooting

Local storage is not the same as local AI processing. CVs, profiles, answers,
command output and files read by an AI assistant may be sent to its provider.
Review that provider's data controls and explicitly consent before sharing.
If you want personal data to remain entirely on your machine, run the CLI
directly and do not share that data with a hosted assistant.

| Problem | Action |
|---|---|
| Agent only prints commands | Use a terminal-capable agent/mode and explicitly ask it to execute; approve the requested tool call |
| `uv` or `jobhunt` not found | Install uv and reopen the terminal; use `uv run jobhunt --help` in the checkout, or activate the pip venv |
| Windows: uv downloads fail with TLS `HandshakeFailure`, but pip works | Set uv's approved package index and, if needed, use Windows certificates; see the [known Windows proxy/TLS issue](../README.md#windows-package-proxy--tls-issue) |
| Different or missing profile/jobs | Check the working directory and `--person` flag on every call; cloud sessions do not share local files |
| Agent ignores skills | Ask it to read `AGENTS.md` and the exact `.github/skills/<name>/SKILL.md` file |
| Search cannot reach job APIs | Review the agent's sandbox/network approval; do not disable all safeguards |
| Browser cannot open | Install Chromium above and run assisted applying locally with a visible desktop |
| Assistant authentication fails | Use that platform's setup guide; job-hunt-agent does not manage model accounts or credentials |

See [all CLI commands](../README.md#6-all-commands) and
[the detailed job-application workflow](workflows.md) for the complete process.
