---
name: mock-interview
description: Run a mock interview or flashcard session for a selected job/application, list role-specific question types, and save I know / I don't know ratings with focused learning recommendations.
---

# Mock interview and flashcards

1. Confirm the person and job. Include `--person <id>` on every command for a named person.
2. `jobhunt mock-interview <job> --list`, or `jobhunt mock-interview --application <app-id> --list`.
   The output lists role-specific technical, knowledge, behavioural, company and (for senior roles)
   system-design/leadership questions. Cards have stable IDs and revealable answer/guide backs.
3. In chat, ask ONE question at a time without showing the back. Wait for the answer, then reveal the curated
   answer or explain the open-ended rubric. Do not claim a rubric is a complete model answer.
4. Ask the user to choose **I know** or **I don't know**. Record that choice, not your own inferred rating:
   `jobhunt mock-interview <job> --rate <card-id> --rating know|dont-know --answer "<optional answer>"`.
   Answers and timestamped ratings are local; do not send them to third parties.
5. For terminal practice: `jobhunt mock-interview <job>` or add `--mode flashcards`.
   The user answers/reveals, then chooses k/d (or the full labels), q to stop.
6. Revisit `--weak-only` and the generated `workspace/mock-interviews/<job-id>/practice.md`.
   Unknown topics link to the user's own resources plus curated/open learning, YouTube and LinkedIn Learning.
   Rate again after studying; history is preserved and the latest rating drives the weak list.
7. Self-ratings are confidence, NOT verified proficiency. Do not change CV skills, eligibility or application status.
