# How to use each feature and interpret its output

[Setup](../README.md#1-quick-start-10-minutes) | [Workflow diagrams](workflows.md)

Run commands from your checkout. Below, `J` is a **job rank or ID**, `A` is an **application tracker ID**,
and `KIT` is the application folder printed by the CLI. Replace those tokens; do not type them literally.
Every example uses `uv run jobhunt --person jane`; keep the same person on every command, or omit `--person jane`
everywhere for the original single-user setup. Pip users can replace `uv run jobhunt` with `jobhunt` after activation.

Named people's generated files live under `workspace/people/jane/` (called **HOME** below).
The original single-user HOME is `workspace/`. `JOBHUNT_HOME` changes that root.
Profile settings live in `me/profiles/jane/profile.yaml`; default single-user settings in `config/profile.yaml`.
No personal data is committed by these commands.

## Setup and people

| Command after `uv run jobhunt --person jane` | Output / feedback | What you do next |
|---|---|---|
| `init` | Creates profile, sites and optional `.env`; prints created/existing files and HOME | Edit settings; init never overwrites existing files |
| `cv-import "My CV.docx" --populate-profile` | Baseline Markdown in `me/profiles/jane/cv/`, original retained, contact extraction and format warnings | Review extracted contacts and fill roles, regions, languages, work rights, salary and answers |
| `profile-from-cv "My CV.docx"` | Fills empty explicit contact fields; reports conflicting nonempty values it kept | Review fields; the input file stays in place |
| `profiles` | Lists local person IDs (no contact details) | Select explicitly on each invocation; there is no sticky active person |
| `doctor` | Pass/warning/error checklist: profile, CV, roles, regions, work rights, browser dependencies, sites and workspace | Resolve errors; read warnings before live search/apply |
| `cv-export` | Word copy of baseline, plus format warnings | Review Word layout before use |

`init` is safe to repeat. A default repository profile contains fictional sample data: **replace it**, including
sample achievements/answers, or use a blank named profile. CV extraction does not replace nonempty sample values.
OCR for scanned CVs is not built in; extract text first. Never infer work rights from name, address or nationality.
Named profiles do not inherit shared notification destinations. Configure `notify` in that person's profile.

## Discover, rank and remember

| Command | Output / feedback | Next action |
|---|---|---|
| `daily` | Search/filter counts, new jobs, ranked results, gaps, study plan, interview packs, insights and optional notification | Read `HOME/ranked-jobs.md`, shortlist and check fit |
| `search` | Collects sites; `HOME/jobs.json` and `ranked-jobs.md`; per-source failures are warnings | Check `--no-filter` if too few results; fix failing board tokens in sites.yaml |
| `import saved-jobs.csv` | Imports saved CSV/JSON jobs and ranks them | Use `list` and `show J` |
| `add URL` or `add --file posting.txt --title "Role" --company "Company"` | Archives manual job in memory; prints fit, integrity flags and job ID/rank | Use `fit J`; login-wall or prohibited sites require pasted/saved text |
| `rank`, `list`, `show J` | Region/remote/relocation/package/CV-match ordering and full job details | Confirm actual pay, work rights and preferences; missing salary is not an offer |
| `memory list`, `memory show J` | Reviewed jobs, decisions, notes and generated output paths | Record `memory decide J shortlist` or `skip`; skip/closed affects search and gap ranking |
| `memory note J "Recruiter feedback"` | Timestamped note in `HOME/memory/` | Reuse feedback in later applications |
| `cv-match`, `fit J`, `eligibility J` | Skill match; fit gates/logistics; proficiency-informed readiness | Resolve blockers or explain legitimate exceptions; these are heuristics, not hiring guarantees |

Search adapters depend on third-party availability. Passing tests validates mocked API handling, not today's
availability of every external career site. Respect site terms, robots.txt and login requirements.

## CV, cover letter and application

| Command | Output / feedback | Next action |
|---|---|---|
| `cv-review J` (or `--role "Backend Engineer"`) | `HOME/cv-review/` report and CV draft; timestamped versions in `cv-versions/`; keyword coverage, wording checks and missing skills | Confirm facts; never insert unsupported keywords just to increase the score |
| `tailor J` | `HOME/tailoring/` suggestions and companion letter draft | Personalise and verify; use `application J` for the full paired-document workflow |
| `application J` / `prepare J` | `HOME/applications/<job>/`: posting, fit, requirement evidence, CV change diff, CV and letter Markdown/Word drafts, form answers, interview prep, checklist and review | Read every requirement; edit drafts and save approved files under final names |
| `research J` | `HOME/company-research/<company>.md`, reused across this person's applications | Write sourced facts in at least two sections; the command supplies a research template, not verified company facts |
| `review J` | `KIT/review.md`, score and blocker/fix/tip findings, preferring final Markdown files if present | Remove placeholders; resolve unsupported claims and material warnings |
| `cv-export KIT/cv-final.md --out KIT/cv-final.docx` | Final Word CV | Inspect it; Markdown edits do not automatically update Word files |
| `apply J --cv KIT/cv-final.docx` | Visible browser, known fields filled, selected CV uploaded, screenshot, missing required fields, tracker history and notification | Supply cover letter manually where requested; review and submit yourself |
| `apply J --dry-run` | Records a dry run without opening/submitting a form | This is not a submitted application |

Fresh drafts intentionally contain placeholders and may score poorly until personalised. A generated kit is
**not** application-ready by default. No CV baseline is changed by tailoring. Repeating `application` regenerates
drafts; preserve approved edits as `cv-final.md` and `cover-letter-final.md`.
Word files are snapshots; finalise the cover letter in Word or paste approved text into the application.
Without `apply --cv`, the baseline is used. Headless/auto-submit is opt-in, not the default.
The automated reviewer is a heuristic quality check, not complete factual verification.

## Ramp-up, study and learning feedback

| Command | Output / feedback | Next action |
|---|---|---|
| `gaps` | `HOME/skill-gaps.md`: weighted missing skills, frequency and course links | Prioritise important gaps for shortlisted/applied jobs |
| `study-plan --hours 6` | `HOME/study-plan.md`: sequential weeks, build tasks and assessment check-ins | Schedule realistic time and log evidence |
| `ramp-up --free --hours-per-week 8` | `HOME/ramp-up.md`: own list first, curated/open material, proof project, check-in dates | Learn and build; links are suggestions, not proof of competence |
| `ramp-up --skills "Python,SQL" --resources my-list.yaml` | Same output for named skills, even without saved jobs | `--with-gaps` also appends gaps; invalid resource rows/hours are reported rather than ignored |
| `ramp-up log Python --hours 3 --note "Built a CLI"` | Timestamped learning journal entry | Evaluate the skill and add it to the CV only with real evidence |
| `assess Python` (or `--self`) | Quiz feedback or structured self-rating, score/level and saved assessment | Treat self-ratings as self-reported; use real projects/interviews to validate readiness |
| `journal log "What I learned" --kind learning`, `journal show` | `HOME/journal.md` and `.jsonl`, timestamps and tags | Review progress weekly |
| `insights` | Strategy advice based on current activity and application outcomes | Pick a practical change to try; no success-rate guarantees |

Own resources: `me/profiles/jane/learning-resources.yaml` or `.csv` / `.md`.
Copy `examples/learning-resources.example.yaml`, or use `Skill | Title | URL | hours` text rows.
Paid/free status is not guaranteed: platforms can change access rules; audit tracks, certificates, labs and trials
may have different costs. `--free` hides known paid entries, but unknown-cost personal entries remain visible.
Invalid lists are errors; repair them rather than assuming every supplied row was accepted.

## Interview prep and confidence ratings

| Command | Output / feedback | Next action |
|---|---|---|
| `interview-prep J` | `HOME/interview-prep/`: research checklist, role-specific technical/behavioural prompts, senior design prompts, STAR stories and practice schedule | Rehearse honest examples and company research |
| `mock-interview J --list` | `HOME/mock-interviews/<job-id>/practice.md`: question types, revealable flashcards, counts and unknown-topic resources | Use card IDs to record explicit user ratings or start an interactive session |
| `mock-interview --application A` | Resolves the tracked application to its saved posting; asks one question at a time | Answer, reveal the answer/guide, choose **I know [k]** / **I don't know [d]**, **q** to stop |
| `mock-interview J --mode flashcards` | Reveal before rating; no spoken/free-text answer required | Rate honestly, then study unknown topics |
| `mock-interview J --rate CARD --rating dont-know` | Timestamped event in `ratings.jsonl`, journal feedback and refreshed report | Review personal resources plus curated links, YouTube and LinkedIn Learning |
| `mock-interview J --rate CARD --rating know --answer "My answer"` | Latest rating changes; prior ratings/answers are preserved locally | Rehearse again later |
| `mock-interview J --weak-only --limit 5` | Practises only cards last rated unknown | No weak cards does not mean all unrated cards are mastered |

Question types are technical, knowledge, behavioural/STAR, company, and senior system-design/leadership.
Knowledge checks use curated answers; open-ended prompts have **answer guides, not automatic correctness grading**.
The chat skill can coach structure, specificity and evidence, but self-ratings only measure confidence.
Ratings do not modify CVs, skill-assessment scores, eligibility or application stage. Nothing automatically rates
external courses: ratings attach to interview learning elements/cards, with resource suggestions for weak topics.
The original posting must still be available in saved/manual jobs for application-ID lookup.

## Tracking and outcomes

| Command | Output / feedback | Next action |
|---|---|---|
| `track list`, `track history A`, `track report` | Current statuses, timestamped events and `HOME/applications-report.md` | Record real progress, failure reasons and next actions |
| `track update A interview --note "Recruiter screen passed" --next "Practise" --due 1` | Status/event and dated next action | Prepare and follow the reminder |
| `track followups` | Drafts in `HOME/followups/` for eligible quiet applications | Review and send manually; drafts are not sent automatically |
| `track sent A` | Logs that **you** sent a follow-up; resets quiet-period counting | Wait an appropriate period; track later responses |
| `track sweep` | Lists/optionally closes applications silent for 60 days by default | Confirm closures; `--days N` changes the threshold, `-y` skips confirmation |
| `track dashboard` | `HOME/dashboard.html`: funnel, weekly/source/status counts and quiet days | Open the HTML file in a browser; inspect and adapt your strategy |

For manual submissions use `track add J applied` **or** update an existing application ID. Do not double-log.
The dashboard is a local static page, not a hosted web app. Notifications only work after you configure them.
The current sweep implementation closes by quiet days, not simply because two follow-ups were sent.

## Verification and remaining external actions

CI is enabled in `.github/workflows/ci.yml`: Python 3.10/3.12, lint and tests including a local browser form.
Repeat locally:

```bash
uv sync --frozen --all-extras
uv run --frozen ruff check src tests
uv run --frozen pytest -q -rs
uv build
```

The tests cover search/filter/ranking, CV import/export and integrity, paired documents, person isolation,
learning plans, tracking/follow-ups/dashboard, mock interview ratings, and a local Playwright form.
They do **not** prove every live ATS form/API, notification account, external course link or employer process works.
Real applications still require profile review, credentials/logins where needed, editing/approval of documents,
site-specific answers and user submission. Those are expected human actions, not unfinished CLI features.
