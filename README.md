# Smart Code Reviewer

**An AI assistant that reviews code for readability, structure, and maintainability — and gates it — before a human ever opens the pull request.**

Built for the Careem challenge by **Rahul**.

Paste a snippet, upload a file, or point it at an entire repository. You get a graded scorecard, a pass/fail Quality Gate, a radar chart across the three quality dimensions, line-level findings with concrete fixes, an annotated source view, and exportable reports. It runs **fully offline** on a built-in static-analysis engine, and becomes sharper when an Anthropic API key is supplied (an optional Claude-powered deep review).

---

## Highlights

| | |
|---|---|
| **Works with zero setup** | The static engine needs no API key. Python is parsed into a real **AST** (cyclomatic complexity, nesting depth, mutable default arguments, naming, bare `except`, `eval`, magic numbers). Other languages use a heuristic line scanner. |
| **Quality Gate** | A configurable pass/fail merge check — the same idea as a CI step that blocks a low-quality pull request. Set the minimum grade in the sidebar. |
| **Real scoring, not vibes** | Every dimension starts at 100 and loses points per finding, weighted by severity. The model is simple and **fully explainable** — documented in the sidebar. |
| **AI that adds judgement** | With a key, Claude **Opus 4.8** returns *schema-validated* findings (structured outputs), a senior-reviewer summary, and a refactor of the weakest section. |
| **Whole-repo mode** | Review many files at once via multiple uploads, a `.zip` of a repository, or a local folder path — with an aggregate health dashboard. |
| **Exports** | One-click Markdown report, JSON report for CI pipelines, and an embeddable SVG grade badge. |
| **Professional UI** | A refined Streamlit interface: a custom-branded header, hairline-bordered cards, monospace metrics, an annotated diff-style code view, and a findings distribution chart. |

---

## Quick start

A single script creates an isolated virtual environment, installs dependencies, and launches the app.

```bash
cd careem-smart-code-reviewer
./run.sh
```

The app opens at **http://localhost:8501**. Pick the `messy_orders.py` sample and select **Review code**.

Prefer to run it manually:

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

> A complete, platform-by-platform setup and troubleshooting guide is in **[HOW_TO_RUN.md](HOW_TO_RUN.md)** (includes Windows instructions).

### Optional: the Claude deep-review layer

In the sidebar, enable **Deep review with Claude** and paste an Anthropic API key (`sk-ant-...`). It is used only for the current session and is never stored. The default model is `claude-opus-4-8`.

### Running the tests

A code-quality tool should be tested itself. The engine ships with a standard-library test suite (no extra dependencies):

```bash
python3.11 -m unittest discover -s tests -v
```

---

## Features in detail

**Single-file review.** Grade hero with a dimension radar chart, a Quality Gate verdict, insight metrics (estimated review time saved, tech-debt count, focus area), per-dimension scorecards, and tabs for Findings, an Annotated code view, a Distribution chart, and the AI review.

**Annotated code view.** Your actual source rendered with line numbers and inline, severity-coloured issue markers — like a real pull-request review.

**Project / repository review.** Load a codebase three ways — multiple files, a `.zip` of a repo, or an absolute local folder path. Common build and dependency directories (`.git`, `node_modules`, `.venv`, `dist`, `build`, and similar) are skipped automatically. The dashboard shows a line-weighted aggregate grade, a per-file score chart, a ranked table, and per-file drill-downs.

**Exports.** Markdown report (human-readable), JSON report (machine-readable for CI), and an SVG grade badge you can embed in a repository README.

---

## What it catches

- **Readability** — vague or ambiguous names, camelCase in Python, missing docstrings, magic numbers, over-long lines, mixed indentation.
- **Structure** — long functions, high cyclomatic complexity, deep nesting, too many parameters.
- **Maintainability** — mutable default arguments, bare and silently-swallowed `except`, `eval`, `global` state, loose equality (`==`) and `var` in JavaScript, leftover `print` / `console.log` / `debugger`, and `TODO` / `FIXME` markers.

…plus anything Claude flags that requires actual understanding of intent.

---

## Architecture

```
careem-smart-code-reviewer/
├── app.py                  Streamlit user interface
├── reviewer/               Review engine (importable, framework-agnostic)
│   ├── __init__.py         review() orchestrator + language detection + dedupe
│   ├── models.py           Finding / Severity / Dimension / ReviewResult
│   ├── analyzer.py         Static engine — Python AST + heuristic line scanner
│   ├── scoring.py          Findings → dimension scores → weighted letter grade
│   └── ai_reviewer.py      Optional Claude pass (structured outputs, graceful fallback)
├── samples/                Demonstration files (with and without planted issues)
├── tests/                  Standard-library test suite for the engine
├── .streamlit/config.toml  Theme and client configuration
├── requirements.txt        Python dependencies
├── run.sh                  One-command launcher
├── HOW_TO_RUN.md           Full setup and troubleshooting guide
└── README.md               This document
```

**Pipeline:** `analyze()` produces findings and metrics → an optional Claude pass adds more → near-duplicates are merged → `score_review()` assigns per-dimension scores and a weighted overall grade → the UI renders the result and the Quality Gate verdict.

The static and AI layers emit the **same `Finding` shape**, so the UI never has to care where an issue came from. The `reviewer` package has no UI dependencies and can be used as a library or wired into a CI pipeline.

---

## Notes

- The application runs entirely on your machine. No code or data leaves it unless the optional Claude deep review is explicitly enabled with your API key.
- Models and structured-output usage follow the current Anthropic SDK (`messages.parse` with adaptive thinking).
- All sample data is self-created and contains no confidential information.

---

*Smart Code Reviewer — built for the Careem challenge by Rahul.*
