from jobhunt.cli import build_parser
from jobhunt.enrich import enrich
from jobhunt.models import Job
from jobhunt.opportunities import select
from jobhunt.sources import dedupe, file_import


def test_contract_metadata_and_duration():
    job = enrich(Job("Backend Engineer", "Client", "", "ashby", tags=["Contract"], description="Duration: 3 months"))
    assert job.opportunity_type == "project"
    assert job.duration == "3 months"
    assert select([job], "project") == [job]
    assert select([job], "job") == []


def test_contract_disclaimer_does_not_turn_permanent_role_into_project():
    job = enrich(
        Job(
            "Backend Engineer",
            "Company",
            "",
            "manual",
            description="Full-time role. Do not pay fees before signing an employment contract.",
        )
    )
    assert job.opportunity_type == "job"


def test_job_and_project_with_same_title_are_not_collapsed():
    permanent = Job("Engineer", "Company", "/permanent", "file")
    project = Job("Engineer", "Company", "/project", "file", opportunity_type="project")
    assert len(dedupe([permanent, project])) == 2


def test_manual_job_and_project_without_urls_have_distinct_ids():
    permanent = Job("Engineer", "Company", "", "manual")
    project = Job("Engineer", "Company", "", "manual", opportunity_type="project")
    assert permanent.id != project.id
    assert Job.from_dict(permanent.to_dict()).id == permanent.id
    assert Job.from_dict(project.to_dict()).id == project.id


def test_classified_projects_get_distinct_ids_without_changing_explicit_ids():
    permanent = Job("Engineer", "Company", "", "ashby")
    contract = enrich(Job("Engineer", "Company", "", "ashby", tags=["Contract"]))
    assert contract.id != permanent.id
    assert enrich(contract).id == contract.id
    explicit = enrich(Job("Engineer", "Company", "", "ashby", tags=["Contract"], id="source-provided-id"))
    assert explicit.id == "source-provided-id"


def test_project_import_and_parser(tmp_path):
    path = tmp_path / "projects.json"
    path.write_text(
        '[{"title":"API integration","company":"Client","opportunity_type":"project","duration":"6 weeks"}]'
    )
    job = file_import.load({"paths": [str(path)]})[0]
    assert job.opportunity_type == "project"
    assert job.duration == "6 weeks"
    assert build_parser().parse_args(["search", "--opportunity-type", "project"]).opportunity_type == "project"
    assert build_parser().parse_args(["add", "--opportunity-type", "project"]).opportunity_type == "project"
