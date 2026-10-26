from __future__ import annotations

import os
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

DEFAULT_FX_TO_USD = {"USD": 1.0, "EUR": 1.08, "GBP": 1.27, "CAD": 0.73, "AUD": 0.66, "CHF": 1.12,
                     "INR": 0.012, "KES": 0.0077, "NGN": 0.00065, "ZAR": 0.055, "SEK": 0.095, "PLN": 0.25,
                     "AED": 0.27}

# Friendly names accepted in preferred_regions -> internal region codes
REGION_ALIASES = {"AFRICA": "MEA", "MIDDLE EAST": "MEA", "EUROPE": "EU", "EMEA": "EU", "NORTH AMERICA": "NA",
                  "US": "NA", "USA": "NA", "CANADA": "NA", "ASIA": "APAC", "LATIN AMERICA": "LATAM",
                  "SOUTH AMERICA": "LATAM", "WORLDWIDE": "GLOBAL", "ANYWHERE": "GLOBAL", "REMOTE": "GLOBAL",
                  "UNITED KINGDOM": "UK", "GB": "UK"}

# Credentials/secrets are read from the environment (or a local .env file), never from committed YAML.
ENV_NOTIFY = {"JOBHUNT_NTFY_TOPIC": "ntfy_topic", "JOBHUNT_WEBHOOK_URL": "webhook_url", "JOBHUNT_DESKTOP": "desktop"}


def load_dotenv(path: str | Path = ".env") -> None:
    """Minimal .env loader (KEY=value lines). Existing environment variables win."""
    path = Path(path)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def workspace_dir() -> Path:
    """Local folder that stores jobs, tracker DB, journal and reports."""
    path = Path(os.environ.get("JOBHUNT_HOME", "workspace")).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_yaml(path: str | Path) -> Any:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_data(name: str) -> Any:
    """Load a bundled catalog from jobhunt/data."""
    text = resources.files("jobhunt.data").joinpath(name).read_text(encoding="utf-8")
    return yaml.safe_load(text) or {}


@dataclass
class Requirement:
    roles: list[str] = field(default_factory=list)
    must_have: list[str] = field(default_factory=list)
    nice_to_have: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    include_any: list[str] = field(default_factory=list)  # at least one must appear in title/description
    exclude_text: list[str] = field(default_factory=list)  # drop if any appears in title/description
    remote_only: bool = False
    min_salary_usd: float | None = None
    max_age_days: int | None = None
    needs_visa_sponsorship: bool = False  # drop onsite jobs that explicitly refuse sponsorship


@dataclass
class Profile:
    name: str = ""
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    github: str = ""
    website: str = ""
    location: str = ""
    cv_path: str = ""
    home_country: str = ""
    preferred_regions: list[str] = field(default_factory=list)
    prefer_remote: bool = True
    open_to_relocation: bool = True
    target_salary_usd: float | None = None
    ranking_mode: str = "strict"  # strict = region > remote > relocation > package > match; weighted = blended score
    ranking_weights: dict[str, float] = field(default_factory=lambda: {
        "region": 0.25, "remote": 0.25, "relocation": 0.15, "package": 0.20, "match": 0.15})
    achievements: list[str] = field(default_factory=list)
    work_authorization: list[str] = field(default_factory=list)  # countries you can already work in
    security_clearance: bool = False
    languages: dict[str, str] = field(default_factory=dict)  # e.g. {English: fluent, Swahili: native}
    career_goals: list[str] = field(default_factory=list)  # words that make a role attractive
    avoid: list[str] = field(default_factory=list)  # words that make a role draining
    requirement: Requirement = field(default_factory=Requirement)
    fx_to_usd: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_FX_TO_USD))
    notify: dict[str, Any] = field(default_factory=dict)
    answers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> Profile:
        raw = load_yaml(path)
        req = Requirement(**(raw.pop("requirement", {}) or {}))
        fx = dict(DEFAULT_FX_TO_USD)
        fx.update(raw.pop("fx_to_usd", {}) or {})
        known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
        profile = cls(requirement=req, fx_to_usd=fx, **known)
        profile.preferred_regions = [REGION_ALIASES.get(r.upper(), r.upper()) for r in profile.preferred_regions]
        profile.notify = dict(profile.notify or {})
        for env, key in ENV_NOTIFY.items():
            if os.environ.get(env):
                profile.notify[key] = os.environ[env] if key != "desktop" else os.environ[env] not in ("0", "false")
        return profile


def load_sites(path: str | Path) -> list[dict[str, Any]]:
    raw = load_yaml(path)
    return raw.get("sites", []) if isinstance(raw, dict) else list(raw)
