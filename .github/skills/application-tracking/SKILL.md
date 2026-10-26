---
name: application-tracking
description: Record and report job application progress with timestamps (passed, failed, pending), follow-ups, journal entries and mindset insights. Use when the user reports news about an application or asks for status.
---

# Tracking, journal & insights

- Status flow: `saved → applying → applied → screening → assessment → interview → final → offer → accepted`;
  failures: `rejected | failed | ghosted | withdrawn | declined`; `skipped` for passes.
- Update: `jobhunt track update <app-id> interview --note "Recruiter call Tue" --next "Send thank-you" --due 1`
  (each update is a timestamped event). Show: `jobhunt track list [passed|failed|pending|<status>]`,
  `jobhunt track history <app-id>`, `jobhunt track report` → `workspace/applications-report.md`.
- Follow-ups: `jobhunt track followups [--days 7]` lists quiet submitted applications and writes a short draft
  note per app to `workspace/followups/`. Help the user personalise the `<...>` line, they send it, then log it
  with `jobhunt track sent <app-id>` (restarts the quiet clock). Max two follow-ups per application.
- Sweep: `jobhunt track sweep [--days 60]` closes long-quiet applications as `ghosted` (asks first; `-y` to skip).
- Dashboard: `jobhunt track dashboard` → `workspace/dashboard.html` (funnel from full history: submitted →
  response → interview → offer, applications per week, by status/source, days quiet, follow-ups sent).
- Journal: `jobhunt journal log "..." --kind progress|learning|feedback|win|setback`; `jobhunt journal show`.
  Always log rejection feedback as `--kind feedback`.
- Coaching: `jobhunt insights` gives "Who Moved My Cheese?"-inspired mindset tips and job-search strategy chosen
  from the user's real stats (low response → tailor + referrals; rejections → adapt; stale → follow up).
  Be encouraging but honest.
