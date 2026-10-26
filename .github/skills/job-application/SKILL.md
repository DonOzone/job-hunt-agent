---
name: job-application
description: Tailor a CV and create a matching cover letter for one selected job, with requirements evidence, change review and human approval. Use when asked to match a CV to a posting, create both application documents or prepare an application for a named person.
---

# One job -> truthful CV + cover letter

1. Select the person first. For a named person, put `--person <id>` on EVERY command below, e.g.
   `jobhunt --person jane application 1`. Never reuse another person's CV, achievements, answers or browser session.
   Bootstrap with `init`, then `cv-import "<CV>" --populate-profile`. Review extracted contacts and fill target roles,
   work rights, languages, salary and preferences yourself. No country or work rights can be inferred from a CV.
2. Add/select the posting: `jobhunt add <url>` or `add --file posting.txt`, then `jobhunt fit <job>`.
3. `jobhunt application <job>` builds the application kit (same gates as `prepare`).
   It includes `requirements.md`, `cv-changes.diff`, CV draft `.md/.docx`, cover letter `.md/.docx`,
   fit/CV reports, form answers, research notes, interview prep and a checklist. The baseline is unchanged.
4. Read every requirement in `posting.md`, not just recognised keywords. Walk through `requirements.md` and the diff:
   surface relevant existing evidence, improve wording without inflating scope, and flag genuine gaps.
   Never promise a perfect match or add unverified skills, numbers, titles, employers, dates or credentials.
   Ask for evidence before including newly confirmed experience; update the baseline only with consent.
5. Complete company research with sourced facts (`jobhunt research <job>`); personalise the letter's "why us?"
   and choose actual CV achievements. Remove all placeholders. Missing experience is a gap, not a keyword to insert.
6. Save approved edits as `cv-final.md` and `cover-letter-final.md` in the kit folder. Run `jobhunt review <job>`;
   resolve blockers and material warnings, then `jobhunt cv-export <kit>/cv-final.md --out <kit>/cv-final.docx`.
   Initial Word files are draft snapshots; editing Markdown does not update Word automatically.
7. With the person's consent, `jobhunt apply <job> --cv <kit>/cv-final.docx` uploads that exact CV.
   Supply the reviewed cover letter manually if the form asks. The person reviews and submits.
   Record manual submissions with `track add <job> applied`; schedule follow-ups.

Detailed diagrams and commands: [Application workflows](../../../docs/workflows.md).
