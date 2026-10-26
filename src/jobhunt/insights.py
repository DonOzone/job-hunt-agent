"""Mindset + strategy coaching based on your tracker stats.

Principles are short paraphrased lessons (data/principles.yaml) inspired by "Who Moved My Cheese?"
(Spencer Johnson) and widely-cited job-search practices - not quotations from the book.
"""
from __future__ import annotations

import random
from datetime import date

from .config import load_data


def principles() -> dict[str, list[dict]]:
    return load_data("principles.yaml")


def contextual_tips(summary: dict, stale_count: int = 0, top_gaps: list[str] | None = None) -> list[dict]:
    """Pick the principles that fit where the user is right now."""
    data = principles()
    triggers: set[str] = {"always"}
    submitted = summary.get("submitted", 0)
    if submitted < 10:
        triggers.add("low_volume")
    if submitted >= 5 and summary.get("response_rate", 0) < 0.1:
        triggers.add("low_response")
    if summary.get("failed", 0) >= 3:
        triggers.add("rejections")
    if summary.get("by_status", {}).get("interview", 0) and not summary.get("by_status", {}).get("offer"):
        triggers.add("interviewing")
    if stale_count:
        triggers.add("stale")
    if top_gaps:
        triggers.add("skill_gaps")

    tips = []
    for group in ("cheese", "strategy"):
        for p in data.get(group, []):
            if triggers & set(p.get("when", ["always"])):
                tips.append({**p, "group": group})
    # Promote situational tips over generic ones
    tips.sort(key=lambda p: "always" in p.get("when", ["always"]))
    return tips


def daily_principle(seed: int | None = None) -> dict:
    items = principles().get("cheese", [])
    rng = random.Random(seed if seed is not None else date.today().toordinal())
    return rng.choice(items) if items else {}


def render(tips: list[dict], limit: int = 8) -> str:
    lines = ["# Insights for today", ""]
    for p in tips[:limit]:
        icon = "🧀" if p["group"] == "cheese" else "🎯"
        lines += [f"{icon} **{p['title']}** — {p['lesson']}", f"   ↳ Action: {p['action']}", ""]
    return "\n".join(lines)
