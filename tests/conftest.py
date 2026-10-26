import pytest

from jobhunt.config import Profile, Requirement
from jobhunt.models import Job


@pytest.fixture(autouse=True)
def tmp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBHUNT_HOME", str(tmp_path / "ws"))
    return tmp_path / "ws"


@pytest.fixture
def jobs():
    return [
        Job(title="Senior Backend Engineer", company="Acme", url="https://boards.greenhouse.io/acme/jobs/1",
            source="greenhouse", location="London, UK",
            description="Python, Kubernetes and AWS. Relocation assistance available. £90,000 - £110,000"),
        Job(title="Backend Engineer", company="Remote Co", url="https://jobs.lever.co/remoteco/2", source="lever",
            location="Remote - Anywhere", description="Go, Docker, Terraform. Salary $120k-$150k", remote=True),
        Job(title="Platform Engineer", company="Berlin GmbH", url="https://jobs.ashbyhq.com/berlin/3", source="ashby",
            location="Berlin, Germany", description="Kubernetes, Terraform, Go. Visa sponsorship provided. €80,000"),
        Job(title="Frontend Intern", company="Nope", url="https://x/4", source="remoteok", location="New York",
            description="React and TypeScript"),
    ]


@pytest.fixture
def profile():
    return Profile(name="Jane Doe", email="jane@example.com", preferred_regions=["UK", "EU", "GLOBAL", "NA"],
                   prefer_remote=True, open_to_relocation=True,
                   requirement=Requirement(roles=["backend engineer", "platform engineer"], exclude=["intern"]))
