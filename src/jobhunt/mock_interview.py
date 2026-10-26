"""Job-specific interview rehearsal and flashcards with explicit, local self-ratings."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import assessment, interview, journal, rampup
from .config import workspace_dir
from .cv import match_job
from .models import Job
from .tracker import now

RATINGS = {"know": "I know", "dont-know": "I don't know"}
GUIDES = {
    "technical": "Explain the concept, give a concrete example, discuss trade-offs and how you would test it. "
                 "Use real experience; if you lack it, say so. This is an answer guide, not a model solution.",
    "behavioural": "Use STAR: Situation, Task, your specific Action, Result. Include a real outcome, "
                   "what you learned and what you would change. Do not invent a story or metric.",
    "system-design": "Clarify requirements and scale, sketch components and data flows, discuss alternatives, "
                     "failure modes, security, observability and trade-offs. Explain your own contribution.",
    "company": "Use sourced company research, connect the role to your actual goals and evidence, "
               "and prepare a specific follow-up question. Do not invent company facts.",
}


@dataclass(frozen=True)
class Card:
    id: str
    kind: str
    topic: str
    question: str
    back: str


def deck(job: Job, cv_skills: set[str]) -> list[Card]:
    """Reuse posting skills, seniority, behavioural themes and curated quiz answers."""
    data = interview.bank()
    match = match_job(cv_skills, job)
    cards: list[Card] = []

    def add(kind: str, topic: str, question: str, back: str) -> None:
        key = hashlib.sha256(f"{kind}\0{topic}\0{question}".encode()).hexdigest()[:12]
        cards.append(Card(key, kind, topic, question, back))

    for skill in match.missing + match.matched:
        for question in data.get("technical", {}).get(skill, [
            f"How would you use {skill} in this role, and what pitfalls would you watch for?",
        ]):
            add("technical", skill, question, GUIDES["technical"])
        for question in assessment.question_bank().get(skill, []):
            answer = str(question["options"][question["answer"]])
            prompt = question["q"] + "\n" + "\n".join(
                f"{chr(97 + i)}. {option}" for i, option in enumerate(question["options"]))
            add("knowledge", skill, prompt, answer + (
                f"\nWhy: {question['why']}" if question.get("why") else ""))
    for question in interview._behavioural(job, data):
        add("behavioural", "Behavioural", question, GUIDES["behavioural"])
    if interview._seniority(job.title) in ("senior", "lead"):
        for question in data["senior"]:
            add("system-design", "System design / leadership", question, GUIDES["system-design"])
    add("company", "Company research", f"Why {job.company}, and why this {job.title} role?", GUIDES["company"])
    return cards


def folder(job: Job) -> Path:
    path = workspace_dir() / "mock-interviews" / job.id
    path.mkdir(parents=True, exist_ok=True)
    return path


def history(job: Job) -> list[dict]:
    path = folder(job) / "ratings.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
            ] if path.exists() else []


def latest(job: Job) -> dict[str, str]:
    return {event["card_id"]: event["rating"] for event in history(job)}


def rate(job: Job, cards: list[Card], card_id: str, rating: str, answer: str = "") -> None:
    if rating not in RATINGS:
        raise ValueError("rating must be know or dont-know")
    card = next((card for card in cards if card.id == card_id), None)
    if card is None:
        raise ValueError(f"Unknown card {card_id!r}; use --list to see this job's current cards")
    event = {"ts": now(), "job_id": job.id, "card_id": card.id, "type": card.kind, "topic": card.topic,
             "rating": rating, "answer": answer}
    with (folder(job) / "ratings.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event) + "\n")
    journal.log(f"Mock interview: {card.topic} - {RATINGS[rating]}", kind="learning",
                tags=["mock-interview", job.id, card.topic])


def select(job: Job, cards: list[Card], weak_only: bool = False) -> list[Card]:
    ratings = latest(job)
    priority = {"dont-know": 0, None: 1, "know": 2}
    return sorted((card for card in cards if not weak_only or ratings.get(card.id) == "dont-know"),
                  key=lambda card: priority[ratings.get(card.id)])


def write_report(job: Job, cards: list[Card]) -> Path:
    ratings = latest(job)
    counts = Counter(ratings.get(card.id, "unrated") for card in cards)
    lines = [f"# Mock interview: {job.title} @ {job.company}", "",
             f"Updated {now()}. Self-ratings measure confidence, not verified proficiency or job eligibility.",
             f"I know: {counts['know']} | I don't know: {counts['dont-know']} | Unrated: {counts['unrated']}", "",
             "## Question types", ""]
    lines += [f"- {kind}: {count}" for kind, count in Counter(card.kind for card in cards).items()]
    lines += ["", "## Flashcards", "", "Try answering before revealing the back. "
              "Open-ended backs are checklists, not authoritative solutions.", ""]
    for card in select(job, cards):
        lines += [f"### {card.id} - {card.topic} ({card.kind})",
                  f"Rating: {RATINGS.get(ratings.get(card.id), 'Not rated')}", "",
                  card.question, "", "<details><summary>Reveal answer / guide</summary>", "",
                  card.back, "", "</details>", ""]
    weak = list(dict.fromkeys(card.topic for card in cards if ratings.get(card.id) == "dont-know"))
    lines += ["## Focused learning review", ""]
    user = rampup.load_user_resources()
    for topic in weak:
        lines += [f"### {topic}", ""]
        resources = [r for r in user if r.skill == topic] + rampup.open_resources(topic)
        # Keep video and LinkedIn discovery available even when curated resources fill the first slots.
        chosen = resources[:3] + [r for r in resources if r.provider in ("YouTube", "LinkedIn Learning")][:3]
        seen: set[tuple[str, str]] = set()
        for resource in chosen:
            key = (resource.name, resource.url)
            if key not in seen:
                seen.add(key)
                link = f"[{resource.name}]({resource.url})" if resource.url else resource.name
                lines.append(f"- {link}")
        lines += ["", "Review, practise an example, then rerate this topic's cards. "
                  "Search links are suggestions, not verified course recommendations.", ""]
    if not weak:
        lines += ["No cards currently rated 'I don't know'. Unrated cards still need practice.", ""]
    path = folder(job) / "practice.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def run(job: Job, cards: list[Card], mode: str, ask: Callable[[str], str], say: Callable[[str], None]) -> int:
    completed = 0
    for card in cards:
        say(f"\n[{card.id}] {card.kind} / {card.topic}\n{card.question}")
        answer = ""
        if mode == "interview":
            answer = ask("Your answer (or q to stop): ").strip()
            if answer.lower() == "q":
                break
        else:
            if ask("Think of your answer; Enter to reveal, q to stop: ").strip().lower() == "q":
                break
        say(f"\nAnswer / guide:\n{card.back}")
        while True:
            response = ask("I know [k] / I don't know [d] / stop [q]: ").strip().lower().replace("\u2019", "'")
            if response == "q":
                return completed
            rating = {"k": "know", "i know": "know", "d": "dont-know", "i don't know": "dont-know"}.get(response)
            if rating:
                rate(job, cards, card.id, rating, answer)
                completed += 1
                break
            say("Choose k (I know), d (I don't know), or q (stop). Nothing was rated.")
    return completed
