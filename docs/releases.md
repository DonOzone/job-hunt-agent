# Packaging and marketplace releases

## What this application is

`jobhunt` is a local Python CLI, with agent skills that orchestrate its commands.
It collects public job postings, ranks them against preferences and CV evidence,
creates application drafts, records progress, recommends learning and supports
interview practice. Word conversion and public API sources work without model
keys; PDF and browser support are optional dependencies. Generated fit scores
are heuristic, not hiring predictions. Drafts and extracted contacts need review.

The existing strengths are person-isolated state, truthful-document workflows,
human approval gates and bundled YAML catalogs. Previously, CI only tested source
and `agent-install` required a repository-shaped installation. A Python wheel
alone did not carry the agent workflows. These releases pair the workflows with
the runnable source without requiring a Git clone.

## Artifact formats

The [Marketplace release artifacts workflow](../.github/workflows/marketplace-release.yml) produces:

| File | Use |
|---|---|
| `job-hunt-agent-X.Y.Z-skill.zip` | Flat skill archive: `SKILL.md` at ZIP root, valid `name` and `description`, `references/` and `scripts/` |
| `job-hunt-agent-X.Y.Z-bundle.zip` | Same payload under one `job-hunt-agent/` folder, matching Agensi's published creator checklist |
| `job_hunt_agent-X.Y.Z-py3-none-any.whl` | Install the Python CLI with pip or uv; no agent workflow registration is included in the wheel |
| `job_hunt_agent-X.Y.Z.tar.gz` | Python source distribution for pip/build tooling |
| `SHA256SUMS` | SHA-256 checksums for all four distributions |

Both ZIPs contain the same text-only skill payload:

```text
SKILL.md
LICENSE
manifest.json
references/setup.md
scripts/app/
  AGENTS.md
  pyproject.toml
  uv.lock
  src/jobhunt/
  .github/skills/
  config/*.example.yaml
  docs/
  examples/                 # text examples only
```

The ZIP builder selects explicitly allowed repository files and honors Git's
ignored-file rules for untracked files. It does not zip the entire checkout.
Personal profiles, `.env`, CVs, browser sessions, workspace data, virtual
environments and compiled files are excluded. The public `.env.example` and
profile/site examples are deliberately included. Every payload file has a
manifest hash; ZIP entry ordering, line endings, permissions and timestamps
are normalized for reproducible skill archives. Wheels/source distributions
are independently built by setuptools; they are not claimed to be byte-identical
between operating systems.

## Install the downloaded artifacts

Extract either ZIP into a new, persistent, user-writable directory. For the
folder layout, enter its `job-hunt-agent` folder first. The application working
directory is always `scripts/app` inside the extracted skill:

```text
cd scripts/app
uv sync --locked
uv run jobhunt --help
uv run jobhunt --person candidate init
uv run jobhunt --person candidate doctor
uv run jobhunt agent-install
```

On Windows use `cd scripts\app`. Replace `candidate` with the confirmed person's
ID. Fill the blank profile and import the CV with consent before relying on
`doctor` or searching. Open the local assistant in the application directory
after `agent-install`, or install the whole outer skill folder in a host's skills
directory if it supports local scripts and references. See the bundled
[setup reference](../packaging/job-hunt-agent/references/setup.md).

The runtime still needs Python 3.10+ or uv and internet access for dependencies.
For PDF/browser features use `uv sync --locked --all-extras`; assisted forms
also need `uv run playwright install chromium`. No browsers or executables
are embedded. Agents must obtain consent for installation and personal-data
processing. No marketplace connector can grant local filesystem/terminal access.

For a wheel-only installation, create and activate a virtual environment, then:

```text
python -m pip install <downloaded-wheel.whl>
jobhunt --person candidate init
```

Optional wheel extras can be installed using pip's `<wheel-path>[all]` syntax.
Run wheel-installed commands from a dedicated data directory. `agent-install`
needs the repository-shaped runtime in the ZIP, not just a wheel installation.
For a source distribution use `python -m pip install <downloaded-source.tar.gz>`.

Updates must not overwrite existing personal folders. Extract a new version
separately, back up personal data locally and migrate intentionally. `JOBHUNT_HOME`
relocates workspace state only; it does not relocate profiles and CVs.

## Version control and GitHub Actions

Use stable `X.Y.Z` versions. Keep `pyproject.toml` and
`src/jobhunt/__init__.py` in sync, run `uv lock`, and commit the version/lock
changes with the implementation. The builder rejects mismatched source versions
and rejects tags or explicitly requested versions that differ from the source.

For a release, push an annotated tag on the reviewed release commit:

```text
git tag -a v0.1.0 -m "Release 0.1.0"
git push origin v0.1.0
```

Use the actual next version, not an existing tag. A `v*` tag starts the workflow:
Windows and Linux build distributions, check the skill frontmatter/manifests,
install the wheel in an isolated environment, extract and install both ZIPs,
initialize a blank test person and register all four local-agent integrations.
The full Python/browser suite also gates publishing. Only after all jobs pass
does the workflow create a GitHub Release with directly downloadable assets.
Write permission is limited to the publishing job. It does not push tags, upload
to PyPI, publish to Agensi or modify an existing release.

The existing `.github/workflows/release.yml` remains the unsigned desktop/Python
app pipeline; marketplace packaging is a separate workflow. It builds the React
UI before Python distributions and retains the existing distribution privacy/UI
checks. The skill ZIPs expose the CLI workflow, not a complete web/native app
installer. Desktop delivery remains managed by the existing app workflow.
Releases created with GitHub's workflow token do not automatically trigger other
release-event workflows; run the desktop workflow manually when needed.

For artifacts without a release, use **Actions > Marketplace release artifacts > Run workflow**.
Select the branch/tag containing the intended source, optionally enter the
expected version, and run. A branch run uploads versioned workflow artifacts
retained for 30 days; it does not create a tag or GitHub Release. A selected tag
also takes the release path. The version input validates source; it does not
rewrite version files. PRs affecting packaging inputs build downloadable
preview artifacts without publishing.

Local equivalent, from the repository root:

```text
uv run ruff check src tests tools
uv run pytest -q tests/test_release_packaging.py
npm ci
npm run build
uv build
uv run python scripts/check-distributions.py dist
uv run python tools/build_release.py --expected-version 0.1.0
uv run python tools/smoke_release.py
```

If a managed machine cannot fetch the locked dependencies through uv, the
documented pip environment is also supported: install `".[dev,all]"` and
`build` into a virtual environment, run `python -m build --installer pip`,
then run the builder and `python tools/smoke_release.py --installer pip`.
This checks pip installation, not reproduction of the locked uv environment;
CI still checks the locked uv path. Do not disable TLS verification.

Use a clean `dist` directory containing only the current version's outputs.
The smoke check deliberately fails on extra wheels/ZIPs rather than guessing.
The local builder includes allowed, non-ignored untracked inputs so new packaging
files can be checked before committing. CI builds from the selected Git ref.
GitHub's workflow artifact download is an outer transport ZIP; unpack it and
submit the inner `*-skill.zip` or `*-bundle.zip`, not that transport wrapper.

## Marketplace submission and remaining improvements

[Agensi's selling guide](https://www.agensi.io/sell) describes creator ZIP upload,
security scans and human review. Its
[creator checklist](https://www.agensi.io/learn/skill-md-creator-checklist)
specifies a single top-level folder with `SKILL.md` immediately inside it; use
`*-bundle.zip` there. Use `*-skill.zip` where the receiving skills repository or
marketplace requires `SKILL.md` at ZIP root. Both have the same workflows/runtime.

Submission stays manual. Declare that this skill executes a local Python CLI,
downloads dependencies and optionally a browser, reads personal CV/profile data,
uses public job APIs and can send explicitly configured notifications. State the
required local terminal permissions and human approval gates in the listing.
Do not promise offline installation, an MCP server, universal agent support or
automatic application submission.

Authenticated upload limits and whether Agensi's MCP delivery exposes executable
supporting files have not been verified. Its public pages say buyers load skills
through MCP rather than downloading them. A ZIP that passes our checks is not
evidence of marketplace approval or runtime compatibility. Confirm these details
with the marketplace before listing a local-runtime product.

Prioritized follow-up work, not included in this packaging change:

| Priority | Improvement | Why |
|---|---|---|
| First | Test discovery and a synthetic job workflow in at least two actual agent hosts | CLI/install smoke checks do not prove natural-language triggering or host compatibility |
| First | Verify marketplace file delivery, dependency-install policy and upload limits | Instructions-only delivery cannot run bundled Python by itself |
| Next | Separate user data from installation with an explicit data-root option and migration support | Current relative paths make skill updates easy to misuse |
| Next | Add machine-readable command outputs and stable error contracts | Agents currently interpret human-oriented terminal output |
| Later | Dependency review, SBOM/provenance and signed artifacts | Improve supply-chain transparency beyond checksums |
| Optional | OS-native executable installers or a separately designed MCP service | Different products with browser/dependency/privacy lifecycle costs |
