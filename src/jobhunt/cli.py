"""jobhunt - your local job-hunt agent. Run `jobhunt doctor` first, then `jobhunt daily`."""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

from . import __version__, assessment, gaps, insights, interview, journal, memory, rampup, ranking, tailor
from .config import (
    Profile,
    default_profile_path,
    default_sites_path,
    load_dotenv,
    load_sites,
    person_scope,
    personal_dir,
    workspace_dir,
)
from .cv import extract_skills, match_job, read_cv
from .matcher import filter_jobs
from .notify import Notifier
from .store import find_job, load_jobs, mark_new, save_jobs
from .tracker import STATUSES, Tracker

ROOT = Path(__file__).resolve().parents[2]


def _profile(args) -> Profile:
    path = Path(args.profile)
    if not path.exists():
        sys.exit(f"Profile {path} not found. Run `jobhunt init` and edit it.")
    return Profile.load(path)


def _cv_skills(args, profile: Profile) -> set[str]:
    path = getattr(args, "cv", None) or profile.cv_path
    if not path:
        return set()
    if not Path(path).exists():
        sys.exit(f"CV not found: {path}")
    return set(extract_skills(read_cv(path)))


def _jobs() -> list:
    jobs = load_jobs()
    if not jobs:
        sys.exit("No saved jobs. Run `jobhunt search` first.")
    return jobs


def _write(name: str, text: str) -> Path:
    path = workspace_dir() / name
    path.write_text(text, encoding="utf-8")
    return path


def _cv_text(args, profile: Profile, required: str = "") -> tuple[str, str]:
    path = getattr(args, "cv", None) or profile.cv_path
    if not path or not Path(path).exists():
        if required:
            sys.exit(f"{required} needs your CV: set cv_path in config/profile.yaml or pass --cv")
        return "", ""
    return read_cv(path), path


def _sync_memory(job_id: str, status: str, note: str | None = None, job=None) -> None:
    """Keep reviewed-jobs memory in step with the application tracker."""
    decision = {"applied": "applied", "skipped": "skip", "withdrawn": "closed", "rejected": "closed",
                "declined": "closed", "ghosted": "closed"}.get(status, "applied" if status in
                                                              ("screening", "assessment", "interview", "final",
                                                               "offer", "accepted") else None)
    try:
        job = job or find_job(job_id)
    except KeyError:
        return
    if decision or note:
        fields = {"status": status, "note": note}
        if decision:
            fields["decision"] = decision
        memory.remember(job, **fields)


def _confirm(question: str, default: bool = True, assume: bool = False) -> bool:
    if assume or not sys.stdin.isatty():
        return default if not assume else True
    answer = input(f"{question} [{'Y/n' if default else 'y/N'}] ").strip().lower()
    return default if not answer else answer.startswith("y")


# --- commands ---------------------------------------------------------------
def cmd_init(args) -> None:
    cfg = Path(args.dir) if args.dir else default_profile_path().parent
    if args.person and args.dir:
        sys.exit("With --person, init uses me/profiles/<person>/; omit --dir.")
    cfg.mkdir(parents=True, exist_ok=True)
    pairs = [(ROOT / "config" / f"{n}.example.yaml", cfg / f"{n}.yaml") for n in ("profile", "sites")]
    pairs.append((ROOT / ".env.example", Path(".env")))
    for src, dst in pairs:
        if dst.exists():
            print(f"exists:  {dst}")
        elif src.exists():
            shutil.copy(src, dst)
            if args.person and dst.name == "profile.yaml":
                import yaml

                # Never inherit the sample person's claims, work rights or application answers.
                dst.write_text(yaml.safe_dump({"name": "", "email": "", "cv_path": "",
                                               "prefer_remote": False, "open_to_relocation": False},
                                              sort_keys=False), encoding="utf-8")
            print(f"created: {dst}")
    print(f"workspace: {workspace_dir().resolve()}")
    print(f"\nNext: populate {cfg / 'profile.yaml'} with `jobhunt profile-from-cv <CV>`, "
          "review it (roles, regions, work rights), then run `jobhunt doctor`.")


def cmd_search(args) -> None:
    from .sources import collect

    profile = _profile(args)
    jobs = collect(load_sites(args.sites))
    print(f"Collected {len(jobs)} jobs")
    if not args.no_filter:
        jobs = filter_jobs(jobs, profile.requirement, profile.fx_to_usd)
        print(f"{len(jobs)} match your requirement")
    _finish_search(args, profile, jobs)


def _finish_search(args, profile: Profile, jobs: list) -> None:
    from .sources import dedupe

    mine = memory.my_jobs()
    jobs = dedupe(jobs + mine) if mine else jobs
    skipped = memory.skipped_ids()
    if skipped:
        before = len(jobs)
        jobs = [j for j in jobs if j.id not in skipped]
        if before != len(jobs):
            print(f"Hid {before - len(jobs)} job(s) you marked skip/closed (`jobhunt memory list` to see them)")
    cv = _cv_skills(args, profile)
    for job in jobs:
        match_job(cv, job)
    new = mark_new(jobs)
    jobs = ranking.rank_jobs(jobs, profile, mode=getattr(args, "mode", None))
    save_jobs(jobs)
    report = _write("ranked-jobs.md", ranking.render_markdown(jobs, profile))
    for job in jobs[: args.top]:
        print(f"{job.rank:>3}. {job.short()}  match={job.match_score or 0:.0%}")
    journal.log(f"Search: {len(jobs)} matching jobs ({new} new)", tags=["search"])
    print(f"\n{new} new since last search. Report: {report}")


def cmd_import(args) -> None:
    from .enrich import enrich
    from .sources import dedupe, file_import

    profile = _profile(args)
    imported = [enrich(j) for j in file_import.load({"paths": args.files})]
    print(f"Imported {len(imported)} jobs from {len(args.files)} file(s)")
    if not args.no_filter:
        imported = filter_jobs(imported, profile.requirement, profile.fx_to_usd)
        print(f"{len(imported)} match your requirement")
    _finish_search(args, profile, dedupe(load_jobs() + imported))


def cmd_show(args) -> None:
    profile = _profile(args)
    job = find_job(args.job)
    m = match_job(_cv_skills(args, profile), job)
    visa = {True: "offered", False: "NOT offered", None: "not stated"}[job.visa_sponsorship]
    print(f"{job.title} @ {job.company}\n{job.url}\n")
    print(f"Rank {job.rank} | region {job.region} | {'remote' if job.remote else 'onsite/hybrid'} | "
          f"relocation {'yes' if job.relocation else 'not stated'} | visa {visa}")
    if job.salary_mid:
        print(f"Package: {job.currency or ''} {job.salary_min or 0:,.0f} - {job.salary_max or job.salary_min:,.0f} /yr")
    print(f"CV match {m.score:.0%}\n  ✅ {', '.join(m.matched) or '-'}\n  ❌ {', '.join(m.missing) or '-'}")
    print(f"First seen: {job.first_seen or '-'} | source: {job.source}\n")
    print(job.description[: args.chars] + ("..." if len(job.description) > args.chars else ""))


def cmd_tailor(args) -> None:
    profile = _profile(args)
    path = getattr(args, "cv", None) or profile.cv_path
    if not path or not Path(path).exists():
        sys.exit("tailor needs your CV: set cv_path in config/profile.yaml or pass --cv")
    job = find_job(args.job)
    out = workspace_dir() / "tailoring"
    out.mkdir(exist_ok=True)
    text = tailor.render(job, profile, read_cv(path))
    (out / f"{job.id}.md").write_text(text, encoding="utf-8")
    print(text)
    print(f"Saved: {out / f'{job.id}.md'}")


def _read_paste() -> str:
    print("Paste the job description, then press Ctrl-D (macOS/Linux) or Ctrl-Z then Enter (Windows):")
    return sys.stdin.read()


def cmd_add(args) -> None:
    """Add a job you found yourself (URL and/or pasted text). It is kept across searches and remembered."""
    from . import fit, guard
    from .enrich import enrich
    from .sources import posting

    profile = _profile(args)
    text = Path(args.file).read_text(encoding="utf-8") if args.file else (_read_paste() if args.paste else "")
    if text.strip():
        job = posting.from_text(text, args.url or "", args.title or "", args.company or "", args.location or "")
    elif args.url:
        try:
            job = posting.fetch(args.url)
        except Exception as exc:  # network blocked, 403, login wall...
            sys.exit(f"Couldn't read {args.url}: {exc}\nCopy the description and run: "
                     f"jobhunt add \"{args.url}\" --paste   (or --file description.txt)")
    else:
        sys.exit("Give a URL and/or the description: jobhunt add <url> [--paste | --file job.txt]")
    job.title = args.title or job.title
    job.company = args.company or job.company or guard.verify_host(job.url)[0]
    job.location = args.location or job.location
    job.remote = job.remote or args.remote
    if args.salary:
        job.description += f"\nSalary: {args.salary}"
    integrity = guard.check(job.description, job.url, job.company)
    job.description = integrity.cleaned
    if integrity.hidden_removed:
        job.tags.append("integrity:hidden-removed")
    if integrity.instructions:
        job.tags.append("integrity:instructions-removed")
    job.id = ""
    job.__post_init__()
    enrich(job)
    if not job.title.strip():
        sys.exit("Couldn't work out the job title - pass --title")
    cv_text, _ = _cv_text(args, profile)
    report = fit.evaluate(job, profile, cv_text, set(extract_skills(cv_text)), integrity)
    memory.save_my_job(job)
    memory.remember(job, decision="shortlist" if not report.blocked else "new", fit=report.to_dict(),
                    note=args.note, integrity=integrity.to_dict())
    jobs = [j for j in load_jobs() if j.id != job.id] + [job]
    jobs = ranking.rank_jobs(jobs, profile)
    save_jobs(jobs)
    _write("ranked-jobs.md", ranking.render_markdown(jobs, profile))
    journal.log(f"Added job: {job.title} @ {job.company} (fit {report.overall})", tags=["add", job.id])
    print(fit.render(report))
    print(f"Saved as [{job.id}] (rank {job.rank}). It stays in your list across searches.")
    print(f"Next: jobhunt prepare {job.id}   (application kit)  |  jobhunt memory note {job.id} \"...\"")


def cmd_fit(args) -> None:
    from . import fit

    profile = _profile(args)
    cv_text, _ = _cv_text(args, profile)
    cv = set(extract_skills(cv_text))
    jobs = [find_job(args.job)] if args.job else _jobs()[: args.top]
    for job in jobs:
        report = fit.evaluate(job, profile, cv_text, cv)
        memory.remember(job, fit=report.to_dict())
        if args.job:
            print(fit.render(report))
        else:
            gates = " ".join(f"{g.icon}{g.name[:4]}" for g in [*report.gates, report.logistics])
            print(f"{report.overall:>3}/100 {gates}  {job.short()}\n        {report.recommendation}")


def cmd_prepare(args) -> None:
    """Help apply to the job you picked: fit check -> application kit -> tracker -> (optional) browser assistant."""
    from . import fit, kit

    profile = _profile(args)
    cv_text, cv_path = _cv_text(args, profile, required="prepare")
    job = find_job(args.job)
    report = fit.evaluate(job, profile, cv_text, set(extract_skills(cv_text)))
    print(fit.render(report))
    memory.remember(job, fit=report.to_dict())
    if report.blocked and not args.force:
        memory.remember(job, note="prepare stopped: gate failed")
        sys.exit("Stopped: a gate failed (see above). If you know you qualify, re-run with --force.")
    if report.integrity.scam_signals and not args.force:
        sys.exit("Stopped: possible scam signals. Verify the employer independently, then use --force.")
    if not _confirm(f"Build the application kit for {job.title} @ {job.company}?", assume=args.yes):
        memory.remember(job, decision="skip" if _confirm("Mark it as skipped?", default=False) else None)
        return
    tr = Tracker()
    try:
        app_id = tr.add(job, "saved", "picked for application")
        tr.update(app_id, "applying", "application kit prepared")
    finally:
        tr.close()
    files = kit.build(job, profile, cv_text, cv_path, report, app_id, docx=not args.no_docx)
    memory.remember(job, decision="preparing", app_id=app_id,
                    outputs={k: str(v) for k, v in files.items()})
    journal.log(f"Prepared application kit: {job.title} @ {job.company} (fit {report.overall})",
                tags=["prepare", job.id])
    folder = next(iter(files.values())).parent
    print(f"\nApplication kit ready in {folder}:")
    for name in files:
        print(f"  - {name}")
    Notifier(profile.notify).send(f"Application kit ready: {job.title} @ {job.company}",
                                  f"Fit {report.overall}/100. Open {folder / 'checklist.md'} and work top to bottom.")
    if args.apply or (sys.stdin.isatty() and not args.yes and _confirm(
            "Open the browser assistant now to fill the form?", default=False)):
        args.auto_submit = False
        args.dry_run = False
        cmd_apply(args)
    else:
        print(f"\nWhen your CV/cover letter are final: jobhunt apply {job.id}   (or apply manually, then "
              f"`jobhunt track update {app_id} applied`)")


def cmd_pick(args) -> None:
    """Interactive menu: choose a job from your ranked list (and your own jobs) and get help applying."""
    jobs = _jobs()
    shown = jobs[: args.top]
    for job in shown:
        rec = memory.get(job.id) or {}
        tag = f" [{rec['decision']}]" if rec.get("decision") not in (None, "new") else ""
        print(f"{job.rank:>3}. {job.short()}  match={job.match_score or 0:.0%}{tag}")
    choice = args.job or input("\nPick a job (rank number or id, Enter to cancel): ").strip()
    if not choice:
        return
    args.job = choice
    cmd_prepare(args)


def cmd_memory(args) -> None:
    if args.action == "list":
        recs = sorted(memory.records().values(), key=lambda r: r.get("last_reviewed", ""), reverse=True)
        if args.decision:
            recs = [r for r in recs if r.get("decision") == args.decision]
        mine = {j.id for j in memory.my_jobs()}
        for r in recs:
            fit_score = (r.get("fit") or {}).get("overall", "-")
            print(f"[{r['id']}] {'✍ ' if r['id'] in mine else ''}{r['title']} @ {r['company']} | fit {fit_score} | "
                  f"{r.get('decision')} | {r.get('last_reviewed', '')[:16]}")
        print(f"\n{len(recs)} record(s). Full view: {memory.render_markdown()}")
        return
    if not args.job:
        sys.exit(f"jobhunt memory {args.action} <job id or rank> ...")
    job = find_job(args.job)
    if args.action == "show":
        rec = memory.get(job.id)
        print(json.dumps(rec, indent=2, ensure_ascii=False) if rec else "Not reviewed yet.")
    elif args.action == "note":
        if not args.text:
            sys.exit('jobhunt memory note <job> "what you learned"')
        memory.remember(job, note=args.text)
        journal.log(f"{job.title} @ {job.company}: {args.text}", kind="learning", tags=["job", job.id])
        print("Noted.")
    elif args.action == "decide":
        if args.text not in memory.DECISIONS:
            sys.exit(f"decision must be one of {', '.join(memory.DECISIONS)}")
        memory.remember(job, decision=args.text)
        print(f"{job.title} @ {job.company} -> {args.text}")


def cmd_cv_review(args) -> None:
    from . import cv_review

    profile = _profile(args)
    cv_text, cv_path = _cv_text(args, profile, required="cv-review")
    if args.job:
        jobs = [find_job(args.job)]
        target = f"{jobs[0].company} {jobs[0].title}"
    else:
        jobs = _jobs()
        if args.mine:
            mine = {j.id for j in memory.my_jobs()}
            jobs = [j for j in jobs if j.id in mine]
        if args.role:
            from .matcher import title_matches

            jobs = [j for j in jobs if title_matches(j.title, [args.role])]
        jobs = jobs[: args.top]
        if not jobs:
            sys.exit("No jobs to review against - try without --role/--mine, or `jobhunt add` a job first.")
        target = args.role or ("my jobs" if args.mine else f"top {len(jobs)} jobs")
    rev = cv_review.review(cv_text, jobs, target)
    paths = cv_review.save(cv_text, cv_path, rev, docx=not args.no_docx)
    for job in jobs if args.job else []:
        memory.remember(job, outputs={"cv-review": str(paths["report"]), "cv-draft": str(paths["draft"])})
    trend = (f" (was {rev.previous_score:.0%})" if rev.previous_score is not None else "")
    print(f"ATS keyword score vs {target}: {rev.score:.0%}{trend}")
    print(f"Missing (add only if true): {', '.join(s for s, _ in rev.missing[:8]) or '-'}")
    print(f"Bullets to improve: {len(rev.bullets)} | buried skills: {', '.join(rev.buried) or '-'}")
    for ok, msg in rev.checks:
        if not ok:
            print(f"  ❌ {msg}")
    for name, path in paths.items():
        print(f"{name:>8}: {path}")
    journal.log(f"CV review vs {target}: {rev.score:.0%}{trend}", kind="learning", tags=["cv-review"])


def cmd_cv_import(args) -> None:
    """Make an existing CV (.docx/.pdf/.md) your editable markdown baseline in the house format."""
    from .cv_format import lint

    if args.populate_profile and args.no_profile:
        sys.exit("--populate-profile cannot be combined with --no-profile")
    src = Path(args.file)
    if not src.exists():
        sys.exit(f"{src} not found")
    dest_dir = Path(args.dir) if args.dir else personal_dir() / "cv"
    (dest_dir / "originals").mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() != ".md":
        shutil.copy(src, dest_dir / "originals" / src.name)
    dest = dest_dir / f"{args.name or src.stem}.md"
    if dest.exists() and not args.yes and not _confirm(f"{dest} exists - overwrite?", default=False):
        sys.exit("Cancelled.")
    dest.write_text(read_cv(src), encoding="utf-8")
    print(f"Baseline CV: {dest}  (edit this file; it is git-ignored)")
    prof = Path(args.profile)
    if not args.no_profile and prof.exists():
        import re

        text = prof.read_text(encoding="utf-8")
        line = f"cv_path: {dest.as_posix()}"
        text, n = re.subn(r"(?m)^cv_path:.*$", line, text)
        prof.write_text(text if n else f"{line}\n{text}", encoding="utf-8")
        print(f"{prof}: {line}")
    for issue in lint(dest.read_text(encoding="utf-8")):
        print(f"  ⚠ {issue}")
    if args.populate_profile:
        _populate_profile(prof, dest)
    print("Next: jobhunt cv-export   (Word copy in the same format)  |  jobhunt cv-review <job>")
    journal.log(f"Imported CV baseline from {src.name}", tags=["cv"])


def _populate_profile(profile: Path, cv: Path) -> None:
    from .profiles import populate

    filled, conflicts = populate(profile, read_cv(cv), cv)
    print(f"Profile: {profile}\nFilled from CV: {', '.join(filled) or 'no empty fields'}")
    if conflicts:
        print(f"Kept existing values for: {', '.join(conflicts)}. Review these fields manually.")
    print("Check all extracted contacts. Set target roles, regions, work rights, salary and answers yourself; "
          "they are never inferred from a CV.")


def cmd_profile_from_cv(args) -> None:
    cv = args.file or args.cv
    if not cv:
        cv = _profile(args).cv_path
    if not cv or not Path(cv).is_file():
        sys.exit("Give a CV file or import a baseline first: jobhunt profile-from-cv <CV>")
    _populate_profile(Path(args.profile), Path(cv))


def cmd_profiles(args) -> None:
    ids = sorted(p.parent.name for p in (Path("me") / "profiles").glob("*/profile.yaml"))
    print("\n".join(ids) if ids else "No named profiles. Start with: jobhunt --person jane init")
    print("Select explicitly for every command: jobhunt --person <id> <command>")


def cmd_cv_export(args) -> None:
    """Render a markdown CV (default: your baseline) to .docx in the house format."""
    from .cv_format import lint, markdown_to_docx

    profile = _profile(args) if Path(args.profile).exists() else None
    src = Path(args.file or getattr(args, "cv", None) or (profile.cv_path if profile else "") or "")
    if not src.is_file() or src.suffix.lower() not in (".md", ".txt"):
        sys.exit("Give a markdown CV: jobhunt cv-export path/to/cv.md  (or set cv_path to a .md file)")
    text = src.read_text(encoding="utf-8")
    out = markdown_to_docx(text, Path(args.out) if args.out else src.with_suffix(".docx"),
                           page="a4" if args.a4 else "letter")
    print(f"Word CV: {out}")
    for issue in lint(text):
        print(f"  ⚠ {issue}")


def cmd_rank(args) -> None:
    profile = _profile(args)
    order = tuple(o.strip() for o in args.order.split(","))
    bad = set(order) - set(ranking.DEFAULT_ORDER)
    if bad:
        sys.exit(f"Unknown order keys {bad}; use {ranking.DEFAULT_ORDER}")
    jobs = ranking.rank_jobs(_jobs(), profile, order, mode=args.mode)
    profile.ranking_mode = args.mode or profile.ranking_mode
    save_jobs(jobs)
    print(f"Report: {_write('ranked-jobs.md', ranking.render_markdown(jobs, profile))}")
    for job in jobs[: args.top]:
        print(f"{job.rank:>3}. {job.short()}")


def cmd_list(args) -> None:
    hidden = set() if args.all else memory.skipped_ids()
    jobs = [j for j in _jobs() if j.id not in hidden]
    for job in jobs[: args.top]:
        flag = f" [{memory.get(job.id)['decision']}]" if memory.get(job.id) else ""
        print(f"{job.rank:>3}. {job.short()}  match={job.match_score or 0:.0%}{flag}")
    if not jobs and not hidden:
        print("No jobs yet. Run `jobhunt search` or add one: jobhunt add <url> --paste")
    if hidden:
        print(f"({len(hidden)} skipped/closed job(s) hidden - `jobhunt list --all` to show)")


def cmd_cv(args) -> None:
    profile = _profile(args)
    cv = _cv_skills(args, profile)
    print(f"CV skills ({len(cv)}): {', '.join(sorted(cv)) or 'none detected'}\n")
    jobs = _jobs()
    results = [match_job(cv, j) for j in jobs]
    save_jobs(jobs)
    for job, m in sorted(zip(jobs, results, strict=True), key=lambda x: -x[1].score)[: args.top]:
        print(f"{m.score:>4.0%}  {job.short()}")
        print(f"      ✅ {', '.join(m.matched) or '-'}\n      ❌ {', '.join(m.missing) or '-'}")


def cmd_gaps(args) -> None:
    profile = _profile(args)
    jobs = _jobs()[: args.jobs] if args.jobs else _jobs()
    found, strengths = gaps.analyse(jobs, _cv_skills(args, profile), gaps.decision_weights(memory.records()))
    path = _write("skill-gaps.md", gaps.render_markdown(found, strengths, len(jobs), args.top))
    for i, g in enumerate(found[: args.top], 1):
        print(f"{i:>2}. {g.skill:<22} importance={g.importance:>5.1f}  jobs={g.jobs}  -> {g.courses[0]['name']}")
    journal.log(f"Gap analysis: top gaps {', '.join(g.skill for g in found[:5])}", kind="learning", tags=["gaps"])
    print(f"\nReport: {path}")


def cmd_ramp_up(args) -> None:
    words = args.words
    if words and words[0] == "log":
        if len(words) < 2:
            sys.exit('usage: jobhunt ramp-up log "<skill>" [--hours N] [--note "what I built"]')
        skill = rampup._canon(" ".join(words[1:]))
        hrs = f" ({args.hours:g} h)" if args.hours else ""
        journal.log(f"Ramp-up: worked on {skill}{hrs}" + (f" - {args.note}" if args.note else ""),
                    kind="learning", tags=["ramp-up", skill])
        print(f"Logged. Next: `jobhunt assess \"{skill}\"` to check yourself before adding it to your CV.")
        return
    if words:
        sys.exit("usage: jobhunt ramp-up [--skills A,B] [--resources FILE] | jobhunt ramp-up log <skill>")
    try:
        user = rampup.load_user_resources(args.resources)
    except FileNotFoundError as e:
        sys.exit(str(e))
    named = [x.strip() for x in (args.skills or "").split(",") if x.strip()]
    found = []
    if not named or args.with_gaps:
        found, _ = gaps.analyse(_jobs(), _cv_skills(args, _profile(args)), gaps.decision_weights(memory.records()))
    steps = rampup.build(found, user, named, args.max_skills, args.free)
    if not steps:
        sys.exit("No gaps found. Add jobs (`jobhunt search` / `jobhunt add`) or name skills with --skills.")
    text = rampup.render(steps, args.hours_per_week, user_count=len(user),
                         leftover=rampup.unused_user_skills(user, steps))
    path = _write("ramp-up.md", text)
    print(text)
    journal.log(f"Ramp-up plan: {', '.join(st.skill for st in steps)}", kind="learning", tags=["ramp-up"])
    print(f"Saved: {path}")


def cmd_study_plan(args) -> None:
    profile = _profile(args)
    found, _ = gaps.analyse(_jobs(), _cv_skills(args, profile), gaps.decision_weights(memory.records()))
    path = _write("study-plan.md", assessment.study_plan(found, args.hours, args.skills))
    print(path.read_text(encoding="utf-8"))
    print(f"Saved: {path}")


def cmd_assess(args) -> None:
    if args.list:
        bank = assessment.question_bank()
        print("Quizzes available:", ", ".join(f"{k} ({len(v)})" for k, v in sorted(bank.items())))
        print("Any other skill uses a structured self-assessment (--self).")
        return
    if not args.skill:
        sys.exit("usage: jobhunt assess <skill> [--self | --export | --answers a,b,c]")
    seed = args.seed if args.seed is not None else date.today().toordinal()
    if args.export:
        print(json.dumps(assessment.export_quiz(args.skill, args.n, seed), indent=2))
        print(f"\nScore with: jobhunt assess \"{args.skill}\" -n {args.n} --seed {seed} --answers a,b,...")
        return
    if args.answers:
        answers = iter(a.strip() for a in args.answers.split(","))
        score, detail = assessment.run_quiz(args.skill, args.n, ask=lambda _: next(answers, ""), seed=seed)
    elif args.self:
        score, detail = assessment.self_assess(args.skill)
    else:
        score, detail = assessment.run_quiz(args.skill, args.n, seed=seed)
    tr = Tracker()
    tr.record_assessment(args.skill, score, "self" if detail.startswith("self") else "quiz", detail)
    tr.close()
    lvl = assessment.level(score)
    print(f"\n{args.skill}: {score:.0%} ({lvl}) — {detail}")
    journal.log(f"Assessed {args.skill}: {score:.0%} ({lvl})", kind="learning", tags=["assessment", args.skill])


def cmd_eligibility(args) -> None:
    profile = _profile(args)
    cv = _cv_skills(args, profile)
    tr = Tracker()
    prof = tr.proficiency()
    tr.close()
    jobs = [find_job(args.job)] if args.job else _jobs()[: args.top]
    for job in jobs:
        e = assessment.eligibility(job, cv, prof)
        print(f"{e.score:>4.0%}  {job.short()}\n      {e.verdict}")
        if e.blockers:
            print(f"      blockers: {', '.join(e.blockers)} -> `jobhunt assess <skill>` after studying")


def cmd_interview(args) -> None:
    profile = _profile(args)
    cv = _cv_skills(args, profile)
    jobs = [find_job(args.job)] if args.job else _jobs()[: args.top]
    for job in jobs:
        print(f"Prep pack: {interview.write_pack(job, cv)}")


def cmd_mock_interview(args) -> None:
    from . import mock_interview

    if args.limit <= 0:
        sys.exit("--limit must be positive")
    if bool(args.job) == (args.application is not None):
        sys.exit("Select a job ID/rank OR --application <application-id>, not both")
    if args.application is not None:
        tr = Tracker()
        try:
            application = tr.get(args.application)
            if application is None:
                sys.exit(f"Application {args.application} not found for the selected person")
            job = find_job(application["job_id"])
        finally:
            tr.close()
    else:
        job = find_job(args.job)
    cards = mock_interview.deck(job, _cv_skills(args, _profile(args)))
    if bool(args.rate) != bool(args.rating):
        sys.exit("--rate <card-id> and --rating know|dont-know must be supplied together")
    if args.answer is not None and not args.rate:
        sys.exit("--answer requires --rate and --rating")
    if args.rate:
        mock_interview.rate(job, cards, args.rate, args.rating, args.answer or "")
    elif not args.list:
        if not sys.stdin.isatty():
            sys.exit("Interactive practice needs a terminal. Use --list, or --rate <card-id> --rating know|dont-know.")
        chosen = mock_interview.select(job, cards, args.weak_only)[:args.limit]
        if not chosen:
            print("No cards rated 'I don't know' yet. Use --list or start without --weak-only.")
        else:
            try:
                mock_interview.run(job, chosen, args.mode, input, print)
            except (EOFError, KeyboardInterrupt):
                print("\nPractice stopped; completed ratings have been saved.")
    path = mock_interview.write_report(job, cards)
    print(path.read_text(encoding="utf-8") if args.list else f"Practice and learning review: {path}")
    if args.list:
        print(f"Saved: {path}")


def cmd_apply(args) -> None:
    from .apply import ApplyAssistant

    profile = _profile(args)
    if args.cv:
        if not Path(args.cv).is_file():
            sys.exit(f"CV not found: {args.cv}")
        profile = replace(profile, cv_path=args.cv)
    job = find_job(args.job)
    missing = match_job(_cv_skills(args, profile), job).missing
    tr = Tracker()
    try:
        res = ApplyAssistant(profile, tr, Notifier(profile.notify), headless=args.headless).apply(
            job, auto_submit=args.auto_submit, dry_run=args.dry_run, missing_skills=missing)
    finally:
        tr.close()
    print(f"Application #{res.app_id}: {res.status}")
    _sync_memory(job.id, res.status, "via apply assistant", job)


def cmd_track(args) -> None:
    tr = Tracker()
    try:
        if args.action == "add":
            app_id = tr.add(find_job(args.target), args.status or "saved", args.note or "")
            print(f"Tracking application #{app_id}")
        elif args.action == "update":
            tr.update(int(args.target), args.status, args.note or "", args.next, args.due)
            row = tr.get(int(args.target))
            _sync_memory(row["job_id"], args.status, args.note)
            print(f"#{row['id']} {row['title']} @ {row['company']} -> {row['status']}")
            kind = "win" if args.status in ("interview", "offer", "accepted") else \
                "setback" if args.status in ("rejected", "failed", "ghosted") else "progress"
            journal.log(f"{row['title']} @ {row['company']}: {args.status}. {args.note or ''}", kind=kind,
                        tags=["application"])
        elif args.action == "list":
            for r in tr.list(args.status):
                print(f"#{r['id']:<4} {r['updated_at']}  {r['status']:<11} {r['title']} @ {r['company']}")
        elif args.action == "history":
            for e in tr.history(int(args.target)):
                print(f"{e['ts']}  {e['status']:<11} {e['note'] or ''}")
        elif args.action == "report":
            path = _write("applications-report.md", tr.report_markdown())
            print(json.dumps({k: v for k, v in tr.summary().items()}, indent=2))
            print(f"Report: {path}")
        elif args.action == "followups":
            args.days = args.days or 7
            rows = tr.stale(args.days)
            profile = _profile(args) if Path(args.profile).exists() else Profile()
            out = workspace_dir() / "followups"
            out.mkdir(exist_ok=True)
            for r in rows:
                sent = tr.followups_sent(r["id"])
                print(f"#{r['id']} {r['title']} @ {r['company']} - {r['status']}, quiet {tr.days_quiet(r['id'])} "
                      f"days, {sent} follow-up(s) sent")
                if sent >= 2:
                    print("   Two follow-ups already - time to move on: `jobhunt track sweep`")
                    continue
                path = out / f"{date.today().isoformat()}-app{r['id']}.md"
                path.write_text(_followup_note(r, profile, sent), encoding="utf-8")
                print(f"   Draft: {path}  (after sending: jobhunt track sent {r['id']})")
            if rows:
                Notifier(profile.notify).send(
                    "Follow-ups due", f"{len(rows)} application(s) quiet for {args.days}+ days. "
                    f"Drafts are in {out}.")
            else:
                print("Nothing to follow up 🎉")
        elif args.action == "sent":
            tr.log_event(int(args.target), f"follow-up sent{': ' + args.note if args.note else ''}")
            print(f"Logged follow-up for #{args.target} (the quiet clock restarts).")
        elif args.action == "sweep":
            days = args.days or 60
            rows = tr.stale(days)
            if not rows:
                print(f"No open applications quiet for {days}+ days.")
            for r in rows:
                print(f"#{r['id']} {r['title']} @ {r['company']} - {r['status']}, quiet {tr.days_quiet(r['id'])} days")
            if rows and _confirm(f"Mark these {len(rows)} as ghosted?", default=False, assume=args.yes):
                for r in rows:
                    tr.update(r["id"], "ghosted", f"no response after {days}+ days (sweep)")
                    _sync_memory(r["job_id"], "ghosted", "sweep")
                journal.log(f"Closed {len(rows)} quiet application(s) as ghosted", kind="setback",
                            tags=["application"])
                print("Done. Ghosting is about their process, not your worth - keep the pipeline full.")
        elif args.action == "dashboard":
            from . import dashboard

            path = _write("dashboard.html", dashboard.render(tr))
            print(f"Dashboard: {path}  (open it in your browser)")
    finally:
        tr.close()


def _followup_note(row, profile: Profile, sent: int) -> str:
    applied = (row["created_at"] or "")[:10]
    name = profile.name or "<Your name>"
    sign = (profile.writing_style or {}).get("sign_off") or "Best regards"
    second = sent >= 1
    return "\n".join([
        f"<!-- Follow-up {'#2 (last one)' if second else '#1'} for application #{row['id']}. Edit, send by email or "
        f"LinkedIn, then run: jobhunt track sent {row['id']} -->",
        "",
        f"Subject: {row['title']} application - {'checking in again' if second else 'following up'}",
        "",
        f"Hi {row['company']} team,",
        "",
        f"I applied for the {row['title']} role{' on ' + applied if applied else ''} and wanted to "
        + ("check in once more." if second else "follow up on my application."),
        "<One line: what draws you to the role or a recent relevant result - specific, not generic.>",
        "",
        ("If the position has been filled, I'd appreciate a quick note so I can close the loop - and I'd be glad "
         "to be considered for similar roles." if second else
         "I'm happy to share anything else that would help with your decision."),
        "",
        f"{sign},",
        name,
    ]) + "\n"


def cmd_review(args) -> None:
    """Hiring-manager-style review of the application kit for a job."""
    from . import kit, review

    profile = _profile(args)
    cv_text, _ = _cv_text(args, profile, required="review")
    job = find_job(args.job)
    folder = kit.folder(job)
    if not any(folder.iterdir()):
        sys.exit(f"No application kit yet. Run: jobhunt prepare {job.id}")
    rep = review.review_kit(job, folder, profile, cv_text)
    path = folder / "review.md"
    path.write_text(review.render(rep), encoding="utf-8")
    print(path.read_text(encoding="utf-8"))
    memory.remember(job, note=f"kit review {rep.score}/100")
    print(f"Saved: {path}")


def cmd_research(args) -> None:
    """Create/open the cached company research notes for a job's company."""
    from . import research

    job = find_job(args.job)
    path = research.brief(job)
    print(path.read_text(encoding="utf-8"))
    print(f"Notes file: {path}  ({'has notes' if research.is_filled(path) else 'fill in 2+ sections'})")


def cmd_journal(args) -> None:
    if args.action == "log":
        e = journal.log(args.text, kind=args.kind, tags=args.tag or [])
        print(f"{e['ts']} logged")
    else:
        for e in journal.entries(args.kind, args.limit):
            print(f"{e['ts']} [{e['kind']}] {e['text']}")


def cmd_insights(args) -> None:
    tr = Tracker()
    summary, stale = tr.summary(), len(tr.stale(7))
    tr.close()
    top = []
    if load_jobs() and Path(args.profile).exists():
        profile = _profile(args)
        found, _ = gaps.analyse(load_jobs(), _cv_skills(args, profile), gaps.decision_weights(memory.records()))
        top = [g.skill for g in found[:3]]
    print(insights.render(insights.contextual_tips(summary, stale, top), args.limit))


def cmd_doctor(args) -> None:
    """Check setup and explain exactly what to fix."""
    results: list[tuple[str, str, str]] = []

    def check(ok: bool | None, what: str, fix: str = "") -> None:
        results.append(("✅" if ok else "⚠️ " if ok is None else "❌", what, "" if ok else fix))

    check(sys.version_info >= (3, 10), f"Python {sys.version.split()[0]}", "Install Python 3.10+")
    prof_path = Path(args.profile)
    profile = None
    if prof_path.exists():
        try:
            profile = Profile.load(prof_path)
            check(True, f"Profile loaded: {prof_path}")
        except Exception as exc:  # noqa: BLE001 - report any YAML problem to the user
            check(False, f"Profile {prof_path} has an error: {exc}", "Fix the YAML (check indentation)")
    else:
        check(False, f"Profile missing: {prof_path}", "Run `jobhunt init`")
    if profile:
        missing = [k for k in ("name", "email") if not getattr(profile, k)]
        check(not missing, "Contact details set" if not missing else f"Missing: {', '.join(missing)}",
              "Fill name/email in config/profile.yaml (used by the apply assistant)")
        check(bool(profile.requirement.roles) or None, f"Target roles: {profile.requirement.roles or 'none'}",
              "Add requirement.roles, e.g. [backend engineer] - otherwise every job matches")
        check(bool(profile.preferred_regions) or None, f"Preferred regions: {profile.preferred_regions or 'none'}",
              "Add preferred_regions in priority order, e.g. [Africa, Europe, Worldwide]")
        cv = getattr(args, "cv", None) or profile.cv_path
        if not cv:
            check(None, "No CV configured", "Set cv_path - needed for matching, gaps, tailoring and interview prep")
        elif not Path(cv).exists():
            check(False, f"CV not found: {cv}", "Fix cv_path (relative to where you run jobhunt)")
        else:
            try:
                skills = extract_skills(read_cv(cv))
                check(bool(skills) or None, f"CV read: {len(skills)} skills detected",
                      "No skills recognised - add a Skills section or extend src/jobhunt/data/skills.yaml")
                if Path(cv).suffix.lower() == ".md":
                    from .cv_format import lint
                    issues = lint(Path(cv).read_text(encoding="utf-8"))
                    check(not issues or None, "CV format: OK" if not issues else f"CV format: {'; '.join(issues)}",
                          "Fix these in your markdown CV (see examples/sample_cv.md)")
                else:
                    check(None, f"CV is {Path(cv).suffix}",
                          "Run `jobhunt cv-import <file>` for a reviewable markdown baseline")
            except ImportError:
                check(False, f"Can't read {Path(cv).suffix} CV", "pip install -e \".[docs]\"")
        check(bool(profile.work_authorization) or None,
              f"Work authorization: {profile.work_authorization or 'not set'}",
              "Set work_authorization (countries you can already work in) - used by the eligibility gate")
        check(bool(profile.languages) or None, f"Languages: {profile.languages or 'not set (assuming English)'}",
              "Set languages, e.g. {English: fluent} - used by the language gate")
        channels = [k for k in ("ntfy_topic", "webhook_url", "desktop") if profile.notify.get(k)]
        check(bool(channels) or None, f"Notifications: console + {', '.join(channels) or 'nothing else'}",
              "Optional: set JOBHUNT_NTFY_TOPIC / JOBHUNT_WEBHOOK_URL in .env for phone/Teams/Slack pings")
    sites_path = Path(args.sites)
    if sites_path.exists():
        sites = load_sites(sites_path)
        check(bool(sites), f"{len(sites)} site(s) configured in {sites_path}", "Add at least one site")
        for s in sites:
            for p in s.get("paths") or []:
                check(Path(p).exists() or None, f"Import file {p}", "Create it or remove it from sites.yaml")
    else:
        check(False, f"Sites missing: {sites_path}", "Run `jobhunt init`")
    try:
        import playwright  # noqa: F401
        check(True, "Playwright installed (apply assistant + browser sources)")
    except ImportError:
        check(None, "Playwright not installed (only needed for `apply` and browser sources)",
              "pip install -e \".[browser]\" && playwright install chromium")
    ws = workspace_dir()
    check(os.access(ws, os.W_OK), f"Workspace writable: {ws.resolve()}", "Set JOBHUNT_HOME to a writable folder")
    for icon, what, fix in results:
        print(f"{icon} {what}" + (f"\n     → {fix}" if fix else ""))
    if any(r[0] == "❌" for r in results):
        sys.exit(1)
    print("\nAll set! Try: jobhunt daily")


def cmd_run(args) -> None:
    """Full daily pipeline: search -> gaps -> study plan -> interview prep -> insights -> ping."""
    cmd_search(args)
    profile = _profile(args)
    cv = _cv_skills(args, profile)
    jobs = load_jobs()
    found, strengths = gaps.analyse(jobs, cv, gaps.decision_weights(memory.records()))
    _write("skill-gaps.md", gaps.render_markdown(found, strengths, len(jobs)))
    _write("study-plan.md", assessment.study_plan(found))
    for job in jobs[: args.prep]:
        interview.write_pack(job, cv)
    tr = Tracker()
    summary, stale = tr.summary(), tr.stale(7)
    tr.close()
    tips = insights.contextual_tips(summary, len(stale), [g.skill for g in found[:3]])
    _write("insights.md", insights.render(tips))
    top = "\n".join(f"{j.rank}. {j.title} @ {j.company} ({j.region})" for j in jobs[:5])
    Notifier(profile.notify).send(
        "Daily job-hunt run complete",
        f"{len(jobs)} matching jobs. Top picks:\n{top}\n"
        f"Top gaps: {', '.join(g.skill for g in found[:3]) or 'none'}\n"
        f"Follow-ups due: {len(stale)}\nTip: {tips[0]['title'] if tips else '-'}\n"
        f"Files in {workspace_dir().resolve()}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jobhunt", description=__doc__)
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--version", action="version", version=f"jobhunt {__version__}")
    common = argparse.ArgumentParser(add_help=False)
    p.add_argument("--person", help="isolated person ID (e.g. jane); also accepted after any command")
    common.add_argument("--profile", help="profile YAML override (does not select a different workspace)")
    common.add_argument("--cv", help="CV path (overrides profile.cv_path)")
    common.add_argument("--top", type=int, default=20)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="create config/profile.yaml and config/sites.yaml")
    s.add_argument("--dir", help="config directory (default: config, or the selected person's directory)")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("doctor", parents=[common], help="check your setup and say what to fix")
    s.add_argument("--sites", help="job sites YAML (default: selected person's sites)")
    s.set_defaults(fn=cmd_doctor)

    for name, fn, hlp in (("search", cmd_search, "collect, filter and rank jobs"),
                          ("daily", cmd_run, "full daily pipeline + notification (alias: run)"),
                          ("run", cmd_run, argparse.SUPPRESS)):
        s = sub.add_parser(name, parents=[common], help=hlp)
        s.add_argument("--sites", help="job sites YAML (default: selected person's sites)")
        s.add_argument("--no-filter", action="store_true")
        s.add_argument("--mode", choices=["strict", "weighted"], help="ranking mode (default: profile)")
        s.add_argument("--prep", type=int, default=3, help="interview packs for top N jobs (daily only)")
        s.set_defaults(fn=fn)

    s = sub.add_parser("import", parents=[common], help="add jobs from CSV/JSON you saved (LinkedIn, Indeed...)")
    s.add_argument("files", nargs="+")
    s.add_argument("--no-filter", action="store_true")
    s.add_argument("--mode", choices=["strict", "weighted"])
    s.set_defaults(fn=cmd_import)

    s = sub.add_parser("show", parents=[common], help="full details for one job")
    s.add_argument("job", help="job id or rank")
    s.add_argument("--chars", type=int, default=1500)
    s.set_defaults(fn=cmd_show)

    s = sub.add_parser("tailor", parents=[common], help="CV suggestions + cover-letter draft for a job")
    s.add_argument("job", help="job id or rank")
    s.set_defaults(fn=cmd_tailor)

    s = sub.add_parser("add", parents=[common], help="add a job YOU found (URL and/or pasted description)")
    s.add_argument("url", nargs="?", help="job link (fetched automatically when allowed)")
    s.add_argument("--paste", action="store_true", help="paste the description into the terminal")
    s.add_argument("--file", help="text/markdown/html file with the description")
    s.add_argument("--title")
    s.add_argument("--company")
    s.add_argument("--location")
    s.add_argument("--salary", help='e.g. "USD 80-100k" or "KES 450,000 per month"')
    s.add_argument("--remote", action="store_true")
    s.add_argument("--note", help="why you like it / who referred you")
    s.set_defaults(fn=cmd_add)

    s = sub.add_parser("fit", parents=[common], help="gates + 5-dimension fit score (one job or top N)")
    s.add_argument("job", nargs="?", help="job id or rank")
    s.set_defaults(fn=cmd_fit, top=10)

    for name, fn, hlp in (("application", cmd_prepare, "tailor CV + cover letter and map requirements for one job"),
                         ("prepare", cmd_prepare, "help me apply to this job: fit check + application kit"),
                          ("pick", cmd_pick, "choose a job from your list, then prepare/apply")):
        s = sub.add_parser(name, parents=[common], help=hlp)
        s.add_argument("job", nargs="?" if name == "pick" else None, help="job id or rank")
        s.add_argument("-y", "--yes", action="store_true", help="don't ask for confirmation")
        s.add_argument("--force", action="store_true", help="continue even if a gate failed")
        s.add_argument("--no-docx", action="store_true", help="skip the Word copy of the CV draft")
        s.add_argument("--apply", action="store_true", help="open the browser assistant right after")
        s.add_argument("--headless", action="store_true")
        s.set_defaults(fn=fn)

    s = sub.add_parser("memory", parents=[common], help="reviewed-jobs memory: list, show, note, decide")
    s.add_argument("action", choices=["list", "show", "note", "decide"])
    s.add_argument("job", nargs="?", help="job id or rank")
    s.add_argument("text", nargs="?", help=f"note text, or decision: {', '.join(memory.DECISIONS)}")
    s.add_argument("--decision", choices=memory.DECISIONS, help="filter list")
    s.set_defaults(fn=cmd_memory)

    s = sub.add_parser("review", parents=[common], help="hiring-manager review of an application kit before sending")
    s.add_argument("job", help="job id or rank")
    s.set_defaults(fn=cmd_review)

    s = sub.add_parser("research", parents=[common], help="company research notes (cached per company)")
    s.add_argument("job", help="job id or rank")
    s.set_defaults(fn=cmd_research)

    s = sub.add_parser("cv-review", parents=[common], help="review + rewrite your CV for a job/role (draft)")
    s.add_argument("job", nargs="?", help="job id or rank (default: top N / --role / --mine)")
    s.add_argument("--role", help='only jobs whose title matches, e.g. "data engineer"')
    s.add_argument("--mine", action="store_true", help="only jobs you added yourself")
    s.add_argument("--no-docx", action="store_true", help="skip the Word copy of the draft")
    s.set_defaults(fn=cmd_cv_review, top=10)

    s = sub.add_parser("cv-import", parents=[common], help="turn your CV (.docx/.pdf/.md) into the markdown baseline")
    s.add_argument("file")
    s.add_argument("--dir", help="where to keep it (default: selected person's cv directory)")
    s.add_argument("--name", help="file name without extension (default: same as the source)")
    s.add_argument("--no-profile", action="store_true", help="don't point profile cv_path at it")
    s.add_argument("--populate-profile", action="store_true", help="also fill empty contact fields from the CV")
    s.add_argument("-y", "--yes", action="store_true")
    s.set_defaults(fn=cmd_cv_import)

    s = sub.add_parser("profile-from-cv", parents=[common], help="fill empty profile contacts from a CV (no guessing)")
    s.add_argument("file", nargs="?", help="CV file (default: selected profile's baseline)")
    s.set_defaults(fn=cmd_profile_from_cv)

    sub.add_parser("profiles", help="list local person IDs (no contact details)").set_defaults(fn=cmd_profiles)

    s = sub.add_parser("cv-export", parents=[common], help="markdown CV -> Word (.docx) in the house format")
    s.add_argument("file", nargs="?", help="markdown CV (default: profile cv_path)")
    s.add_argument("--out", help="output .docx path")
    s.add_argument("--a4", action="store_true", help="A4 paper (default US Letter)")
    s.set_defaults(fn=cmd_cv_export)

    s = sub.add_parser("rank", parents=[common], help="re-rank saved jobs")
    s.add_argument("--order", default=",".join(ranking.DEFAULT_ORDER))
    s.add_argument("--mode", choices=["strict", "weighted"])
    s.set_defaults(fn=cmd_rank)
    s = sub.add_parser("list", parents=[common], help="show saved jobs")
    s.add_argument("--all", action="store_true", help="include jobs you skipped/closed")
    s.set_defaults(fn=cmd_list)
    sub.add_parser("cv-match", parents=[common], help="match CV skills to each job").set_defaults(fn=cmd_cv)

    s = sub.add_parser("gaps", parents=[common], help="rank skill gaps + courses")
    s.add_argument("--jobs", type=int, help="only analyse top N ranked jobs")
    s.set_defaults(fn=cmd_gaps, top=15)

    s = sub.add_parser("ramp-up", parents=[common],
                       help="learning path for missing skills: your list + open materials")
    s.add_argument("words", nargs="*", help='empty to plan, or: log "<skill>"')
    s.add_argument("--skills", help="comma-separated skills to ramp up on (otherwise: your top gaps)")
    s.add_argument("--with-gaps", action="store_true", help="add your top gaps after the skills you named")
    s.add_argument("--resources", help="your learning list (default: me/learning-resources.yaml|csv|md)")
    s.add_argument("--free", action="store_true", help="hide paid materials")
    s.add_argument("--max-skills", type=int, default=5)
    s.add_argument("--hours-per-week", type=int, default=6)
    s.add_argument("--hours", type=float, help="with `log`: hours spent")
    s.add_argument("--note", help="with `log`: what you did or built")
    s.set_defaults(fn=cmd_ramp_up)

    s = sub.add_parser("study-plan", parents=[common], help="week-by-week plan to close gaps")
    s.add_argument("--hours", type=int, default=6)
    s.add_argument("--skills", type=int, default=5)
    s.set_defaults(fn=cmd_study_plan)

    s = sub.add_parser("assess", help="quiz or self-assess a skill")
    s.add_argument("skill", nargs="?")
    s.add_argument("-n", type=int, default=5)
    s.add_argument("--self", action="store_true", help="structured self-rating instead of quiz")
    s.add_argument("--list", action="store_true", help="list skills that have quizzes")
    s.add_argument("--export", action="store_true", help="print questions as JSON (for an AI agent to ask in chat)")
    s.add_argument("--answers", help="non-interactive answers, e.g. a,c,b,d,a")
    s.add_argument("--seed", type=int, help="question order (default: today's date)")
    s.set_defaults(fn=cmd_assess)

    s = sub.add_parser("eligibility", parents=[common], help="are you eligible for a job?")
    s.add_argument("job", nargs="?", help="job id or rank")
    s.set_defaults(fn=cmd_eligibility, top=10)

    s = sub.add_parser("interview-prep", parents=[common], help="build interview prep packs")
    s.add_argument("job", nargs="?", help="job id or rank (default: top N)")
    s.set_defaults(fn=cmd_interview, top=3)

    s = sub.add_parser("mock-interview", parents=[common], help="role-specific mock interview and rated flashcards")
    s.add_argument("job", nargs="?", help="job ID or rank (or use --application)")
    s.add_argument("--application", type=int, help="application tracker ID for the selected person")
    s.add_argument("--mode", choices=["interview", "flashcards"], default="interview")
    s.add_argument("--list", action="store_true", help="export question types, flashcards and learning review")
    s.add_argument("--limit", type=int, default=10, help="cards per interactive session")
    s.add_argument("--weak-only", action="store_true", help="practise only cards last rated I don't know")
    s.add_argument("--rate", help="card ID to rate (for chat agents or non-interactive use)")
    s.add_argument("--rating", choices=["know", "dont-know"])
    s.add_argument("--answer", help="optional answer to store with --rate")
    s.set_defaults(fn=cmd_mock_interview)

    s = sub.add_parser("apply", parents=[common], help="Playwright-assisted application")
    s.add_argument("job", help="job id or rank")
    s.add_argument("--auto-submit", action="store_true")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--headless", action="store_true", help="no visible browser (use with --auto-submit)")
    s.set_defaults(fn=cmd_apply)

    s = sub.add_parser("track", help="application tracker")
    s.add_argument("action", choices=["add", "update", "list", "history", "report", "followups", "sent", "sweep",
                                      "dashboard"],
                   help="followups = draft notes for quiet apps; sent = log a follow-up you sent; "
                        "sweep = close apps quiet 60+ days as ghosted; dashboard = HTML funnel")
    s.add_argument("target", nargs="?", help="job id/rank (add) or application id (update/history/sent)")
    s.add_argument("status", nargs="?", help=f"one of {sorted(STATUSES)} (list also accepts passed/failed/pending)")
    s.add_argument("--note")
    s.add_argument("--next", help="next action, e.g. 'Send thank-you email'")
    s.add_argument("--due", type=int, help="next action due in N days")
    s.add_argument("--days", type=int, help="quiet days (default: followups 7, sweep 60)")
    s.add_argument("-y", "--yes", action="store_true", help="don't ask (sweep)")
    s.add_argument("--profile", help="profile YAML override")
    s.set_defaults(fn=cmd_track)

    s = sub.add_parser("journal", help="progress & learnings log")
    s.add_argument("action", choices=["log", "show"])
    s.add_argument("text", nargs="?")
    s.add_argument("--kind", choices=journal.KINDS)
    s.add_argument("--tag", action="append")
    s.add_argument("--limit", type=int, default=30)
    s.set_defaults(fn=cmd_journal)

    s = sub.add_parser("insights", parents=[common], help="mindset + strategy tips for your situation")
    s.add_argument("--limit", type=int, default=8)
    s.set_defaults(fn=cmd_insights)
    return p


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    selector = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    selector.add_argument("--person")
    selected, rest = selector.parse_known_args(argv)
    args = build_parser().parse_args(rest)
    args.person = selected.person or args.person
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    if args.cmd == "journal" and args.action == "log":
        args.kind = args.kind or "progress"
        if not args.text:
            sys.exit("journal log needs text")
    if args.cmd == "track" and args.action in ("update",) and not args.status:
        sys.exit("track update <app_id> <status>")
    try:
        with person_scope(args.person):
            args.profile = getattr(args, "profile", None) or str(default_profile_path())
            if hasattr(args, "sites"):
                args.sites = args.sites or str(default_sites_path())
            args.fn(args)
    except (KeyError, ValueError, RuntimeError) as exc:
        sys.exit(f"error: {exc}")


if __name__ == "__main__":
    main()
