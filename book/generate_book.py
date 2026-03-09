"""
Generate a Quarto book from event study JSON files.

Reads all JSON metadata from event_study/json/, generates:
  - One .qmd chapter per event study with 3 sections (Plot, Code, Data)
  - _quarto.yml configuration
  - index.qmd landing page

Run from the repo root: python book/generate_book.py
"""

import json
import os
import glob
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_DIR = os.path.join(REPO_ROOT, "event_study", "json")
CHAPTERS_DIR = os.path.join(REPO_ROOT, "chapters")
PLOTS_DIR = os.path.join(REPO_ROOT, "event_study", "plots")
CSV_DIR = os.path.join(REPO_ROOT, "event_study", "csv")


def load_studies():
    """Load all JSON study files, sorted by timestamp."""
    studies = []
    pattern = os.path.join(JSON_DIR, "*.json")
    for fpath in glob.glob(pattern):
        with open(fpath, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                studies.append(data)
            except json.JSONDecodeError:
                print(f"WARNING: Could not parse {fpath}, skipping.")
    studies.sort(key=lambda s: s.get("timestamp", ""))
    return studies


def generate_chapter(study, idx):
    """Generate a .qmd file for a single event study with 3 sections."""
    sid = study["id"]
    paper = study.get("paper", {})
    method = study.get("methodology", {})
    qa = study.get("qa", {})
    results = study.get("results", {})
    data_rows = results.get("data", [])
    ci = results.get("confidence_level", 95)
    lang = method.get("code_language", "stata")
    code = method.get("code", "# No code provided")
    ts = study.get("timestamp", "")

    # Format date
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        date_str = dt.strftime("%B %d, %Y")
    except Exception:
        date_str = ts[:10] if len(ts) >= 10 else "Unknown"

    # Build data table (show first 3 rows + summary)
    table_header = "| Period | Estimate | Std. Error | LB {ci}% | UB {ci}% |".format(ci=ci)
    table_sep = "|--------|----------|------------|----------|----------|"
    table_rows = []
    for row in data_rows[:3]:
        table_rows.append(
            "| {period} | {est:.5f} | {se:.5f} | {lb:.5f} | {ub:.5f} |".format(
                period=row["period"],
                est=row["estimate"],
                se=row["std_error"],
                lb=row["lb"],
                ub=row["ub"],
            )
        )
    if len(data_rows) > 3:
        table_rows.append(
            "| ... | *{n} more rows* | | | |".format(n=len(data_rows) - 3)
        )

    data_table = "\n".join([table_header, table_sep] + table_rows)

    # Q&A section
    qa_section = ""
    if qa and (qa.get("reviewer_name") or qa.get("reviewer_comments") or qa.get("author_response")):
        qa_section = """
## Reviewer Q&A

**Reviewer:** {reviewer}

> **Comments:** {comments}

**Author Response:** {response}
""".format(
            reviewer=qa.get("reviewer_name", "Anonymous"),
            comments=qa.get("reviewer_comments", "No comments."),
            response=qa.get("author_response", "No response."),
        )

    # Plot path (relative from chapters/ to repo root)
    plot_rel = "../event_study/plots/{sid}.png".format(sid=sid)

    qmd = """---
title: "{title}"
author: "{authors}"
date: "{date}"
---

## Event Study Plot

![Event study estimates with {ci}% confidence intervals]({plot_path}){{fig-align="center" width="100%"}}

*{desc}*

{identification}

## Code

The following {lang} code generated this event study:

```{{{lang}}}
{code}
```

## Data

{data_table}

{n_obs} total observations | Confidence level: {ci}%
{qa_section}
""".format(
        title=paper.get("title", "Untitled Study"),
        authors=paper.get("authors", "Unknown"),
        date=date_str,
        ci=ci,
        plot_path=plot_rel,
        desc=paper.get("description", ""),
        identification=(
            "::: {{.callout-note}}\n**Identification Strategy:** {}\n:::".format(
                method.get("identification_strategy", "Not specified")
            )
            if method.get("identification_strategy")
            else ""
        ),
        lang=lang,
        code=code,
        data_table=data_table,
        n_obs=results.get("observations", len(data_rows)),
        qa_section=qa_section,
    )

    fname = "study_{idx:03d}_{sid}.qmd".format(idx=idx, sid=sid)
    fpath = os.path.join(CHAPTERS_DIR, fname)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(qmd)

    return fname


def generate_index(studies):
    """Generate index.qmd with a table of all studies."""
    rows = []
    for i, s in enumerate(studies, 1):
        paper = s.get("paper", {})
        ts = s.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            date_str = dt.strftime("%Y-%m-%d")
        except Exception:
            date_str = "?"
        decision = s.get("decision", {})
        status = "Accepted" if decision.get("accepted") else "Pending"
        rows.append(
            "| {i} | {title} | {authors} | {date} | {status} |".format(
                i=i,
                title=paper.get("title", "Untitled")[:50],
                authors=paper.get("authors", "?")[:30],
                date=date_str,
                status=status,
            )
        )

    table = "\n".join(
        [
            "| # | Title | Authors | Date | Status |",
            "|---|-------|---------|------|--------|",
        ]
        + rows
    )

    qmd = """---
title: "Event Study Results"
---

This book contains event study results submitted and reviewed through the [Event Study Plotter](https://anzonyquispe.github.io/did_book/web/event_study_plotter.html).

Each entry includes three sections:

1. **Event Study Plot** — the visualization with confidence intervals
2. **Code** — the DiD code that generated the results
3. **Data** — a preview of the estimation results

## Studies

{table}

---

*Auto-generated on {now}*
""".format(
        table=table,
        now=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    )

    fpath = os.path.join(REPO_ROOT, "index.qmd")
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(qmd)


def generate_quarto_yml(chapter_files):
    """Generate _quarto.yml with the list of chapters."""
    chapters_yaml = "\n".join(
        "    - chapters/{f}".format(f=f) for f in chapter_files
    )

    yml = """project:
  type: book
  output-dir: _site

book:
  title: "Event Study Results"
  author: "Auto-generated"
  chapters:
    - index.qmd
{chapters}

format:
  html:
    theme: cosmo
    toc: true
    code-fold: true
    code-tools: false
""".format(
        chapters=chapters_yaml
    )

    fpath = os.path.join(REPO_ROOT, "_quarto.yml")
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(yml)


def main():
    os.makedirs(CHAPTERS_DIR, exist_ok=True)

    # Clean old generated chapters
    for old in glob.glob(os.path.join(CHAPTERS_DIR, "study_*.qmd")):
        os.remove(old)

    studies = load_studies()
    if not studies:
        print("No event study JSON files found. Generating empty book.")
        generate_index([])
        generate_quarto_yml([])
        return

    print(f"Found {len(studies)} event study/studies.")

    chapter_files = []
    for idx, study in enumerate(studies, 1):
        fname = generate_chapter(study, idx)
        chapter_files.append(fname)
        print(f"  Generated: chapters/{fname}")

    generate_index(studies)
    print("  Generated: index.qmd")

    generate_quarto_yml(chapter_files)
    print("  Generated: _quarto.yml")

    print("Done! Run 'quarto render' to build the book.")


if __name__ == "__main__":
    main()
