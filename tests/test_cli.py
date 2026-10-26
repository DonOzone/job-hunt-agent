import json

from jobhunt import cli
from jobhunt.sources import api_sources

FAKE = {"jobs": [
    {"title": "Senior Backend Engineer", "absolute_url": "https://gh/1", "location": {"name": "London, UK"},
     "content": "Python, Kubernetes, AWS, Terraform. Relocation support. £95,000 - £115,000"},
    {"title": "Platform Engineer", "absolute_url": "https://gh/2", "location": {"name": "Remote"},
     "content": "Go, Kubernetes, Docker. $130k-$160k"},
    {"title": "Marketing Intern", "absolute_url": "https://gh/3", "location": {"name": "Paris"}, "content": "Excel"},
]}


def test_cli_end_to_end(tmp_path, tmp_home, monkeypatch, capsys):
    monkeypatch.setattr(api_sources, "get_json", lambda url, params=None: FAKE)
    cv = tmp_path / "cv.md"
    cv.write_text("Python, Docker, AWS, Git, 5 years")
    profile = tmp_path / "profile.yaml"
    profile.write_text(
        f"name: Jane Doe\nemail: j@x.com\ncv_path: {cv}\npreferred_regions: [UK, GLOBAL]\n"
        "requirement:\n  roles: [backend engineer, platform engineer]\n  exclude: [intern]\n")
    sites = tmp_path / "sites.yaml"
    sites.write_text("sites:\n  - {type: greenhouse, company: acme}\n")
    p = ["--profile", str(profile)]

    cli.main(["run", *p, "--sites", str(sites)])
    saved = json.loads((tmp_home / "jobs.json").read_text())
    assert [j["region"] for j in saved] == ["UK", "GLOBAL"]
    for f in ("ranked-jobs.md", "skill-gaps.md", "study-plan.md", "insights.md", "journal.md"):
        assert (tmp_home / f).exists(), f
    assert len(list((tmp_home / "interview-prep").glob("*.md"))) == 2

    cli.main(["track", "add", "1"])
    cli.main(["track", "update", "1", "applied", "--note", "via site", "--next", "follow up", "--due", "7"])
    cli.main(["track", "update", "1", "rejected", "--note", "no feedback"])
    cli.main(["track", "report"])
    report = (tmp_home / "applications-report.md").read_text()
    assert "❌ Failed (1)" in report and "via site" in report

    cli.main(["eligibility", *p])
    cli.main(["gaps", *p])
    cli.main(["journal", "log", "Practised system design", "--kind", "learning"])
    cli.main(["insights", *p])
    out = capsys.readouterr().out
    assert "Kubernetes" in out and "Insights for today" in out
