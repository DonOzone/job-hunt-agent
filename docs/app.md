# Web, installed desktop and mobile

These clients add a **single-host pilot** dashboard to the existing CLI. They share
the Python API and per-user ownership checks, but do not import your existing
`me/`, `workspace/` or mailbox. CLI subscription/assistant workflows remain separate.
Jobs and short-term projects use the same matching, draft and application flow.

The existing CLI also supports projects without using a different application pipeline:

```console
uv run jobhunt search --opportunity-type project
uv run jobhunt add --file examples/project-posting.txt --opportunity-type project --duration "6 weeks"
```

Replace `examples/project-posting.txt` with your own locally saved posting; no
sample posting file is supplied. Project classification and duration survive
imports. `daily --opportunity-type project` uses the same pipeline but can send
configured notifications; prefer `search` for search-only requests. For a named
person, include `--person <id>` on every CLI command.

## Native launch on Windows, macOS and Linux

Requirements: Python 3.10+ (3.12 recommended), Node 22+, npm and optionally uv.
Run these commands from the repository root:

```console
uv sync --extra web --extra docs
npm ci
npm run build
uv run --extra web --extra docs python -m jobhunt.web --host 127.0.0.1 --port 8650
```

Set `JOBHUNT_WEB_SECRET` to a stable, randomly generated secret **before** starting
the backend. Store it securely outside version control; keep it unchanged across
restarts so encrypted provider credentials remain decryptable. Generate a value locally:

```console
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

PowerShell sets an environment variable with `$env:JOBHUNT_WEB_SECRET = '<secret>'`;
macOS/Linux shells use `export JOBHUNT_WEB_SECRET='<secret>'`. Do not paste secrets
into issues, commits or shared logs.

Without uv, create a virtual environment and install the editable project:

```console
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[web,docs]"
npm ci
npm run build
npm run backend -- --host 127.0.0.1 --port 8650
```

macOS/Linux:

```sh
.venv/bin/python -m pip install -e ".[web,docs]"
npm ci
npm run build
npm run backend -- --host 127.0.0.1 --port 8650
```

The npm launch helper uses `JOBHUNT_PYTHON` if set, an existing `.venv` interpreter,
then uv if available, then `python3`/`python`. The fallback interpreter must already
have this project and its web/docs extras installed. It does not install system
packages or request administrator permissions.

Open `http://127.0.0.1:8650`. The backend serves packaged web assets and its API on
the same origin. For web development, run `npm run dev` in a second terminal;
the API remains on port 8650. `npm run build` also copies assets into the Python
package so a built wheel serves the UI without Node installed.

Use `--data-dir <directory>` or `JOBHUNT_WEB_HOME` for an isolated server data
directory on a local persistent disk. Do not point it at the CLI's personal files.
Keep the secret and data directory stable across restarts.
The local durable-run worker is enabled by default in native and container
launches. `--no-worker` is a diagnostic/server-only option: queued searches and
optional API text-generation runs will not progress without a worker. Do not
deploy multiple backend/worker replicas against the pilot SQLite disk.

## Installed desktop

```console
npm run desktop
npm run desktop:build
```

Electron packages the React web UI; this is **not** React Native desktop and
**does not bundle Python**. Install/run the backend separately as above, use
Docker, or connect to your own HTTPS backend in the client settings. Backend
availability is required for all dashboard actions.

Desktop resources are served on `http://127.0.0.1:5174` to avoid `file://` null-origin
CORS. That port must be free. Node integration is disabled, context isolation
and sandboxing are enabled, permissions are denied except sanitized clipboard
text writes from the packaged UI for handoff copying, webviews are blocked,
navigation stays on the UI origin, and only validated HTTP(S) links may open in
the system browser. CSP permits API connections over HTTPS or HTTP loopback;
use HTTPS for a desktop connection to another computer.
See the [Electron security checklist](https://www.electronjs.org/docs/latest/tutorial/security).

Local packaging creates platform-specific files in `apps/desktop/release/`:
Windows NSIS `.exe`, macOS `.dmg`/`.zip`, Linux `.AppImage`/`.deb`. Build on the
matching OS; the release workflow uses a three-platform matrix. Outputs are
unsigned engineering builds, not a claim of store distribution or trusted signing.
Do not bypass OS trust warnings. Production distribution needs independently
configured signing/notarization credentials and verification; none are included.

## React Native mobile

```console
npm run mobile
npm run mobile:export
```

The Expo client includes account registration/login, a progress dashboard,
public-source search, pasted job/project creation and tracking, application
status/next actions and drafts, pasted received email feedback, manual task
handoff/copy/result completion, learning goals, cards/reveal/answer, background
runs, profile editing and optional AI-provider configuration.

An actual phone's `127.0.0.1` is the phone, not your computer. For trusted local
development, bind the backend to `--host 0.0.0.0` and enter your computer's private
LAN IP on port 8650, checking firewall rules. HTTP is permitted only for loopback
or private development LAN addresses by the client. **Use HTTPS outside trusted
development networks.** Platform network policies can additionally reject cleartext
HTTP in installed builds; use an HTTPS backend for release builds.
Add that LAN IP to `JOBHUNT_WEB_HOSTS` for backend Host-header validation. For a
hosted API, configure its hostname in `JOBHUNT_WEB_HOSTS` and the exact authorized
HTTPS browser app origins in `JOBHUNT_WEB_ORIGINS`.
Binding to a non-loopback interface requires a stable secret and explicit
Host/origin configuration at startup. Browser origins are not API hostnames:
origins include scheme and port; Hosts are comma-separated hostname/IP entries.
Keep `localhost,127.0.0.1` in the Host list so local health checks remain valid.
Native bearer requests need no fabricated browser Origin header.

Authentication uses opaque bearer tokens stored using Expo SecureStore, not
AsyncStorage or browser localStorage. Applying a changed server address clears
the session; sign in separately at the new server. Tokens are never exported in
the dashboard. See [SecureStore](https://docs.expo.dev/versions/latest/sdk/securestore/).
Clipboard handoff intentionally copies selected feedback/job information: review
it first, and consider clearing your clipboard after use.

Expo `export` creates JS/assets, **not an installable APK/IPA**. For native local
builds use `npm run android --workspace @jobhunt/mobile` with Android Studio/JDK,
or `npm run ios --workspace @jobhunt/mobile` on macOS with Xcode. EAS profiles
are provided in `apps/mobile/eas.json`; from that directory, an account owner may
run `npx eas-cli build --profile preview --platform android` or the production
profile for Android/iOS after configuring their Expo project and credentials.
EAS accounts, signing, store membership and submission are user-owned; no builds,
signing operations or uploads have been performed by this implementation.

Pinned native compatibility: Expo 58.0.22's bundled module list specifies
React 19.3.0, React Native 0.88.1, SecureStore ~58.0.2, Clipboard ~58.0.4 and
safe-area-context ~5.10.1. The web workspace can independently use React 19.2.
Electron is pinned to stable 42.11.18 rather than the registry's prerelease tag.

## Feedback, assistants and API consent

There is no mailbox OAuth or automatic inbox read/send. Paste received feedback;
the web client also imports supported `.eml`/`.txt` files. Select an application,
create a handoff task, inspect its prompt, and copy it to an official assistant
where you are already authorized/logged in. Paste and review its result, then
explicitly mark the task completed. This is a manual interchange, not an agent
runtime, autonomous assistant invocation or application submission.

Received emails/postings are untrusted data and cannot authorize tool use.
Drafts are unverified templates; check every fact, role and skill against your
confirmed CV. Neither matching scores nor AI drafts verify visa/work eligibility.

Optional OpenAI/Anthropic/Gemini API keys are sent only to your configured
backend for encrypted storage and are never returned to clients. API generation
is opt-in per request, requires confirmation of outbound data, and generates
text only. No automatic fallback provider, autonomous code execution, browser
submission, email sending or mailbox integration is included.
Clients first retrieve `/api/ai/preview`, show its exact prompt and provider/model,
then send the approved snapshot's `preview_digest` with explicit consent. A
changed prompt or provider connection requires a fresh preview rather than
silently reusing old consent.

## Docker and persistent state

```console
docker compose up --build -d
docker compose logs --tail=50
docker compose down
```

Set `JOBHUNT_WEB_SECRET` before `up`; Compose refuses to start without it.
The image supplies explicit local-development Host/origin defaults; override
them with your API hostname and exact HTTPS app origins for a hosted service.
The image builds React in a Node stage, then installs Python `.[web,docs]` and
packaged assets into a non-root runtime. Its allowlisted build context excludes
personal config, `.env`, `me/`, `workspace/`, documentation other than the public
README, git and node_modules. No developer CVs or credentials enter the image.

Compose exposes the backend on host loopback only and persists state in the
`jobhunt-data` named volume. `down` preserves it; **`down --volumes` deletes data**.
Back up the persistent disk/database and securely preserve the encryption secret.
Use SQLite's online backup API or stop the service for a consistent backup;
copying only the active database while WAL writes continue is not a safe backup.
Validate restoration, including encrypted provider settings, before production.

## CI, release, registry and optional deployment

* `ci.yml` retains Python tests/ruff, adds all workspace checks, web packaging,
  mobile exports, a Python wheel/source distribution and a no-push Docker build.
  Python tests include the authenticated backend and install `dev,browser,web,docs`
  extras. Workspace checks typecheck web/mobile/client and run desktop security
  checks. Distribution checks reject private state/credential paths and require
  the built React entrypoint before uploading Python artifacts. CI uses `pip`
  and the npm lockfile; it does not require a regenerated/frozen `uv.lock`.
* `release.yml` builds unsigned desktop artifacts on Windows/macOS/Linux and
  Python distributions with built UI on a published release or manual invocation.
  Artifacts are downloadable from the workflow run; the workflow does not publish
  to PyPI/app stores or attach signed installers to releases.
* `container.yml` builds and pushes to GHCR on main/release or manual invocation
  using repository-scoped package permissions; pull requests cannot publish.
  Configure repository package visibility/access before distributing an image.
* `deploy.yml` is manual and targets **your explicitly configured Linux Docker
  host**, not an assumed cloud service. Configure the protected `production`
  environment, approval rules, and secrets `DEPLOY_HOST`, `DEPLOY_USER`,
  `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS` (verified known-host entry). The host must
  already have Docker, curl, a dedicated deployment account allowed to manage
  containers, and `/etc/jobhunt/backend.env` containing the stable backend secret,
  origins and secure-cookie setting. Supply a public GHCR image pinned by digest.
  Include `JOBHUNT_WEB_HOSTS` with `localhost,127.0.0.1` and the API hostname in
  that server environment file.
  Private registry authentication must be provisioned on the host separately.
  Deploy replaces one named container while preserving its named volume, then
  checks health. There is brief downtime, no rolling deployment or automatic
  rollback; retain the prior digest and backups for operator-controlled recovery.

GitHub Actions/Pages do not themselves host this Python API. Pages can serve
static sites, but the authenticated backend needs a persistent server elsewhere.
No cloud deployment or signing has been executed.

## Public-production limitations

This is a local/single-host pilot, **not a production-ready multi-tenant SaaS**.
SQLite WAL and the durable run queue require one persistent local disk and one
backend instance/local worker. Do not use multiple replicas, NFS or ephemeral
container disks; PostgreSQL/distributed queues are not implemented.

Before exposing it publicly, operators must provide TLS/reverse proxy, exact
`JOBHUNT_WEB_ORIGINS`, `JOBHUNT_WEB_SECURE_COOKIES=1`, verified-email and password
reset/recovery flows, ingress/body limits, rate limiting/abuse protection,
monitoring, security review, consistent backups and tested recovery. Secure
cookies require HTTPS. Keep port 8650 behind the proxy and limit administrative
access. Desktop/mobile signing, licensing/store policies and dependency updates
are separate release responsibilities. Do not advertise autoscaling, inbox
automation or autonomous applying.
