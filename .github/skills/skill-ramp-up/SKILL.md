---
name: skill-ramp-up
description: Build a learning path for skills the user is missing, using their own resource list plus open materials (YouTube, LinkedIn Learning, freeCodeCamp, Coursera/edX audit, MIT OCW, Microsoft Learn, GitHub, roadmap.sh). Use when asked how to learn, upskill, ramp up or close a gap.
---

# Skill ramp-up

1. Make sure there are gaps: `jobhunt gaps` (needs saved jobs), or take skills the user names.
2. Ask whether they have a learning list. If yes, save it as `me/learning-resources.yaml` (see
   `examples/learning-resources.example.yaml`) or `.md`/`.csv` lines `Skill | Title | URL | hours`.
3. `jobhunt ramp-up` (top gaps) · `jobhunt ramp-up --skills "A,B"` (named skills) · add `--free` to hide paid
   material, `--hours-per-week N` to set pace. Output: `workspace/ramp-up.md`. User resources come first, then curated
   courses, then open search links.
4. Present the plan briefly: per skill the 1-2 best resources, the proof project and the check-in date.
5. After they study: `jobhunt ramp-up log "<skill>" --hours N --note "what I built"`, then `jobhunt assess "<skill>"`.
6. Only when it is true and evidenced, add the skill to the CV (`cv-review`, `tailor`). Never add skills they have
   not used.
7. Never claim a course exists beyond what the links show; links are searches, not endorsements.
