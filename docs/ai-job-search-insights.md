# Ideas adopted from ai-job-search

[ai-job-search](https://github.com/ai-job-search-dev/ai-job-search) is a Claude Code framework for job applications.
It is MIT-licensed; we re-implemented (not copied) the ideas that fit a local Python CLI. Credit to its authors.

| ai-job-search | Here | Status |
|---|---|---|
| `tools/posting_guard.py` - strip hidden text / prompt injection from postings | `guard.py`, used by `add`, `fit`, `prepare` | ✅ |
| Fit evaluation with hard gates (eligibility, language, logistics) | `fit.py`, `jobhunt fit` | ✅ |
| Seen-jobs state / dedupe across runs | `memory.py` (`reviewed-jobs`), `store.py` | ✅ |
| Add a posting you found yourself | `jobhunt add <url> [--paste/--file]` | ✅ |
| `/apply` - CV + cover letter + forms per job | `jobhunt prepare` application kit | ✅ |
| `application-reviewer` agent - hiring-manager critique grounded in the profile | `review.py`, `jobhunt review`, `application-review` skill | ✅ new |
| `09-web-research` + company research cache | `research.py`, `jobhunt research` (cached per company) | ✅ new |
| `/outcome followup` - drafts for quiet applications | `jobhunt track followups` + `track sent` | ✅ new |
| `/outcome stale` - sweep 60+ day silence | `jobhunt track sweep` | ✅ new |
| `/html-report` - funnel dashboard from history | `jobhunt track dashboard` | ✅ new |
| `/upskill` - gaps weighted by how much you want each job | `gaps.decision_weights` | ✅ new |
| `03-writing-style` - tone, clichés, forward-looking letters | `data/writing_style.yaml`, profile `writing_style`, cover-letter template | ✅ new |
| `tools/robots_check.py` | `sources/robots.py` (posting fetch + browser source) | ✅ new |
| Portal CLIs for Danish job boards (Jobindex, Jobnet...) | Not adopted - region-specific; add as a source if you need them | ➖ |
| LinkedIn search CLI | Not adopted - LinkedIn's terms forbid scraping; use `add --paste` | ➖ |
| Gmail / Notion sync | Not adopted yet - needs OAuth credentials; candidates for a future optional extra | 🔜 |
| `/expand` - competencies from diplomas, references, GitHub | Partly: `cv-import`; GitHub/diploma scan is a future idea | 🔜 |
| LaTeX CV/cover-letter templates, salary Excel tool | Not adopted - we use the Word house format (`cv-export`) | ➖ |
