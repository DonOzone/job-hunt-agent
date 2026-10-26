from jobhunt.enrich import detect_region, enrich, parse_salary, strip_html
from jobhunt.matcher import filter_jobs, title_matches
from jobhunt.ranking import rank_jobs, render_markdown


def test_strip_html():
    assert strip_html("&lt;p&gt;Hello <b>world</b>&lt;/p&gt;") == "Hello world"


def test_parse_salary_variants():
    assert parse_salary("Pay: $120k - $150k") == (120000, 150000, "USD")
    assert parse_salary("£90,000 – £110,000 per year") == (90000, 110000, "GBP")
    assert parse_salary("EUR 75000") == (75000, None, "EUR")
    assert parse_salary("5 years experience, $50/hour") == (104000, None, "USD")  # annualised
    assert parse_salary("KES 450,000 per month") == (5_400_000, None, "KES")
    assert parse_salary("Salary 70.000 EUR") == (70000, None, "EUR")
    assert parse_salary("3 years of experience, team of 12") == (None, None, None)


def test_detect_region():
    assert detect_region("London, UK") == "UK"
    assert detect_region("Berlin, Germany") == "EU"
    assert detect_region("Remote") == "GLOBAL"
    assert detect_region("Lagos, Nigeria") == "MEA"


def test_enrich_flags(jobs):
    a, b, c, _ = [enrich(j) for j in jobs]
    assert a.relocation and not a.remote and a.region == "UK" and a.currency == "GBP"
    assert b.remote and b.region == "GLOBAL" and b.salary_max == 150000
    assert c.relocation and c.region == "EU"


def test_visa_and_relocation_flags():
    from jobhunt.models import Job
    j = enrich(Job(title="x", company="y", url="u", source="s", description="No visa sponsorship. Relocation support"))
    assert j.relocation and j.visa_sponsorship is False
    j = enrich(Job(title="x", company="y", url="u", source="s", description="We sponsor visas for this role"))
    assert j.visa_sponsorship is True and j.relocation
    j = enrich(Job(title="x", company="y", url="u", source="s", description="Great team"))
    assert j.visa_sponsorship is None


def test_title_matching():
    assert title_matches("Senior Backend Engineer (Python)", ["backend engineer"])
    assert not title_matches("Backend Developer", ["backend engineer"])
    assert title_matches("Anything", [])


def test_filter_and_rank(jobs, profile):
    jobs = [enrich(j) for j in jobs]
    matched = filter_jobs(jobs, profile.requirement, profile.fx_to_usd)
    assert [j.company for j in matched] == ["Acme", "Remote Co", "Berlin GmbH"]
    ranked = rank_jobs(matched, profile)
    assert [j.region for j in ranked] == ["UK", "EU", "GLOBAL"]
    assert [j.rank for j in ranked] == [1, 2, 3]
    md = render_markdown(ranked, profile)
    assert "## UK (1)" in md and "Acme" in md


def test_rank_custom_order(jobs, profile):
    ranked = rank_jobs([enrich(j) for j in jobs[:3]], profile, ("salary",))
    assert ranked[0].company == "Remote Co"  # highest USD package


def test_min_salary_filter(jobs, profile):
    profile.requirement.min_salary_usd = 100_000
    matched = filter_jobs([enrich(j) for j in jobs], profile.requirement, profile.fx_to_usd)
    assert "Berlin GmbH" not in [j.company for j in matched]


def test_new_filters(jobs, profile):
    from jobhunt.models import Job
    jobs = [enrich(j) for j in jobs]
    profile.requirement.exclude_text = ["terraform"]
    assert [j.company for j in filter_jobs(jobs, profile.requirement)] == ["Acme"]
    profile.requirement.exclude_text = []
    profile.requirement.include_any = ["kubernetes"]
    assert [j.company for j in filter_jobs(jobs, profile.requirement)] == ["Acme", "Berlin GmbH"]
    profile.requirement.include_any = []
    profile.requirement.needs_visa_sponsorship = True
    nope = enrich(Job(title="Backend Engineer", company="NoVisa", url="u", source="s", location="Paris, France",
                      description="Applicants must be authorized to work in the EU."))
    assert nope not in filter_jobs([nope], profile.requirement)
    profile.requirement.needs_visa_sponsorship = False
    profile.requirement.max_age_days = 30
    old = enrich(Job(title="Backend Engineer", company="Old", url="u", source="s", posted_at="2000-01-01"))
    assert filter_jobs([old], profile.requirement) == []


def test_weighted_mode_and_home_country(jobs, profile):
    jobs = [enrich(j) for j in jobs[:3]]
    profile.home_country = "Germany"
    profile.ranking_mode = "weighted"
    ranked = rank_jobs(jobs, profile)
    assert all(0 <= j.score <= 1 for j in ranked)
    assert ranked == sorted(ranked, key=lambda j: -j.score)
    from jobhunt.ranking import component_scores
    assert component_scores(next(j for j in jobs if j.company == "Berlin GmbH"), profile)["relocation"] == 1.0


def test_region_aliases(tmp_path):
    from jobhunt.config import Profile
    p = tmp_path / "p.yaml"
    p.write_text("preferred_regions: [Africa, Europe, Worldwide]\n")
    assert Profile.load(p).preferred_regions == ["MEA", "EU", "GLOBAL"]


def test_env_credentials(tmp_path, monkeypatch):
    from jobhunt.config import Profile, load_dotenv
    env = tmp_path / ".env"
    env.write_text("# secrets\nJOBHUNT_NTFY_TOPIC=my-topic\nJOBHUNT_DESKTOP=1\n")
    monkeypatch.delenv("JOBHUNT_NTFY_TOPIC", raising=False)
    monkeypatch.delenv("JOBHUNT_DESKTOP", raising=False)
    load_dotenv(env)
    p = tmp_path / "p.yaml"
    p.write_text("name: X\n")
    prof = Profile.load(p)
    assert prof.notify["ntfy_topic"] == "my-topic" and prof.notify["desktop"] is True
