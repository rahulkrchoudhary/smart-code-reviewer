# Smart Code Reviewer — Setup & Run Guide

**An AI assistant that reviews code for readability, structure, and maintainability — and gates it — before a human ever opens the pull request.**

Submitted for the Careem challenge by **Rahul**.

This guide is fully self-contained: follow it top to bottom and the application will be running locally in a couple of minutes. It works **with no API key** (a built-in static-analysis engine), and becomes sharper when an Anthropic API key is supplied (an optional Claude-powered deep review).

---

## 1. Prerequisites

| Requirement | Details |
|-------------|---------|
| **Operating system** | macOS, Linux, or Windows |
| **Python** | Version **3.10 – 3.12** (3.11 recommended and tested) |
| **Internet** | Required only for the first install (to fetch dependencies) and to load web fonts |
| **Disk** | ~150 MB for the virtual environment and dependencies |

Verify your Python version:

```bash
python3 --version
```

> If you have multiple Python versions, use the one in the 3.10–3.12 range (for example `python3.11`).

---

## 2. Quick start (recommended)

A single script creates an isolated virtual environment, installs the dependencies, and launches the app.

**macOS / Linux**

```bash
cd careem-smart-code-reviewer
./run.sh
```

If the script is not executable yet:

```bash
chmod +x run.sh
./run.sh
```

The app opens automatically in your browser at **http://localhost:8501**.

---

## 3. Manual setup (alternative)

Use this if you prefer to run each step yourself, or if you are on Windows.

**macOS / Linux**

```bash
cd careem-smart-code-reviewer
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

**Windows (PowerShell)**

```powershell
cd careem-smart-code-reviewer
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

Then open **http://localhost:8501** in your browser.

---

## 4. Using the application

### Single-file review
1. Choose the **Single file** mode at the top.
2. Pick a bundled **Sample**, **Paste** code, or **Upload** a file.
3. Confirm the detected **Language** and select **Review code**.
4. Review the results: an overall grade, a Quality Gate verdict, a dimension radar chart, line-level findings, an annotated source view, and a findings distribution chart.
5. Export a **Markdown report**, a **JSON report** (for CI pipelines), or an **SVG grade badge**.

### Project / repository review
1. Switch to **Project (repo / folder)** mode.
2. Load a codebase one of three ways:
   - **Files** — select multiple source files,
   - **Zip / repo** — upload a `.zip` of a folder or repository,
   - **Folder path** — paste an absolute path to a local folder (when running locally).
3. Select **Review project** to see an aggregate health dashboard with a per-file score breakdown and drill-downs.

> Common build and dependency directories (`.git`, `node_modules`, `.venv`, `dist`, `build`, and similar) are skipped automatically.

### Optional: enable the Claude deep review
1. In the sidebar, turn on **Deep review with Claude**.
2. Paste an **Anthropic API key** (`sk-ant-...`). It is used only for the current session and is never stored.
3. Re-run the review to add an AI-written summary, additional findings, and a suggested refactor of the weakest section.

The default model is **Claude Opus 4.8**; Sonnet and Haiku can be selected from the sidebar.

---

## 5. Running the tests

The review engine ships with a test suite that uses only the Python standard library (no extra dependencies):

```bash
python3.11 -m unittest discover -s tests -v
```

All tests should report **OK**.

---

## 6. Troubleshooting

| Symptom | Resolution |
|---------|------------|
| **Port 8501 already in use** | Run on another port: `streamlit run app.py --server.port 8502` |
| **`streamlit: command not found`** | Activate the virtual environment first (`source .venv/bin/activate`), then re-run. |
| **Dependency install fails on a very new Python** | Use Python **3.10–3.12**; the latest pre-release Python versions may not yet have prebuilt packages. |
| **UI looks unstyled or icons show as text** | Do a hard refresh in the browser — **Cmd/Ctrl + Shift + R** — to clear cached styles. |
| **Stop the app** | Press **Ctrl + C** in the terminal running it. |

---

## 7. Project structure

```
careem-smart-code-reviewer/
├── app.py                  Streamlit user interface
├── reviewer/               Review engine (importable, framework-agnostic)
│   ├── analyzer.py         Static engine — Python AST + heuristic analysis
│   ├── scoring.py          Findings → dimension scores → letter grade
│   ├── ai_reviewer.py      Optional Claude-powered deep review
│   └── models.py           Shared data models
├── samples/                Demonstration files (with and without issues)
├── tests/                  Standard-library test suite
├── requirements.txt        Python dependencies
├── run.sh                  One-command launcher
└── HOW_TO_RUN.md           This guide
```

---

## 8. Notes

- The application runs entirely on your machine. No code or data is sent anywhere unless the optional Claude deep review is explicitly enabled with your API key.
- All sample data is self-created and contains no confidential information.

---

*Smart Code Reviewer — built for the Careem challenge by Rahul.*
