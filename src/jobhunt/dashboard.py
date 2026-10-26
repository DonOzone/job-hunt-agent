"""Self-contained HTML dashboard of your applications (no JavaScript, no external files - open it anywhere)."""
from __future__ import annotations

import html
from collections import Counter
from datetime import datetime

from .tracker import FAILED, PASSED, Tracker, now, outcome

COLOURS = {"passed": "#2e7d32", "failed": "#c62828", "pending": "#1f3864"}
CSS = """
body{font-family:Calibri,Segoe UI,Arial,sans-serif;margin:24px auto;max-width:1100px;color:#222;padding:0 16px}
h1{color:#1f3864;margin-bottom:0}h2{color:#1f3864;border-bottom:2px solid #dbe4f0;padding-bottom:4px}
.muted{color:#777}.cards{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}
.card{flex:1;min-width:130px;background:#f4f7fb;border-radius:8px;padding:12px 16px}
.card b{display:block;font-size:28px;color:#1f3864}.bar{height:22px;border-radius:4px;color:#fff;padding:0 8px;
line-height:22px;font-size:13px;white-space:nowrap;min-width:fit-content}
.row{display:flex;align-items:center;gap:10px;margin:6px 0}.row span{width:150px}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:6px 8px;
border-bottom:1px solid #e5e5e5}th{background:#f4f7fb}.pill{border-radius:10px;padding:1px 8px;color:#fff;
font-size:12px}
"""


def _bars(counts: list[tuple[str, int]], colour: str | dict[str, str] = "#1f3864") -> str:
    top = max((v for _, v in counts), default=1) or 1
    out = []
    for label, value in counts:
        c = colour.get(label, "#1f3864") if isinstance(colour, dict) else colour
        out.append(f'<div class="row"><span>{html.escape(str(label))}</span><div class="bar" '
                   f'style="width:{max(4, 100 * value / top):.0f}%;background:{c}">{value}</div></div>')
    return "\n".join(out) or '<p class="muted">No data yet.</p>'


def _pct(a: int, b: int) -> str:
    return f"{a / b:.0%}" if b else "-"


def render(tr: Tracker) -> str:
    rows = [r for r in tr.list() if r["status"] != "skipped"]
    f = tr.funnel()
    by_status = Counter(r["status"] for r in rows)
    by_source = Counter(r["source"] or "manual" for r in rows)
    weeks: Counter[str] = Counter()
    for r in rows:
        sent = next((e["ts"] for e in tr.history(r["id"]) if e["status"] == "applied"), None)
        if sent:
            y, w, _ = datetime.fromisoformat(sent).isocalendar()
            weeks[f"{y}-W{w:02d}"] += 1
    stale = {r["id"] for r in tr.stale(7)}
    parts = [f"<!doctype html><html><head><meta charset='utf-8'><title>Job hunt dashboard</title>"
             f"<style>{CSS}</style></head><body>",
             "<h1>Job hunt dashboard</h1>", f'<p class="muted">Generated {now()}</p>', '<div class="cards">']
    for label, value in (("Tracked", len(rows)), ("Submitted", f["submitted"]),
                         ("Response rate", _pct(f["responded"], f["submitted"])),
                         ("Interview rate", _pct(f["interview"], f["submitted"])),
                         ("Offers", f["offer"]), ("Follow-ups due", len(stale))):
        parts.append(f'<div class="card">{label}<b>{value}</b></div>')
    parts += ["</div>", "<h2>Funnel</h2>", '<p class="muted">Counted from each application\'s full history, so a '
              "rejection after an interview still counts as reaching interview.</p>",
              _bars([("Submitted", f["submitted"]), ("Got a response", f["responded"]),
                     ("Interviewed", f["interview"]), ("Offer", f["offer"])]),
              "<h2>Applications per week</h2>", _bars(sorted(weeks.items())[-12:]),
              "<h2>Current status</h2>",
              _bars(sorted(by_status.items(), key=lambda kv: -kv[1]),
                    {s: COLOURS[outcome(s)] for s in by_status}),
              "<h2>By source</h2>", _bars(by_source.most_common()),
              "<h2>All applications</h2>",
              "<table><tr><th>#</th><th>Role</th><th>Company</th><th>Status</th><th>Updated</th>"
              "<th>Days quiet</th><th>Follow-ups</th><th>Next action</th></tr>"]
    for r in rows:
        c = COLOURS[outcome(r["status"])]
        quiet = tr.days_quiet(r["id"])
        title = html.escape(r["title"] or "")
        link = f'<a href="{html.escape(r["url"])}">{title}</a>' if r["url"] else title
        parts.append(
            f"<tr><td>{r['id']}</td><td>{link}</td><td>{html.escape(r['company'] or '')}</td>"
            f'<td><span class="pill" style="background:{c}">{r["status"]}</span></td>'
            f"<td>{(r['updated_at'] or '')[:10]}</td><td>{'⏰ ' if r['id'] in stale else ''}{quiet}</td>"
            f"<td>{tr.followups_sent(r['id'])}</td>"
            f"<td>{html.escape(r['next_action'] or '')} {html.escape(r['next_action_due'] or '')}</td></tr>")
    parts += ["</table>", f'<p class="muted">Passed = {", ".join(sorted(PASSED))}. '
              f'Failed = {", ".join(sorted(FAILED))}.</p>', "</body></html>"]
    return "\n".join(parts)
