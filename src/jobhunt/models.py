from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Job:
    title: str
    company: str
    url: str
    source: str
    location: str = ""
    description: str = ""
    remote: bool = False
    relocation: bool = False
    salary_min: float | None = None
    salary_max: float | None = None
    currency: str | None = None
    posted_at: str | None = None
    tags: list[str] = field(default_factory=list)
    region: str = "UNKNOWN"
    visa_sponsorship: bool | None = None  # None = not stated
    # Filled in by analysis steps
    skills: list[str] = field(default_factory=list)
    match_score: float | None = None
    rank: int | None = None
    score: float | None = None  # weighted ranking score (0-1)
    first_seen: str | None = None
    is_new: bool = False
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = hashlib.sha1(f"{self.source}|{self.company}|{self.title}|{self.url}".encode()).hexdigest()[:12]

    @property
    def salary_mid(self) -> float | None:
        vals = [v for v in (self.salary_min, self.salary_max) if v]
        return sum(vals) / len(vals) if vals else None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Job:
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def short(self) -> str:
        bits = [self.region, "remote" if self.remote else "onsite"]
        if self.relocation:
            bits.append("relocation")
        if self.visa_sponsorship:
            bits.append("visa")
        if self.salary_mid:
            bits.append(f"{self.currency or ''}{self.salary_mid:,.0f}")
        new = "🆕 " if self.is_new else ""
        return f"{new}[{self.id}] {self.title} @ {self.company} ({self.location or 'n/a'}) - {', '.join(bits)}"
