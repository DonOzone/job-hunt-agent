import pytest

from jobhunt import cli, rampup
from jobhunt.gaps import Gap


def gap(skill="Kubernetes", importance=80.0):
    return Gap(skill=skill, category="devops", importance=importance, jobs=3, share=0.5)


def test_user_list_formats(tmp_path):
    y = tmp_path / "l.yaml"
    y.write_text("resources:\n  - {skill: kubernetes, name: K8s course, url: 'https://x.io/k', hours: 4, free: true}\n")
    t = tmp_path / "l.md"
    t.write_text("# my list\nSkill | Title | URL | hours\n- Terraform | TF tutorials | https://tf.io/t | 8\n"
                 "|---|---|---|---|\nSQL,SQLBolt,https://sqlbolt.com,2\n")
    (r,) = rampup.load_user_resources(y)
    assert (r.skill, r.hours, r.free, r.origin) == ("Kubernetes", 4.0, True, "yours")
    rows = rampup.load_user_resources(t)
    assert [(x.skill, x.name, x.hours) for x in rows] == [("Terraform", "TF tutorials", 8.0), ("SQL", "SQLBolt", 2.0)]
    with pytest.raises(FileNotFoundError):
        rampup.load_user_resources(tmp_path / "nope.yaml")


def test_build_puts_user_resources_first_and_adds_open_sources():
    mine = [rampup.Resource(skill="Kubernetes", name="My course", url="https://x/k", hours=5, origin="yours")]
    (step,) = rampup.build([gap()], mine, max_skills=1)
    assert step.resources[0].origin == "yours" and step.hours == 5
    assert any(r.provider == "YouTube" for r in rampup.open_resources("Kubernetes"))
    assert step.practice


def test_free_filter_and_named_skills_lead():
    assert not any(r.free is False for r in rampup.open_resources("Python", free_only=True))
    steps = rampup.build([gap("Terraform")], [], extra_skills=["kubernetes"], max_skills=2)
    assert [s.skill for s in steps] == ["Kubernetes", "Terraform"]
    text = rampup.render(steps)
    assert "linkedin.com/learning" in text and "ramp-up log" in text


def test_cli_ramp_up_named_skills_and_log(tmp_home, capsys, tmp_path):
    tmp_home.mkdir(parents=True, exist_ok=True)
    lst = tmp_path / "mine.csv"
    lst.write_text("Kubernetes,K8s the hard way,https://github.com/kelseyhightower/kubernetes-the-hard-way,10\n")
    cli.main(["ramp-up", "--skills", "Kubernetes", "--resources", str(lst), "--profile", "missing.yaml"])
    out = (tmp_home / "ramp-up.md").read_text()
    assert "K8s the hard way" in out and "YOUR LIST" in out and "youtube.com" in out
    cli.main(["ramp-up", "log", "kubernetes", "--hours", "3", "--note", "deployed demo"])
    assert "assess" in capsys.readouterr().out
    assert "deployed demo" in (tmp_home / "journal.jsonl").read_text()
