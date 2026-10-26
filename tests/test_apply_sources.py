import pytest

from jobhunt import apply as apply_mod
from jobhunt.apply import ApplyAssistant, classify_field, detect_ats, profile_values
from jobhunt.models import Job
from jobhunt.notify import Notifier
from jobhunt.sources import api_sources, collect
from jobhunt.tracker import Tracker


def test_detect_ats():
    assert detect_ats("https://boards.greenhouse.io/x/jobs/1") == "greenhouse"
    assert detect_ats("https://acme.wd5.myworkdayjobs.com/x") == "workday"
    assert detect_ats("https://example.com/careers/1") == "generic"


def test_classify_fields(profile):
    assert classify_field("First Name *") == "first_name"
    assert classify_field("Surname") == "last_name"
    assert classify_field("Email address") == "email"
    assert classify_field("LinkedIn Profile") == "linkedin"
    assert classify_field("What is your notice period?", {"notice period": "4 weeks"}) == "answer:notice period"
    assert classify_field("Favourite colour") is None
    vals = profile_values(profile)
    assert vals["first_name"] == "Jane" and vals["last_name"] == "Doe"


def test_apply_dry_run_and_blocked(profile):
    msgs = []
    tr = Tracker()
    a = ApplyAssistant(profile, tr, Notifier(echo=msgs.append))
    res = a.apply(Job(title="BE", company="Acme", url="https://jobs.lever.co/acme/1", source="lever"), dry_run=True)
    assert res.status == "saved"
    assert [e["status"] for e in tr.history(res.app_id)] == ["saved", "applying", "saved"]
    with pytest.raises(RuntimeError):
        a.apply(Job(title="x", company="y", url="https://www.linkedin.com/jobs/1", source="s"))
    tr.close()


def test_expected_flows_cover_known_ats():
    assert {"greenhouse", "lever", "ashby", "workday", "generic"} <= set(apply_mod.EXPECTED_FLOWS)


def test_sources_parse(monkeypatch):
    payloads = {
        "greenhouse": {"jobs": [{"title": "Backend Engineer", "absolute_url": "https://gh/1",
                                 "location": {"name": "Remote, UK"}, "content": "&lt;p&gt;Python&lt;/p&gt;",
                                 "updated_at": "2026-10-01T00:00:00Z"}]},
        "lever": [{"text": "Platform Engineer", "hostedUrl": "https://lever/2", "categories": {"location": "Berlin"},
                   "descriptionPlain": "Kubernetes", "workplaceType": "remote", "createdAt": 1760000000000,
                   "salaryRange": {"min": 70000, "max": 90000, "currency": "EUR"}, "lists": []}],
        "ashby": {"jobs": [{"title": "SRE", "jobUrl": "https://ashby/3", "location": "Toronto", "isRemote": False,
                            "descriptionPlain": "Go", "compensation": {"summaryComponents": [
                                {"compensationType": "Salary", "minValue": 100000, "maxValue": 130000,
                                 "currencyCode": "CAD"}]}}]},
        "remoteok": [{"legal": "notice"}, {"position": "DevOps", "company": "R", "url": "https://rok/4",
                                           "description": "Terraform", "salary_min": 90000, "salary_max": 0,
                                           "date": "2026-10-01"}],
        "arbeitnow": {"data": [{"title": "Backend", "company_name": "A", "url": "https://an/5", "location": "Munich",
                                "description": "Java", "remote": False, "created_at": 1760000000}],
                      "links": {"next": None}},
    }

    def fake_get(url, params=None):
        for key, payload in payloads.items():
            if key in url:
                return payload
        raise AssertionError(url)

    monkeypatch.setattr(api_sources, "get_json", fake_get)
    sites = [{"type": "greenhouse", "company": "g"}, {"type": "lever", "company": "l"},
             {"type": "ashby", "company": "a"}, {"type": "remoteok"}, {"type": "arbeitnow"},
             {"type": "unknown"}]
    jobs = {j.source: j for j in collect(sites)}
    assert set(jobs) == {"greenhouse", "lever", "ashby", "remoteok", "arbeitnow"}
    assert jobs["greenhouse"].description == "Python" and jobs["greenhouse"].region == "UK"
    assert jobs["lever"].remote and jobs["lever"].currency == "EUR" and jobs["lever"].region == "EU"
    assert jobs["ashby"].salary_max == 130000 and jobs["ashby"].region == "NA"
    assert jobs["remoteok"].remote and jobs["remoteok"].salary_max is None


def test_collect_survives_failing_source(monkeypatch):
    def boom(url, params=None):
        raise ConnectionError("down")
    monkeypatch.setattr(api_sources, "get_json", boom)
    assert collect([{"type": "remoteok"}]) == []
