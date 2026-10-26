"""The house CV format: one markdown master <-> a clean, ATS-friendly Word document.

Markdown conventions (see examples/sample_cv.md):

    # FULL NAME                                   -> name, bold 18pt
    **Headline | focus areas**                    -> headline, bold 11.5pt navy
    City, Country | +phone | email | linkedin     -> contact line (everything before the first ##)
    ## PROFESSIONAL SUMMARY                       -> section heading (Title style, bold 14pt, rule below)
    ### COMPANY | City, Country                   -> employer line, bold
    _Job Title | Start – End_                     -> role line, italic
    #### Product / client / area                  -> sub-heading inside a role, bold
    - Bullet text, **bold** allowed               -> List Bullet
    Plain text                                    -> paragraph
    <!-- comments -->                             -> never exported

Single column, no tables/text boxes/images: parsers read it top to bottom without surprises.
"""
from __future__ import annotations

import re
from pathlib import Path

FONT = "Calibri"
SIZES = {"name": 18, "headline": 11.5, "section": 14, "body": 10.5}
HEADLINE_RGB = "1F3864"
TEXT_RGB = "000000"
MARGIN_IN = 0.6
PAGE = {"letter": (8.5, 11.0), "a4": (8.27, 11.69)}
SECTION_ORDER = ["PROFESSIONAL SUMMARY", "CORE COMPETENCIES", "TECHNICAL SKILLS", "LEADERSHIP AND OWNERSHIP",
                 "PROFESSIONAL EXPERIENCE", "EDUCATION", "SELECTED PROJECTS", "CERTIFICATIONS AND TRAINING",
                 "ADDITIONAL INFORMATION"]

INLINE_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
BULLET_RE = re.compile(r"^\s*[-*•▪●◦]\s+(.*)$")


# --------------------------------------------------------------------------- docx -> markdown
def _runs_md(par) -> str:
    """Paragraph text with partially-bold runs kept as **bold**."""
    runs = [r for r in par.runs if r.text]
    if not runs:
        return par.text.strip()
    if all(r.bold for r in runs) or not any(r.bold for r in runs):
        return "".join(r.text for r in runs).strip()
    out = ""
    for r in runs:
        out += f"**{r.text.strip()}** " if r.bold and r.text.strip() else r.text
    return re.sub(r"\s+", " ", out).strip()


def _is_bullet(par) -> bool:
    name = (par.style.name or "").lower() if par.style is not None else ""
    return "list" in name or par._p.pPr is not None and par._p.pPr.numPr is not None


def docx_to_markdown(path: str | Path) -> str:
    """Read a .docx CV into the markdown format above (headings, roles and bullets preserved)."""
    import docx  # python-docx

    doc = docx.Document(str(path))
    out: list[str] = []
    seen_section = False
    for par in doc.paragraphs:
        text = par.text.strip()
        if not text:
            continue
        style = (par.style.name or "") if par.style is not None else ""
        runs = [r for r in par.runs if r.text.strip()]
        bold = bool(runs) and all(r.bold for r in runs)
        italic = bool(runs) and all(r.italic for r in runs)
        if style == "Title" or style.startswith("Heading"):
            if not out:
                out.append(f"# {text}")
                continue
            out += ["", f"## {text.upper() if text.isupper() else text}"]
            seen_section = True
        elif _is_bullet(par):
            out.append(f"- {_runs_md(par)}")
        elif not out:
            out.append(f"# {text}")
        elif not seen_section and bold and len(out) == 1:
            out.append(f"**{text}**")
        elif bold and seen_section:
            head = text.split("|")[0].strip()
            level = "###" if head.isupper() or (head.upper() == head and any(c.isalpha() for c in head)) else "####"
            out += ["", f"{level} {text}"] if level == "###" else [f"{level} {text}"]
        elif italic:
            out.append(f"_{text}_")
        else:
            out.append(_runs_md(par))
    md = "\n".join(out).strip() + "\n"
    return re.sub(r"\n{3,}", "\n\n", md)


# --------------------------------------------------------------------------- markdown -> docx
def _set_font(run, size: float, bold: bool = False, italic: bool = False, rgb: str | None = TEXT_RGB) -> None:
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor

    run.font.name = FONT
    rfonts = run._element.get_or_add_rPr().get_or_add_rFonts()
    rfonts.set(qn("w:cs"), FONT)
    run.font.size = Pt(size)
    run.font.bold = bold or None
    run.font.italic = italic or None
    if rgb:  # None keeps the paragraph style colour (section headings)
        run.font.color.rgb = RGBColor.from_string(rgb)


def _add(doc, text: str, size: float, style: str | None = None, bold: bool = False, italic: bool = False,
         rgb: str | None = TEXT_RGB):
    par = doc.add_paragraph(style=style) if style else doc.add_paragraph()
    parts = INLINE_BOLD_RE.split(text)
    for i, part in enumerate(parts):  # odd indexes were inside **...**
        if part:
            _set_font(par.add_run(part), size, bold or i % 2 == 1, italic, rgb)
    return par


def markdown_to_docx(markdown: str, path: str | Path, page: str = "letter") -> Path:
    """Render CV markdown in the house format. `page` is 'letter' or 'a4'."""
    import docx  # python-docx
    from docx.shared import Inches

    doc = docx.Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = (Inches(x) for x in PAGE.get(page.lower(), PAGE["letter"]))
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, side, Inches(MARGIN_IN))

    body = SIZES["body"]
    lines = COMMENT_RE.sub("", markdown).splitlines()
    in_header, had_headline = True, False
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("## ") or (line.startswith("# ") and not in_header):
            in_header = False
            _add(doc, line.lstrip("# ").strip().upper(), SIZES["section"], style="Title", bold=True, rgb=None)
        elif line.startswith("# "):
            _add(doc, line[2:].strip().upper(), SIZES["name"], bold=True)
        elif line.startswith("#"):
            _add(doc, line.lstrip("# ").strip().replace("**", ""), body, bold=True)
        elif m := BULLET_RE.match(raw):
            _add(doc, m.group(1).strip(), body, style="List Bullet")
        elif in_header and not had_headline and line.startswith("**") and line.endswith("**"):
            had_headline = True
            _add(doc, line.strip("*").strip(), SIZES["headline"], bold=True, rgb=HEADLINE_RGB)
        elif re.fullmatch(r"_(.+)_|\*(?!\*)(.+)\*", line):
            _add(doc, line[1:-1].strip(), body, italic=True)
        else:
            _add(doc, line, body)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    return path


# --------------------------------------------------------------------------- helpers
def convert(src: str | Path, dest: str | Path, page: str = "letter") -> Path:
    """.docx -> .md or .md/.txt -> .docx, chosen by file extensions."""
    src, dest = Path(src), Path(dest)
    if src.suffix.lower() == ".docx" and dest.suffix.lower() in (".md", ".txt"):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(docx_to_markdown(src), encoding="utf-8")
        return dest
    if src.suffix.lower() in (".md", ".txt") and dest.suffix.lower() == ".docx":
        return markdown_to_docx(src.read_text(encoding="utf-8"), dest, page)
    raise ValueError("convert .docx -> .md, or .md -> .docx")


def lint(markdown: str) -> list[str]:
    """Format problems worth fixing before sending (placeholders, missing sections, contact details)."""
    issues = []
    text = COMMENT_RE.sub("", markdown)
    for ph in sorted(set(re.findall(r"\[[^\]\n]{2,80}\]", text))):
        if not re.match(r"\[\s*[xX ]\s*\]$", ph):
            issues.append(f"unfilled placeholder {ph}")
    if not re.search(r"^# \S", text, re.M):
        issues.append("no '# NAME' line at the top")
    headings = {h.strip().upper() for h in re.findall(r"^## (.+)$", text, re.M)}
    for need in ("PROFESSIONAL SUMMARY", "PROFESSIONAL EXPERIENCE", "EDUCATION"):
        if not any(need.split()[-1] in h for h in headings):
            issues.append(f"missing section: {need}")
    head = "\n".join(text.splitlines()[:6])
    if not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", head):
        issues.append("no email in the contact line")
    if "linkedin.com/in/" not in head.lower():
        issues.append("no LinkedIn URL in the contact line")
    return issues
