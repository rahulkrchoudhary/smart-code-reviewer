"""Smart Code Reviewer — a Streamlit app for the Careem challenge.

An AI assistant that reviews code for readability, structure and maintainability
*before* a human reviewer ever looks at it. It works fully offline on a built-in
static-analysis engine, and gets sharper when you add a Claude API key.

Features:
  • Single-file review with a graded scorecard, radar chart and annotated source
  • A configurable Quality Gate (pass/fail merge check — the CI angle)
  • Project mode: review many files, a .zip of a repo, or a local folder path
  • Insight metrics, findings distribution, embeddable grade badge, JSON/MD export

Run with:  streamlit run app.py
"""
from __future__ import annotations

import datetime as _dt
import html
import io
import json
import os
import zipfile
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

import reviewer
from reviewer import Dimension, Severity
from reviewer.models import SEVERITY_RANK
from reviewer.scoring import grade_label, score_to_grade

SAMPLES_DIR = Path(__file__).parent / "samples"

# ── Design tokens ──────────────────────────────────────────────────────────
INK = "#10151C"          # near-black, cool
MUTED = "#5A6675"        # secondary text
FAINT = "#8A94A1"        # tertiary text
LINE = "#E8ECEF"         # hairline
LINE_STRONG = "#D6DDE2"
PAPER = "#FFFFFF"
PAPER_2 = "#F6F8F9"
GREEN = "#0E9E6B"        # disciplined Careem-green accent
GREEN_BRIGHT = "#26C281"
GREEN_DARK = "#0A7E55"

GRADE_COLOR = {"A": "#0E9E6B", "B": "#3E9E78", "C": "#B98A1E",
               "D": "#CE6A2C", "F": "#C0413E"}
GRADE_RANK = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}

SEV_COLOR = {Severity.CRITICAL: "#C0413E", Severity.MAJOR: "#CE6A2C",
             Severity.MINOR: "#B98A1E", Severity.INFO: "#3B6FB0"}
SEV_TINT = {Severity.CRITICAL: "#FBEDEC", Severity.MAJOR: "#FBF0E8",
            Severity.MINOR: "#FAF4E6", Severity.INFO: "#EDF2F9"}

IGNORE_DIRS = {".git", "node_modules", ".venv", "venv", "env", "__pycache__",
               "dist", "build", ".next", "target", ".idea", ".vscode", "vendor",
               ".mypy_cache", ".pytest_cache", "coverage", ".tox"}
MAX_FILE_BYTES = 200_000
MAX_PROJECT_FILES = 400

# ── Inline iconography (no emoji) ──────────────────────────────────────────
def logo_svg(size: int = 44, variant: str = "dark") -> str:
    """A '</>' code-review monogram. `dark` for the hero, `light` for the nav."""
    if variant == "dark":
        border, stroke, fill = "#0E9E6B", "#2FD08C", "rgba(14,158,107,0.16)"
    else:
        border, stroke, fill = "#0E9E6B", "#0E9E6B", "rgba(14,158,107,0.10)"
    return (
        f'<svg viewBox="0 0 44 44" width="{size}" height="{size}" aria-hidden="true">'
        f'<rect x="1.3" y="1.3" width="41.4" height="41.4" rx="12.5" fill="{fill}" '
        f'stroke="{border}" stroke-width="1.3"/>'
        f'<path d="M16 14.5l-6.5 7.5 6.5 7.5" fill="none" stroke="{stroke}" '
        f'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<path d="M28 14.5l6.5 7.5-6.5 7.5" fill="none" stroke="{stroke}" '
        f'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<path d="M25.5 12l-7 20" fill="none" stroke="{stroke}" stroke-width="2.5" '
        f'stroke-linecap="round"/></svg>'
    )
ICON_CHECK = ('<svg width="17" height="17" viewBox="0 0 24 24" fill="none" '
              'stroke="currentColor" stroke-width="2.6" stroke-linecap="round" '
              'stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>')
ICON_BLOCK = ('<svg width="17" height="17" viewBox="0 0 24 24" fill="none" '
              'stroke="currentColor" stroke-width="2.2" stroke-linecap="round">'
              '<circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/></svg>')

st.set_page_config(
    page_title="Smart Code Reviewer · Careem",
    page_icon=":material/fact_check:",
    layout="wide",
    initial_sidebar_state="expanded",
)


# --------------------------------------------------------------------------- #
# Styling
# --------------------------------------------------------------------------- #
def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Archivo:wght@600;700;800&family=IBM+Plex+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500;700&display=swap');
        @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&family=Material+Symbols+Outlined');

        :root {{
            --ink:{INK}; --muted:{MUTED}; --faint:{FAINT}; --line:{LINE};
            --line-strong:{LINE_STRONG}; --green:{GREEN}; --green-dark:{GREEN_DARK};
            --font-body:'IBM Plex Sans',system-ui,sans-serif;
            --font-display:'Archivo',system-ui,sans-serif;
            --font-mono:'JetBrains Mono',ui-monospace,SFMono-Regular,monospace;
        }}
        html, body, .stApp {{ font-family: var(--font-body); }}
        /* Never restyle Streamlit's Material icon glyphs (expander chevrons,
           upload icon, help dots) — they rely on the icon font's ligatures. */
        [data-testid="stIconMaterial"], span[class*="material-symbols"] {{
            font-family:'Material Symbols Rounded','Material Symbols Outlined',
            'Material Icons' !important; }}
        .stApp {{ background:#FBFCFD; color:var(--ink); }}
        .main .block-container {{ padding-top:1.4rem; max-width:1200px; }}
        h1,h2,h3,h4,h5 {{ font-family:var(--font-display); color:var(--ink);
            letter-spacing:-0.015em; font-weight:700; }}
        .scr-mono, code, kbd, pre {{ font-family:var(--font-mono); }}

        @keyframes scrUp {{ from {{opacity:0; transform:translateY(9px);}}
            to {{opacity:1; transform:none;}} }}

        /* Header band ----------------------------------------------------- */
        .scr-hero {{ position:relative; overflow:hidden; border-radius:20px;
            padding:30px 34px; margin-bottom:20px; border:1px solid #1C2733;
            background:radial-gradient(130% 150% at 0% 0%, #17222E 0%, #0B1117 62%);
            box-shadow:0 18px 48px -24px rgba(8,15,22,0.7);
            animation:scrUp .55s ease both; }}
        .scr-hero::before {{ content:""; position:absolute; right:-90px; top:-110px;
            width:320px; height:320px; pointer-events:none;
            background:radial-gradient(circle, rgba(14,158,107,0.30), transparent 68%); }}
        .scr-hero::after {{ content:""; position:absolute; inset:0; pointer-events:none;
            background-image:radial-gradient(rgba(255,255,255,0.045) 1px, transparent 1px);
            background-size:20px 20px; }}
        .scr-hero-row {{ position:relative; display:flex; align-items:center; gap:18px; }}
        .scr-kicker {{ font-family:var(--font-mono); font-size:0.7rem; font-weight:500;
            letter-spacing:0.22em; color:#3FD9A0; text-transform:uppercase; }}
        .scr-word {{ font-family:var(--font-display); font-weight:800; color:#fff;
            font-size:2.05rem; line-height:1.05; margin:4px 0 0;
            letter-spacing:-0.025em; }}
        .scr-sub {{ color:#9FB0BF; font-size:0.98rem; margin:7px 0 0; max-width:640px; }}
        .scr-chips {{ position:relative; margin-top:16px; display:flex; flex-wrap:wrap;
            gap:8px; }}
        .scr-chip {{ font-family:var(--font-mono); font-size:0.7rem; letter-spacing:0.06em;
            text-transform:uppercase; color:#C7D4DD; padding:4px 11px; border-radius:7px;
            border:1px solid rgba(255,255,255,0.16); background:rgba(255,255,255,0.04); }}

        /* Cards ----------------------------------------------------------- */
        .scr-card {{ background:{PAPER}; border:1px solid var(--line); border-radius:14px;
            padding:18px 20px; height:100%; animation:scrUp .45s ease both;
            box-shadow:0 1px 2px rgba(16,21,28,0.03); transition:border-color .15s ease,
            box-shadow .15s ease, transform .15s ease; }}
        .scr-card:hover {{ border-color:var(--line-strong);
            box-shadow:0 8px 24px -16px rgba(16,21,28,0.30); }}
        .scr-label {{ color:var(--faint); font-size:0.7rem; font-weight:500;
            font-family:var(--font-mono); text-transform:uppercase; letter-spacing:0.1em;
            margin-bottom:6px; }}
        .scr-value {{ color:var(--ink); font-size:1.55rem; font-weight:600;
            font-family:var(--font-mono); letter-spacing:-0.02em; }}
        .scr-grade {{ font-family:var(--font-mono); font-size:3.5rem; font-weight:700;
            line-height:1; margin:2px 0; letter-spacing:-0.03em; }}
        .scr-dot {{ display:inline-block; width:10px; height:10px; border-radius:50%;
            margin-right:9px; vertical-align:baseline; }}

        /* Quality gate ---------------------------------------------------- */
        .scr-gate {{ border-radius:14px; padding:15px 20px; margin-bottom:8px;
            display:flex; align-items:center; gap:14px; border:1px solid;
            animation:scrUp .45s ease both; }}
        .scr-gate .ico {{ display:flex; }}
        .scr-gate .txt {{ font-size:0.96rem; color:var(--ink); }}
        .scr-status {{ font-family:var(--font-mono); font-weight:700; font-size:0.74rem;
            letter-spacing:0.12em; text-transform:uppercase; padding:3px 9px;
            border-radius:6px; margin-left:2px; }}

        /* Findings -------------------------------------------------------- */
        .scr-finding {{ border-left:3px solid #ccc; background:{PAPER};
            border:1px solid var(--line); border-radius:11px; padding:13px 16px;
            margin-bottom:10px; }}
        .scr-badge {{ display:inline-block; padding:2px 9px; border-radius:6px;
            font-size:0.66rem; font-weight:700; color:white; font-family:var(--font-mono);
            letter-spacing:0.06em; text-transform:uppercase; }}
        .scr-tag {{ display:inline-block; padding:2px 9px; border-radius:6px;
            font-size:0.66rem; background:{PAPER_2}; color:var(--muted);
            border:1px solid var(--line); margin-left:6px; font-family:var(--font-mono);
            letter-spacing:0.05em; text-transform:uppercase; }}
        .scr-loc {{ color:var(--faint); font-size:0.72rem; font-family:var(--font-mono);
            margin-left:8px; }}
        .scr-fix {{ color:var(--green-dark); font-size:0.88rem; margin-top:7px; }}
        .scr-fix b {{ font-family:var(--font-mono); font-size:0.7rem; letter-spacing:0.06em;
            text-transform:uppercase; }}

        /* Annotated code -------------------------------------------------- */
        .scr-code {{ border:1px solid var(--line); border-radius:12px; overflow:auto;
            max-height:560px; font-family:var(--font-mono); font-size:0.82rem;
            background:{PAPER}; }}
        .scr-row {{ display:flex; align-items:flex-start; }}
        .scr-gutter {{ width:46px; min-width:46px; text-align:right; padding:1px 12px;
            color:#AEB8C1; user-select:none; border-right:1px solid #EEF2F1; }}
        .scr-codetext {{ padding:1px 14px; white-space:pre; flex:1; color:var(--ink); }}
        .scr-note {{ margin:2px 0 7px 58px; font-size:0.76rem; }}

        /* Project table --------------------------------------------------- */
        .scr-ptable {{ width:100%; border-collapse:collapse; font-size:0.88rem; }}
        .scr-ptable th {{ text-align:left; color:var(--faint); font-size:0.66rem;
            font-family:var(--font-mono); text-transform:uppercase; letter-spacing:0.08em;
            padding:7px 10px; border-bottom:1px solid var(--line-strong); }}
        .scr-ptable td {{ padding:9px 10px; border-bottom:1px solid var(--line); }}
        .scr-ptable td.num {{ font-family:var(--font-mono); }}

        /* Streamlit widget refinements ------------------------------------ */
        section[data-testid="stSidebar"] {{ background:var(--paper-2);
            border-right:1px solid var(--line); }}
        .stButton > button {{ background:var(--ink); color:#fff; border:0;
            border-radius:10px; font-weight:600; font-family:var(--font-body);
            padding:0.55rem 1.3rem; letter-spacing:0.005em; transition:all .15s ease; }}
        .stButton > button:hover {{ background:var(--green); color:#fff;
            transform:translateY(-1px); }}
        .stDownloadButton > button {{ background:{PAPER}; color:var(--ink);
            border:1px solid var(--line-strong); border-radius:10px; font-weight:600; }}
        .stDownloadButton > button:hover {{ border-color:var(--green);
            color:var(--green-dark); background:{PAPER}; }}
        button[data-baseweb="tab"] {{ font-family:var(--font-mono); font-size:0.76rem;
            letter-spacing:0.04em; text-transform:uppercase; color:var(--muted); }}
        button[data-baseweb="tab"][aria-selected="true"] {{ color:var(--ink); }}
        [data-baseweb="tab-highlight"] {{ background:var(--green) !important; }}
        div[role="radiogroup"] {{ gap:10px; }}
        .scr-foot {{ color:var(--faint); font-size:0.78rem; text-align:center;
            margin-top:30px; font-family:var(--font-mono); letter-spacing:0.04em; }}
        .scr-foot b {{ color:var(--green-dark); }}

        /* Sidebar brand lockup */
        .scr-brand {{ display:flex; align-items:center; gap:11px;
            padding:2px 2px 12px; margin-bottom:8px;
            border-bottom:1px solid var(--line); }}
        .scr-brand-name {{ font-family:var(--font-display); font-weight:700;
            font-size:1rem; color:var(--ink); line-height:1.12; }}
        .scr-brand-by {{ font-family:var(--font-mono); font-size:0.64rem;
            letter-spacing:0.14em; text-transform:uppercase; color:var(--green-dark);
            margin-top:3px; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def hero() -> None:
    chips = ["Offline-capable", "Claude Opus 4.8", "Quality gate", "Repo mode",
             "Embeddable badge"]
    chip_html = "".join(f'<span class="scr-chip">{c}</span>' for c in chips)
    st.markdown(
        f"""
        <div class="scr-hero">
          <div class="scr-hero-row">
            <div>{logo_svg(46, "dark")}</div>
            <div>
              <div class="scr-kicker">Code Quality Platform · Careem</div>
              <div class="scr-word">Smart Code Reviewer</div>
              <div class="scr-sub">Readability, structure and maintainability —
                  graded and gated before a human ever opens the pull request.</div>
            </div>
          </div>
          <div class="scr-chips">{chip_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
def sidebar() -> dict:
    with st.sidebar:
        st.markdown(
            f'<div class="scr-brand">{logo_svg(34, "light")}'
            f'<div><div class="scr-brand-name">Smart Code Reviewer</div>'
            f'<div class="scr-brand-by">by Rahul</div></div></div>',
            unsafe_allow_html=True)
        st.markdown("### Review settings")

        ai_possible = reviewer.ai_reviewer.is_available()
        use_ai = st.toggle(
            "Deep review with Claude", value=False,
            help="Adds an LLM pass for issues that need understanding. Needs a key.",
            disabled=not ai_possible)
        if not ai_possible:
            st.caption("Install `anthropic` to enable the AI layer.")

        api_key, model = "", reviewer.ai_reviewer.DEFAULT_MODEL
        if use_ai:
            api_key = st.text_input("Anthropic API key", type="password",
                                    placeholder="sk-ant-...",
                                    help="Used only this session — never stored.")
            model = st.selectbox("Model", ["claude-opus-4-8", "claude-sonnet-4-6",
                                           "claude-haiku-4-5"], index=0)

        st.divider()
        st.markdown("### Quality gate")
        gate_grade = st.select_slider(
            "Minimum grade to pass", options=["F", "D", "C", "B", "A"], value="C",
            help="Code below this grade fails the gate — like a CI check that "
            "blocks a merge.")

        st.divider()
        st.markdown("##### Scoring")
        st.caption(
            "Each dimension starts at 100 and loses points per issue by severity "
            "(Critical −22, Major −11, Minor −4.5, Info −1). The headline grade "
            "weighs Structure 35% · Maintainability 35% · Readability 30%.")
        st.markdown("##### About")
        st.caption(
            "Built for the Careem challenge by Rahul. The static engine parses "
            "Python into a real AST; other languages use heuristic analysis. The "
            "AI engine returns schema-validated findings, a summary, and a "
            "refactor of the worst section.")

        return {"use_ai": use_ai, "api_key": api_key, "model": model,
                "gate_grade": gate_grade}


# --------------------------------------------------------------------------- #
# Input — single file
# --------------------------------------------------------------------------- #
def list_samples() -> dict[str, Path]:
    if not SAMPLES_DIR.exists():
        return {}
    return {p.name: p for p in sorted(SAMPLES_DIR.iterdir()) if p.is_file()}


def single_input() -> tuple[str, str]:
    tab_sample, tab_paste, tab_upload = st.tabs(["Sample", "Paste", "Upload"])
    source, filename = "", ""

    with tab_sample:
        samples = list_samples()
        if samples:
            choice = st.selectbox("Pick a sample with planted issues",
                                  list(samples.keys()))
            source = samples[choice].read_text()
            filename = choice
            st.code(source[:1200] + ("\n…" if len(source) > 1200 else ""),
                    language=reviewer.detect_language(filename, source).lower())
        else:
            st.info("No sample files found in ./samples")

    with tab_paste:
        pasted = st.text_area("Paste your code here", height=300,
                              placeholder="def example():\n    ...")
        if pasted.strip():
            source, filename = pasted, "pasted_snippet"

    with tab_upload:
        up = st.file_uploader("Upload a source file",
                              type=["py", "js", "jsx", "ts", "tsx", "java", "go",
                                    "c", "h", "cpp", "cs", "rb", "php", "rs",
                                    "kt", "swift"])
        if up is not None:
            source = up.read().decode("utf-8", errors="replace")
            filename = up.name
            st.code(source[:1200] + ("\n…" if len(source) > 1200 else ""),
                    language=reviewer.detect_language(filename, source).lower())

    return source, filename


# --------------------------------------------------------------------------- #
# Input — project (multi-file / zip / folder)
# --------------------------------------------------------------------------- #
def _is_reviewable(name: str) -> bool:
    ext = os.path.splitext(name)[1].lower()
    parts = name.replace("\\", "/").split("/")
    if any(p in IGNORE_DIRS for p in parts):
        return False
    return ext in reviewer._EXT_MAP


def files_from_uploads(uploads) -> dict[str, str]:
    out: dict[str, str] = {}
    for up in uploads or []:
        if _is_reviewable(up.name):
            out[up.name] = up.read().decode("utf-8", errors="replace")
    return out


def files_from_zip(uploaded) -> dict[str, str]:
    out: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(uploaded.read())) as zf:
        for info in zf.infolist():
            if info.is_dir() or info.file_size > MAX_FILE_BYTES:
                continue
            if not _is_reviewable(info.filename):
                continue
            try:
                out[info.filename] = zf.read(info).decode("utf-8", errors="replace")
            except Exception:
                continue
            if len(out) >= MAX_PROJECT_FILES:
                break
    return out


def files_from_folder(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    root_path = Path(path).expanduser()
    for root, dirs, fnames in os.walk(root_path):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
        for fn in fnames:
            fp = Path(root) / fn
            if not _is_reviewable(fn):
                continue
            try:
                if fp.stat().st_size > MAX_FILE_BYTES:
                    continue
                out[str(fp.relative_to(root_path))] = fp.read_text(
                    encoding="utf-8", errors="replace")
            except Exception:
                continue
            if len(out) >= MAX_PROJECT_FILES:
                return out
    return out


def project_input() -> dict[str, str]:
    t_multi, t_zip, t_folder = st.tabs(["Files", "Zip / repo", "Folder path"])
    files: dict[str, str] = {}

    with t_multi:
        ups = st.file_uploader(
            "Select several source files", accept_multiple_files=True,
            type=["py", "js", "jsx", "ts", "tsx", "java", "go", "c", "h", "cpp",
                  "cs", "rb", "php", "rs", "kt", "swift"], key="proj_multi")
        if ups:
            files = files_from_uploads(ups)

    with t_zip:
        st.caption("Zip a folder or repo and drop it here — we skip .git, "
                   "node_modules, .venv, and build directories.")
        z = st.file_uploader("Upload a .zip", type=["zip"], key="proj_zip")
        if z is not None:
            files = files_from_zip(z)

    with t_folder:
        st.caption("Running locally? Point at a repo on disk and we'll scan it.")
        path = st.text_input("Absolute folder path",
                             placeholder="/Users/you/code/my-project")
        if path and os.path.isdir(os.path.expanduser(path)):
            files = files_from_folder(path)
        elif path:
            st.warning("That path isn't a folder I can read.")

    if files:
        st.success(f"Loaded {len(files)} reviewable file(s).")
    return files


# --------------------------------------------------------------------------- #
# Charts & badge
# --------------------------------------------------------------------------- #
def radar_chart(result: reviewer.ReviewResult) -> go.Figure:
    dims = [d.value for d in Dimension]
    scores = [result.dimension_scores[d].score for d in Dimension]
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=scores + [scores[0]], theta=dims + [dims[0]], fill="toself",
        fillcolor="rgba(14,158,107,0.18)", line=dict(color=GREEN, width=2.5),
        marker=dict(size=7, color=GREEN_DARK),
        hovertemplate="%{theta}: %{r}/100<extra></extra>"))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100],
                                   tickfont=dict(size=10, color=FAINT),
                                   gridcolor=LINE),
                   angularaxis=dict(tickfont=dict(size=12, color=INK),
                                    gridcolor=LINE),
                   bgcolor="rgba(0,0,0,0)"),
        showlegend=False, height=320, margin=dict(l=42, r=42, t=30, b=30),
        font=dict(family="IBM Plex Sans"), paper_bgcolor="rgba(0,0,0,0)")
    return fig


def findings_bar(result: reviewer.ReviewResult) -> go.Figure:
    dims = [d.value for d in Dimension]
    fig = go.Figure()
    for sev in Severity:
        ys = [sum(1 for f in result.findings_for(d) if f.severity == sev)
              for d in Dimension]
        fig.add_trace(go.Bar(name=sev.value, x=dims, y=ys,
                             marker_color=SEV_COLOR[sev]))
    fig.update_layout(
        barmode="stack", height=300, margin=dict(l=30, r=20, t=20, b=30),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="IBM Plex Sans", color=MUTED),
        legend=dict(orientation="h", y=1.14), yaxis_title="findings")
    return fig


def make_badge_svg(grade: str, score: float) -> str:
    color = GRADE_COLOR.get(grade, MUTED)
    value = f"{grade} · {score:.0f}/100"
    lw, vw = 96, 96
    total = lw + vw
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total}" height="20">'
        f'<rect width="{lw}" height="20" rx="3" fill="#2A323B"/>'
        f'<rect x="{lw}" width="{vw}" height="20" rx="3" fill="{color}"/>'
        f'<g fill="#fff" font-family="Verdana,Geneva,sans-serif" font-size="11" '
        f'text-anchor="middle"><text x="{lw // 2}" y="14">code quality</text>'
        f'<text x="{lw + vw // 2}" y="14">{value}</text></g></svg>'
    )


def sev_dot(sev: Severity) -> str:
    return f'<span class="scr-dot" style="background:{SEV_COLOR[sev]};"></span>'


# --------------------------------------------------------------------------- #
# Result rendering — single file
# --------------------------------------------------------------------------- #
def render_quality_gate(grade: str, score: float, threshold: str,
                        subject: str = "This code") -> None:
    passed = GRADE_RANK[grade] >= GRADE_RANK[threshold]
    if passed:
        bg, border, color, icon, status = ("#ECF7F1", "#BCE3CE", GREEN_DARK,
                                           ICON_CHECK, "Pass")
    else:
        bg, border, color, icon, status = ("#FBECEC", "#EEBEBE", "#B4282C",
                                           ICON_BLOCK, "Blocked")
    verb = "passes" if passed else "is blocked by"
    st.markdown(
        f"""<div class="scr-gate" style="background:{bg};border-color:{border};">
            <span class="ico" style="color:{color};">{icon}</span>
            <span class="txt">{subject} <b>{verb}</b> the quality gate &nbsp;·&nbsp;
            grade <b>{grade}</b> ({score:.0f}/100) vs. minimum <b>{threshold}</b>
            <span class="scr-status" style="background:{color};color:#fff;">{status}</span>
            </span></div>""",
        unsafe_allow_html=True)


def render_grade_hero(result: reviewer.ReviewResult) -> None:
    g = result.overall_grade
    color = GRADE_COLOR.get(g, MUTED)
    counts = result.counts_by_severity()
    c1, c2 = st.columns([1, 2.4])
    with c1:
        st.markdown(
            f"""<div class="scr-card" style="text-align:center;">
              <div class="scr-label">Overall grade</div>
              <div class="scr-grade" style="color:{color};">{g}</div>
              <div style="color:{MUTED};font-size:0.9rem;">{grade_label(g)}</div>
              <div class="scr-mono" style="font-size:1.2rem;font-weight:600;
                   color:{INK};margin-top:8px;">{result.overall_score}<span
                   style="font-size:0.85rem;color:{FAINT};">/100</span></div>
            </div>""",
            unsafe_allow_html=True)
    with c2:
        st.plotly_chart(radar_chart(result), use_container_width=True,
                        config={"displayModeBar": False})

    cols = st.columns(4)
    for col, sev in zip(cols, Severity):
        col.markdown(
            f"""<div class="scr-card" style="text-align:center;">
                <div class="scr-value">{sev_dot(sev)}{counts[sev]}</div>
                <div class="scr-label" style="margin-top:6px;">{sev.value}</div></div>""",
            unsafe_allow_html=True)


def render_insights(result: reviewer.ReviewResult) -> None:
    weight = {Severity.CRITICAL: 5, Severity.MAJOR: 3, Severity.MINOR: 1.5,
              Severity.INFO: 0.5}
    minutes = round(2 + sum(weight[f.severity] for f in result.findings))
    debt = sum(1 for f in result.findings
               if f.severity in (Severity.CRITICAL, Severity.MAJOR, Severity.MINOR))
    focus = min(Dimension, key=lambda d: result.dimension_scores[d].score)
    focus_txt = focus.value if result.dimension_scores[focus].score < 99.5 else "None"
    ai_n = sum(1 for f in result.findings if f.source == "ai")
    static_n = len(result.findings) - ai_n

    items = [("Est. review time saved", f"~{minutes} min"),
             ("Tech-debt items", debt),
             ("Focus area", focus_txt),
             ("Found by", f"{static_n} static · {ai_n} AI")]
    cols = st.columns(len(items))
    for col, (label, value) in zip(cols, items):
        col.markdown(
            f"""<div class="scr-card"><div class="scr-label">{label}</div>
                <div class="scr-value" style="font-size:1.3rem;">{value}</div></div>""",
            unsafe_allow_html=True)


def render_metrics(result: reviewer.ReviewResult) -> None:
    m = result.metrics
    items = [("Language", m.get("language", "—")),
             ("Lines of code", m.get("code_lines", "—")),
             ("Functions", m.get("functions", "—")),
             ("Comment density", f"{m.get('comment_density', 0)}%")]
    if "avg_complexity" in m:
        items += [("Avg complexity", m.get("avg_complexity", "—")),
                  ("Max complexity", m.get("max_complexity", "—"))]
    cols = st.columns(len(items))
    for col, (label, value) in zip(cols, items):
        col.markdown(
            f"""<div class="scr-card"><div class="scr-label">{label}</div>
                <div class="scr-value" style="font-size:1.3rem;">{value}</div></div>""",
            unsafe_allow_html=True)


def render_dimension_cards(result: reviewer.ReviewResult) -> None:
    cols = st.columns(3)
    for col, dim in zip(cols, Dimension):
        ds = result.dimension_scores[dim]
        color = GRADE_COLOR.get(ds.grade, MUTED)
        n = len(result.findings_for(dim))
        col.markdown(
            f"""<div class="scr-card">
                <div class="scr-label">{dim.value}</div>
                <div style="display:flex;align-items:baseline;gap:9px;">
                  <span class="scr-value" style="color:{color};">{ds.score}</span>
                  <span class="scr-badge" style="background:{color};">{ds.grade}</span>
                </div>
                <div style="color:{MUTED};font-size:0.82rem;margin-top:5px;">
                  {n} finding{'s' if n != 1 else ''}</div>
                <div style="background:{PAPER_2};border-radius:6px;height:6px;
                     margin-top:9px;overflow:hidden;border:1px solid {LINE};">
                  <div style="width:{ds.score}%;height:6px;background:{color};"></div>
                </div></div>""",
            unsafe_allow_html=True)


def render_finding(f: reviewer.Finding) -> None:
    color = SEV_COLOR[f.severity]
    loc = f'<span class="scr-loc">line {f.line}</span>' if f.line else ""
    src = "AI" if f.source == "ai" else "Static"
    st.markdown(
        f"""<div class="scr-finding" style="border-left-color:{color};">
          <div><span class="scr-badge" style="background:{color};">{f.severity.value}</span>
            <span class="scr-tag">{f.dimension.value}</span>
            <span class="scr-tag">{src}</span>{loc}</div>
          <div style="font-weight:600;color:{INK};margin-top:7px;">{html.escape(f.title)}</div>
          <div style="color:{MUTED};font-size:0.9rem;margin-top:2px;">{html.escape(f.message)}</div>
          {'<div class="scr-fix"><b>Fix →</b> ' + html.escape(f.suggestion) + '</div>' if f.suggestion else ''}
        </div>""",
        unsafe_allow_html=True)


def render_findings(result: reviewer.ReviewResult) -> None:
    if not result.findings:
        st.success("No issues found — clean across all three dimensions.")
        return
    fc1, fc2 = st.columns(2)
    sev_filter = fc1.multiselect("Severity", [s.value for s in Severity],
                                 default=[s.value for s in Severity])
    dim_filter = fc2.multiselect("Dimension", [d.value for d in Dimension],
                                 default=[d.value for d in Dimension])
    shown = [f for f in result.findings
             if f.severity.value in sev_filter and f.dimension.value in dim_filter]
    st.caption(f"Showing {len(shown)} of {len(result.findings)} findings")
    for f in shown:
        render_finding(f)


def render_annotated_code(source: str, result: reviewer.ReviewResult) -> None:
    by_line: dict[int, list] = {}
    for f in result.findings:
        if f.line:
            by_line.setdefault(f.line, []).append(f)

    lines = source.split("\n")
    if len(lines) > 700:
        st.info("File is large — showing the first 700 lines.")
        lines = lines[:700]

    rows: list[str] = []
    for i, raw in enumerate(lines, start=1):
        code = html.escape(raw) if raw else "&nbsp;"
        fs = by_line.get(i)
        if fs:
            worst = min(fs, key=lambda f: SEVERITY_RANK[f.severity])
            color = SEV_COLOR[worst.severity]
            tint = SEV_TINT[worst.severity]
            rows.append(
                f'<div class="scr-row" style="background:{tint};'
                f'border-left:3px solid {color};">'
                f'<div class="scr-gutter">{i}</div>'
                f'<div class="scr-codetext">{code}</div></div>')
            for f in fs:
                c = SEV_COLOR[f.severity]
                rows.append(
                    f'<div class="scr-note">'
                    f'<span class="scr-badge" style="background:{c};">'
                    f'{f.severity.value}</span> '
                    f'<b style="color:{INK};">{html.escape(f.title)}</b> — '
                    f'<span style="color:{MUTED};">{html.escape(f.message)}</span>'
                    f'</div>')
        else:
            rows.append(
                f'<div class="scr-row"><div class="scr-gutter">{i}</div>'
                f'<div class="scr-codetext">{code}</div></div>')
    st.markdown(f'<div class="scr-code">{"".join(rows)}</div>',
                unsafe_allow_html=True)


def render_ai_section(result: reviewer.ReviewResult) -> None:
    if not result.ai_used:
        st.caption("Turn on Deep review with Claude in the sidebar (with an API "
                   "key) to add an AI summary and a refactor suggestion.")
        return
    if result.summary:
        st.info(result.summary)
    if result.refactor:
        st.markdown("**Suggested refactor of the worst section**")
        st.code(result.refactor, language=result.language.lower())


# --------------------------------------------------------------------------- #
# Exports
# --------------------------------------------------------------------------- #
def build_report(result: reviewer.ReviewResult, filename: str, gate: str) -> str:
    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    passed = GRADE_RANK[result.overall_grade] >= GRADE_RANK[gate]
    lines = [
        f"# Code Review Report — {filename or 'snippet'}",
        f"_Generated by Smart Code Reviewer on {now}_", "",
        f"**Overall grade: {result.overall_grade} ({result.overall_score}/100 — "
        f"{grade_label(result.overall_grade)})**",
        f"**Quality gate (min {gate}): {'PASS' if passed else 'FAIL'}**", "",
        "## Dimension scores",
    ]
    for dim in Dimension:
        ds = result.dimension_scores[dim]
        lines.append(f"- **{dim.value}**: {ds.score}/100 ({ds.grade})")
    if result.ai_used and result.summary:
        lines += ["", "## Reviewer summary", result.summary]
    lines += ["", f"## Findings ({len(result.findings)})"]
    if not result.findings:
        lines.append("No issues found.")
    for f in result.findings:
        loc = f" (line {f.line})" if f.line else ""
        lines += [f"\n### [{f.severity.value}] {f.title}{loc}",
                  f"- **Dimension:** {f.dimension.value} · "
                  f"**Source:** {'AI' if f.source == 'ai' else 'static'}",
                  f"- {f.message}"]
        if f.suggestion:
            lines.append(f"- Fix: _{f.suggestion}_")
    if result.ai_used and result.refactor:
        lines += ["", "## Suggested refactor",
                  f"```{result.language.lower()}", result.refactor, "```"]
    return "\n".join(lines)


def build_json_report(result: reviewer.ReviewResult, filename: str,
                      gate: str) -> str:
    passed = GRADE_RANK[result.overall_grade] >= GRADE_RANK[gate]
    payload = {
        "tool": "Smart Code Reviewer",
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "file": filename or "snippet", "language": result.language,
        "overall": {"grade": result.overall_grade, "score": result.overall_score},
        "quality_gate": {"min_grade": gate, "passed": passed},
        "dimensions": {d.value: {"score": result.dimension_scores[d].score,
                                 "grade": result.dimension_scores[d].grade}
                       for d in Dimension},
        "metrics": result.metrics, "ai_used": result.ai_used,
        "findings": [{"severity": f.severity.value, "dimension": f.dimension.value,
                      "title": f.title, "message": f.message,
                      "suggestion": f.suggestion, "line": f.line,
                      "source": f.source, "rule_id": f.rule_id}
                     for f in result.findings],
    }
    return json.dumps(payload, indent=2)


def render_downloads(result, filename, gate) -> None:
    c1, c2, c3 = st.columns(3)
    c1.download_button("Markdown report", build_report(result, filename, gate),
                       file_name="code_review_report.md", mime="text/markdown",
                       use_container_width=True)
    c2.download_button("JSON (for CI)", build_json_report(result, filename, gate),
                       file_name="code_review.json", mime="application/json",
                       use_container_width=True)
    c3.download_button("Grade badge (SVG)",
                       make_badge_svg(result.overall_grade, result.overall_score),
                       file_name="code_quality_badge.svg", mime="image/svg+xml",
                       use_container_width=True)
    badge = make_badge_svg(result.overall_grade, result.overall_score)
    st.markdown(
        f"<div style='margin-top:8px;color:{MUTED};font-size:0.85rem;'>"
        f"Embeddable badge &nbsp; {badge}</div>", unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Project mode
# --------------------------------------------------------------------------- #
def review_project(files: dict[str, str]) -> dict[str, reviewer.ReviewResult]:
    results: dict[str, reviewer.ReviewResult] = {}
    progress = st.progress(0.0, text="Reviewing project…")
    total = len(files)
    for idx, (name, src) in enumerate(sorted(files.items()), start=1):
        lang = reviewer.detect_language(name, src)
        results[name] = reviewer.review(src, lang)
        progress.progress(idx / total, text=f"Reviewing {name}")
    progress.empty()
    return results


def _project_aggregate(results: dict[str, reviewer.ReviewResult]) -> tuple[float, str]:
    weights = {n: max(r.metrics.get("code_lines", 0), 1) for n, r in results.items()}
    total = sum(weights.values()) or 1
    score = sum(r.overall_score * weights[n] for n, r in results.items()) / total
    return round(score, 1), score_to_grade(score)


def render_project_dashboard(results: dict[str, reviewer.ReviewResult],
                             gate: str) -> None:
    agg_score, agg_grade = _project_aggregate(results)
    total_findings = sum(len(r.findings) for r in results.values())
    serious = sum(1 for r in results.values() for f in r.findings
                  if f.severity in (Severity.CRITICAL, Severity.MAJOR))
    ranked = sorted(results.items(), key=lambda kv: kv[1].overall_score)
    worst_name = ranked[0][0] if ranked else "—"

    render_quality_gate(agg_grade, agg_score, gate, subject="This project")

    color = GRADE_COLOR.get(agg_grade, MUTED)
    cols = st.columns(5)
    cards = [
        ("Project grade",
         f"<span style='color:{color};'>{agg_grade}</span> "
         f"<span style='font-size:0.95rem;color:{FAINT};'>{agg_score}</span>"),
        ("Files reviewed", len(results)),
        ("Total findings", total_findings),
        ("Critical + Major", serious),
        ("Lowest-graded",
         f"<span style='font-size:0.85rem;'>{html.escape(worst_name)}</span>"),
    ]
    for col, (label, value) in zip(cols, cards):
        col.markdown(
            f"""<div class="scr-card"><div class="scr-label">{label}</div>
                <div class="scr-value" style="font-size:1.3rem;">{value}</div></div>""",
            unsafe_allow_html=True)

    st.write("")
    names = [n for n, _ in ranked]
    scores = [r.overall_score for _, r in ranked]
    bar_colors = [GRADE_COLOR.get(r.overall_grade, MUTED) for _, r in ranked]
    fig = go.Figure(go.Bar(x=scores, y=names, orientation="h",
                           marker_color=bar_colors,
                           hovertemplate="%{y}: %{x}/100<extra></extra>"))
    fig.update_layout(
        height=max(220, 26 * len(names) + 60), margin=dict(l=10, r=20, t=10, b=20),
        xaxis=dict(range=[0, 100], title="score", gridcolor=LINE),
        font=dict(family="IBM Plex Sans", color=MUTED),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    head = ("<table class='scr-ptable'><tr><th>File</th><th>Lang</th>"
            "<th>Grade</th><th>Score</th><th>Findings</th><th>Crit/Maj</th></tr>")
    body = []
    for name, r in ranked:
        c = GRADE_COLOR.get(r.overall_grade, MUTED)
        cm = sum(1 for f in r.findings
                 if f.severity in (Severity.CRITICAL, Severity.MAJOR))
        body.append(
            f"<tr><td>{html.escape(name)}</td><td>{r.metrics.get('language','')}</td>"
            f"<td><span class='scr-badge' style='background:{c};'>{r.overall_grade}"
            f"</span></td><td class='num'>{r.overall_score}</td>"
            f"<td class='num'>{len(r.findings)}</td><td class='num'>{cm}</td></tr>")
    st.markdown(head + "".join(body) + "</table>", unsafe_allow_html=True)

    st.write("")
    st.markdown("#### Drill into a file")
    for name, r in ranked:
        with st.expander(f"{r.overall_grade} · {name} — {r.overall_score}/100 "
                         f"({len(r.findings)} findings)"):
            for f in r.findings[:40]:
                render_finding(f)
            if not r.findings:
                st.success("Clean.")

    summary = {
        "tool": "Smart Code Reviewer — project",
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "project": {"grade": agg_grade, "score": agg_score, "files": len(results),
                    "total_findings": total_findings, "critical_major": serious,
                    "quality_gate": {"min_grade": gate,
                                     "passed": GRADE_RANK[agg_grade] >= GRADE_RANK[gate]}},
        "files": {n: {"grade": r.overall_grade, "score": r.overall_score,
                      "findings": len(r.findings)} for n, r in ranked},
    }
    st.download_button("Project report (JSON)", json.dumps(summary, indent=2),
                       file_name="project_review.json", mime="application/json")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def run_single(settings: dict) -> None:
    source, filename = single_input()
    lang_guess = reviewer.detect_language(filename, source) if source else "Python"
    c1, c2 = st.columns([1, 2], vertical_alignment="bottom")
    language = c1.selectbox(
        "Language", reviewer.SUPPORTED_LANGUAGES,
        index=reviewer.SUPPORTED_LANGUAGES.index(lang_guess)
        if lang_guess in reviewer.SUPPORTED_LANGUAGES else 0)
    run = c2.button("Review code", use_container_width=True)

    if run:
        if not source.strip():
            st.warning("Add some code first — paste, upload, or pick a sample.")
            return
        if settings["use_ai"] and not settings["api_key"]:
            st.warning("Deep review is on but no API key was provided. "
                       "Running the static engine only.")
        try:
            with st.spinner("Reviewing…"):
                result = reviewer.review(
                    source, language,
                    use_ai=settings["use_ai"] and bool(settings["api_key"]),
                    api_key=settings["api_key"], model=settings["model"])
            st.session_state["result"] = result
            st.session_state["source"] = source
            st.session_state["filename"] = filename
        except Exception as exc:
            st.error(f"Review failed: {exc}")
            return

    result = st.session_state.get("result")
    if result is None:
        st.markdown("<div class='scr-foot'>Pick a sample and select "
                    "Review code to see it in action.</div>",
                    unsafe_allow_html=True)
        return

    st.divider()
    render_quality_gate(result.overall_grade, result.overall_score,
                        settings["gate_grade"])
    render_grade_hero(result)
    st.write("")
    render_insights(result)
    st.write("")
    render_metrics(result)
    st.write("")
    render_dimension_cards(result)
    st.write("")

    t_find, t_code, t_chart, t_ai = st.tabs(
        ["Findings", "Annotated code", "Distribution", "AI review"])
    with t_find:
        render_findings(result)
    with t_code:
        render_annotated_code(st.session_state.get("source", ""), result)
    with t_chart:
        st.plotly_chart(findings_bar(result), use_container_width=True,
                        config={"displayModeBar": False})
    with t_ai:
        render_ai_section(result)

    st.write("")
    render_downloads(result, st.session_state.get("filename", ""),
                     settings["gate_grade"])


def run_project(settings: dict) -> None:
    files = project_input()
    if st.button("Review project"):
        if not files:
            st.warning("Load some files first (multiple files, a .zip, or a "
                       "folder path).")
            return
        st.session_state["proj_results"] = review_project(files)

    results = st.session_state.get("proj_results")
    if results:
        st.divider()
        render_project_dashboard(results, settings["gate_grade"])
    else:
        st.markdown("<div class='scr-foot'>Load a repo (multiple files, a .zip, "
                    "or a local folder) and select Review project.</div>",
                    unsafe_allow_html=True)


def main() -> None:
    inject_css()
    hero()
    settings = sidebar()

    mode = st.radio("Mode", ["Single file", "Project (repo / folder)"],
                    horizontal=True, label_visibility="collapsed")
    if mode == "Single file":
        run_single(settings)
    else:
        run_project(settings)

    st.markdown(
        "<div class='scr-foot'>Built by <b>Rahul</b> — Careem challenge · "
        "static engine + Claude Opus 4.8</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
