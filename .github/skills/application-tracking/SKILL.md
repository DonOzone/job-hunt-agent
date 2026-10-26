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
- Follow-ups: `jobhunt track followups --days 7` pings the user about quiet applications.
- Journal: `jobhunt journal log "..." --kind progress|learning|feedback|win|setback`; `jobhunt journal show`.
  Always log rejection feedback as `--kind feedback`.
- Coaching: `jobhunt insights` gives "Who Moved My Cheese?"-inspired mindset tips and job-search strategy chosen
  from the user's real stats (low response → tailor + referrals; rejections → adapt; stale → follow up).
  Be encouraging but honest.
