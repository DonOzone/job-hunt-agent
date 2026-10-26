import json

import pytest

from jobhunt import cli
from jobhunt import mock_interview as mock
from jobhunt.config import person_scope
from jobhunt.models import Job
from jobhunt.store import save_jobs
from jobhunt.tracker import Tracker


def job(title="Senior Backend Engineer", url="https://example.com/jobs/one"):
    return Job(title=title, company="Example", url=url, source="manual",
               description="Python, SQL, Kubernetes. Ownership and collaboration.", rank=1)


def test_deck_is_stable_and_role_specific():
    senior = mock.deck(job(), {"Python"})
    assert senior == mock.deck(job(), {"Python"})
    assert len({card.id for card in senior}) == len(senior)
    assert {card.kind for card in senior} == {"technical", "knowledge", "behavioural", "system-design", "company"}
    assert any("CrashLoopBackOff" in card.question for card in senior)
    assert not any(card.kind == "system-design" for card in mock.deck(job("Junior Engineer"), set()))
    knowledge = next(card for card in senior if "yield" == card.back)
    assert "generator" in knowledge.question


def test_ratings_history_latest_and_learning_review(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    j = job()
    cards = mock.deck(j, set())
    card = next(c for c in cards if c.topic == "Python")
    mock.rate(j, cards, card.id, "dont-know", "Need to learn generators")
    assert mock.select(j, cards, weak_only=True) == [card]
    path = mock.write_report(j, cards)
    text = path.read_text()
    assert "I don't know: 1" in text and "youtube.com" in text and "linkedin.com/learning" in text
    mock.rate(j, cards, card.id, "know")
    assert not mock.select(j, cards, weak_only=True)
    assert len(mock.history(j)) == 2 and mock.latest(j)[card.id] == "know"
    assert "I know: 1" in mock.write_report(j, cards).read_text()
    with pytest.raises(ValueError, match="Unknown card"):
        mock.rate(j, cards, "missing", "know")
    with pytest.raises(ValueError, match="rating"):
        mock.rate(j, cards, card.id, "maybe")
    with person_scope("another"):
        assert not mock.history(j)
    assert not mock.history(job(url="https://example.com/jobs/two"))


def test_interactive_reveal_and_validated_ratings():
    j = job()
    cards = mock.deck(j, set())[:2]
    answers = iter(["My first answer", "invalid", "I don't know", "My second answer", "I know"])
    output = []
    assert mock.run(j, cards, "interview", lambda _: next(answers), output.append) == 2
    assert any("Nothing was rated" in line for line in output)
    assert mock.history(j)[0]["answer"] == "My first answer"
    assert [event["rating"] for event in mock.history(j)] == ["dont-know", "know"]
    responses = iter(["", "q"])
    assert mock.run(j, cards, "flashcards", lambda _: next(responses), output.append) == 0
    assert len(mock.history(j)) == 2


def test_flashcard_reveal_and_personal_learning_list(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    resources = tmp_path / "me" / "learning-resources.yaml"
    resources.parent.mkdir()
    resources.write_text("resources:\n  - {skill: Python, name: My selected tutorial, url: 'https://example.com/learn'}\n")
    j = job()
    cards = [next(card for card in mock.deck(j, set()) if card.topic == "Python")]
    responses = iter(["", "d"])
    shown = []
    assert mock.run(j, cards, "flashcards", lambda _: next(responses), shown.append) == 1
    assert cards[0].back in shown[-1]
    assert mock.history(j)[0]["answer"] == ""
    report = mock.write_report(j, cards).read_text()
    assert "My selected tutorial" in report and "https://example.com/learn" in report


def test_cli_by_application_and_noninteractive_ratings(tmp_path, tmp_home, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    cli.main(["--person", "jane", "init"])
    j = job()
    with person_scope("jane"):
        save_jobs([j])
        tracker = Tracker()
        app = tracker.add(j, "interview")
        tracker.close()
    cli.main(["--person", "jane", "mock-interview", "--application", str(app), "--list"])
    assert "Question types" in capsys.readouterr().out
    with person_scope("jane"):
        card = mock.deck(j, set())[0]
    cli.main(["mock-interview", "1", "--person", "jane", "--rate", card.id,
              "--rating", "dont-know", "--answer", "Need practice"])
    report = tmp_home / "people" / "jane" / "mock-interviews" / j.id
    events = [json.loads(line) for line in (report / "ratings.jsonl").read_text().splitlines()]
    assert events[0]["rating"] == "dont-know"
    assert "I don't know: 1" in (report / "practice.md").read_text()
    assert not (tmp_home / "mock-interviews").exists()
    with pytest.raises(SystemExit, match="terminal"):
        cli.main(["--person", "jane", "mock-interview", "1"])
    with pytest.raises(SystemExit, match="supplied together"):
        cli.main(["--person", "jane", "mock-interview", "1", "--rate", card.id])
    with pytest.raises(SystemExit, match="not both"):
        cli.main(["--person", "jane", "mock-interview", "1", "--application", str(app)])
