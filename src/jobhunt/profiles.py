"""Conservative CV contact extraction and non-destructive profile population."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from .config import load_yaml
from .cv_format import COMMENT_RE
from .cv_review import EMAIL_RE, PHONE_RE, section_of


def from_cv(text: str) -> dict[str, str]:
    """Extract explicit header contacts only; never infer citizenship, salary, work rights or preferences."""
    lines = COMMENT_RE.sub("", text).splitlines()
    header: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("## ") or (header and section_of(line) in
                                      ("summary", "skills", "experience", "education", "certifications")):
            break
        header.append(line)
        if len(header) >= 12:
            break
    out: dict[str, str] = {}
    if not header:
        return out
    name = re.sub(r"^[#\s]+", "", header[0]).strip("*_ ")
    if (2 <= len(name.split()) <= 7 and section_of(name) in (None, "other") and
            all(c.isalpha() or c in " .'-" for c in name)):
        out["name"] = name
    text = "\n".join(header)
    if email := EMAIL_RE.search(text):
        out["email"] = email.group()
    for field, domain in (("linkedin", r"(?:www\.)?linkedin\.com/in/"),
                          ("github", r"(?:www\.)?github\.com/")):
        if link := re.search(rf"(?:https?://)?{domain}[\w%-]+/?", text, re.I):
            out[field] = link.group() if "://" in link.group() else "https://" + link.group()
    for line in header:
        cells = [c.strip().strip("*_") for c in line.split("|")]
        for cell in cells:
            phone = re.sub(r"^(?:phone|mobile|tel)\s*:\s*", "", cell, flags=re.I)
            if PHONE_RE.fullmatch(phone):
                out.setdefault("phone", phone)
        if len(cells) > 1:
            location = cells[0]
            if re.fullmatch(r"[^\W\d_][^\d@:/|]+\s*,\s*[^\W\d_][^\d@:/|]+", location):
                out.setdefault("location", location)
    return out


def populate(path: Path, text: str, cv_path: Path) -> tuple[list[str], list[str]]:
    """Fill empty fields, preserve existing confirmed values, and report conflicts for manual review."""
    raw = load_yaml(path) if path.exists() else {"prefer_remote": False, "open_to_relocation": False}
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    extracted = from_cv(text)
    extracted["cv_path"] = cv_path.as_posix()
    filled, conflicts = [], []
    for key, value in extracted.items():
        if not raw.get(key):
            raw[key] = value
            filled.append(key)
        elif str(raw[key]) != value:
            conflicts.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return filled, conflicts
