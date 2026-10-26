"""Runs the real Playwright assistant against a local ATS-like form (skipped if Chromium isn't installed)."""
import pytest

from jobhunt.apply import ApplyAssistant
from jobhunt.models import Job
from jobhunt.notify import Notifier
from jobhunt.tracker import Tracker

pw = pytest.importorskip("playwright.sync_api")

FORM = """<html><body><form id="f" onsubmit="document.body.dataset.sent='1'; return false;">
<label for="fn">First Name *</label><input id="fn" required>
<label for="ln">Last Name *</label><input id="ln" required>
<label>Email <input name="email" type="email" required></label>
<input placeholder="LinkedIn Profile" name="urls[LinkedIn]">
<label for="np">What is your notice period?</label><input id="np">
<label for="cv">Resume/CV *</label><input id="cv" type="file" required>
<label for="why">Why do you want to work here? *</label><textarea id="why" required></textarea>
<button type="submit">Submit application</button></form></body></html>"""


def _chromium_available():
    try:
        with pw.sync_playwright() as p:
            p.chromium.launch().close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _chromium_available(), reason="playwright chromium not installed")
def test_assistant_fills_form(tmp_path, profile):
    page = tmp_path / "form.html"
    page.write_text(FORM)
    cv = tmp_path / "cv.pdf"
    cv.write_bytes(b"%PDF-1.4 fake")
    profile.cv_path = str(cv)
    profile.linkedin = "https://linkedin.com/in/jane"
    profile.answers = {"notice period": "4 weeks"}
    tr = Tracker()
    msgs = []
    assistant = ApplyAssistant(profile, tr, Notifier(echo=msgs.append), confirm=lambda _: "y", headless=True)
    res = assistant.apply(Job(title="BE", company="Acme", url=page.as_uri(), source="test"),
                          auto_submit=True, missing_skills=["Kubernetes"])
    assert {"first_name", "last_name", "email", "linkedin", "answer:notice period", "resume"} <= set(res.filled)
    assert res.missing_required == ["Why do you want to work here? *"]
    # A required field is still empty, so it must NOT auto-submit; user confirmed manually ('y').
    assert res.status == "applied"
    assert [e["status"] for e in tr.history(res.app_id)] == ["saved", "applying", "applied"]
    assert any("Room for growth" in m and "Kubernetes" in m for m in msgs)
    assert (tmp_path / "ws" / "screenshots").exists()
    tr.close()
