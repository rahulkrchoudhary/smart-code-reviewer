"""The heuristic static-analysis engine.

This is what makes the reviewer useful *with no API key at all*. For Python it
walks the real AST (complexity, nesting, naming, mutable defaults, …). For every
other language it falls back to a language-agnostic line scanner. Both feed the
same `Finding` model the AI layer uses, so the UI never has to care where an
issue came from.
"""
from __future__ import annotations

import ast
import re

from .models import Dimension, Finding, Severity

# Loop/throwaway names that are fine even though they're short.
_OK_SHORT_NAMES = {"i", "j", "k", "n", "x", "y", "z", "_", "id", "ok", "fn", "db"}
# Names that are technically valid but read as placeholders in real code.
_VAGUE_NAMES = {"data", "data2", "temp", "tmp", "foo", "bar", "baz", "val", "obj",
                "thing", "stuff", "res", "ret", "var", "arr", "lst", "dct"}
_AMBIGUOUS_SINGLE = {"l", "I", "O"}  # PEP 8 E741 — easily confused with 1/0

_MAGIC_OK = {0, 1, 2, -1, 100, 1000}

_CAMEL_RE = re.compile(r"^[a-z]+[A-Z]")
_SNAKE_OK_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
_PASCAL_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")


# --------------------------------------------------------------------------- #
# Python AST analysis
# --------------------------------------------------------------------------- #

_BRANCHING_NODES = (
    ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler,
    ast.With, ast.AsyncWith, ast.Assert, ast.comprehension,
)


def _complexity(node: ast.AST) -> int:
    """A McCabe-style cyclomatic complexity count for one function body."""
    score = 1
    for child in ast.walk(node):
        if isinstance(child, _BRANCHING_NODES):
            score += 1
        elif isinstance(child, ast.BoolOp):
            score += len(child.values) - 1
        elif isinstance(child, ast.IfExp):  # ternary
            score += 1
    return score


def _max_nesting(node: ast.AST, depth: int = 0) -> int:
    nesting_nodes = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With,
                     ast.AsyncWith, ast.Try)
    deepest = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, nesting_nodes):
            deepest = max(deepest, _max_nesting(child, depth + 1))
        else:
            deepest = max(deepest, _max_nesting(child, depth))
    return deepest


class _PyVisitor(ast.NodeVisitor):
    def __init__(self, source_lines: list[str]):
        self.lines = source_lines
        self.findings: list[Finding] = []
        self.func_count = 0
        self.func_lengths: list[int] = []
        self.complexities: list[int] = []
        # id()s of literal nodes that are the value of a *named* constant
        # (e.g. TAX_RATE = 0.05) — naming them is exactly the fix we'd suggest,
        # so they must not be flagged as magic numbers.
        self.named_constant_ids: set[int] = set()

    # -- helpers ----------------------------------------------------------- #
    def add(self, dimension, severity, title, message, suggestion="", line=None,
            rule_id=""):
        self.findings.append(Finding(
            dimension=dimension, severity=severity, title=title, message=message,
            suggestion=suggestion, line=line, source="static", rule_id=rule_id,
        ))

    def _check_name(self, name: str, line: int, kind: str):
        if name in _AMBIGUOUS_SINGLE:
            self.add(Dimension.READABILITY, Severity.MINOR,
                     "Ambiguous single-character name",
                     f"`{name}` is easily confused with a digit (PEP 8 E741).",
                     "Rename it to something descriptive.", line, "PY-NAME-AMBIG")
        elif name in _VAGUE_NAMES:
            self.add(Dimension.READABILITY, Severity.MINOR,
                     "Vague identifier name",
                     f"`{name}` doesn't say what it holds — readers have to guess.",
                     "Name it after the value it represents (e.g. `customer`, "
                     "`pending_orders`).", line, "PY-NAME-VAGUE")
        elif kind in ("function", "variable") and _CAMEL_RE.match(name):
            self.add(Dimension.READABILITY, Severity.MINOR,
                     "Non-idiomatic naming (camelCase)",
                     f"`{name}` uses camelCase; Python convention is snake_case.",
                     f"Rename to `{_to_snake(name)}`.", line, "PY-NAME-CASE")

    # -- visitors ---------------------------------------------------------- #
    def visit_FunctionDef(self, node: ast.FunctionDef):  # noqa: N802
        self._handle_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):  # noqa: N802
        self._handle_function(node)
        self.generic_visit(node)

    def _handle_function(self, node):
        self.func_count += 1
        start = node.lineno
        end = getattr(node, "end_lineno", start) or start
        length = end - start
        self.func_lengths.append(length)
        is_public = not node.name.startswith("_")

        self._check_name(node.name, start, "function")

        # Length
        if length > 50:
            self.add(Dimension.STRUCTURE, Severity.MAJOR, "Very long function",
                     f"`{node.name}` spans ~{length} lines — too much to hold in "
                     "your head at once.",
                     "Extract cohesive blocks into named helper functions.",
                     start, "PY-FN-LONG")
        elif length > 30:
            self.add(Dimension.STRUCTURE, Severity.MINOR, "Long function",
                     f"`{node.name}` is ~{length} lines.",
                     "Consider splitting out one or two helpers.", start,
                     "PY-FN-LONGISH")

        # Complexity
        cx = _complexity(node)
        self.complexities.append(cx)
        if cx > 15:
            self.add(Dimension.STRUCTURE, Severity.MAJOR, "High cyclomatic complexity",
                     f"`{node.name}` has complexity {cx} — many independent paths "
                     "to test and reason about.",
                     "Flatten nested conditionals; use guard clauses or a lookup "
                     "table.", start, "PY-FN-COMPLEX")
        elif cx > 10:
            self.add(Dimension.STRUCTURE, Severity.MINOR, "Elevated complexity",
                     f"`{node.name}` has complexity {cx}.",
                     "Watch for growth; consider early returns.", start,
                     "PY-FN-COMPLEXISH")

        # Nesting
        nesting = _max_nesting(node)
        if nesting >= 4:
            self.add(Dimension.STRUCTURE, Severity.MINOR, "Deep nesting",
                     f"`{node.name}` nests {nesting} levels deep.",
                     "Invert conditions and return early to flatten the pyramid.",
                     start, "PY-FN-NEST")

        # Parameter count (ignore self/cls)
        args = node.args
        positional = [a for a in args.args if a.arg not in ("self", "cls")]
        total_params = len(positional) + len(args.kwonlyargs)
        if total_params > 6:
            self.add(Dimension.STRUCTURE, Severity.MINOR, "Too many parameters",
                     f"`{node.name}` takes {total_params} parameters.",
                     "Group related arguments into a dataclass or config object.",
                     start, "PY-FN-PARAMS")

        # Mutable default arguments
        for default in args.defaults + args.kw_defaults:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                self.add(Dimension.MAINTAINABILITY, Severity.MAJOR,
                         "Mutable default argument",
                         f"`{node.name}` has a mutable default ([] / {{}}) that is "
                         "shared across all calls — a classic Python bug.",
                         "Default to None and create the container inside the body.",
                         start, "PY-FN-MUTDEFAULT")

        # Missing docstring on public API
        if is_public and ast.get_docstring(node) is None and length > 8:
            self.add(Dimension.READABILITY, Severity.INFO, "Missing docstring",
                     f"Public function `{node.name}` has no docstring.",
                     "Add a one-line summary of what it does and returns.",
                     start, "PY-FN-DOC")

        for arg in positional:
            self._check_name(arg.arg, start, "variable")

    def visit_ClassDef(self, node: ast.ClassDef):  # noqa: N802
        if not _PASCAL_RE.match(node.name):
            self.add(Dimension.READABILITY, Severity.MINOR,
                     "Non-idiomatic class name",
                     f"`{node.name}` should be PascalCase.",
                     "Rename, e.g. `OrderProcessor`.", node.lineno, "PY-CLS-CASE")
        if ast.get_docstring(node) is None:
            self.add(Dimension.READABILITY, Severity.INFO, "Missing class docstring",
                     f"Class `{node.name}` has no docstring.",
                     "Describe the responsibility of the class.", node.lineno,
                     "PY-CLS-DOC")
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler):  # noqa: N802
        if node.type is None:
            self.add(Dimension.MAINTAINABILITY, Severity.MAJOR, "Bare except",
                     "`except:` swallows *every* error, including KeyboardInterrupt "
                     "and real bugs.",
                     "Catch the specific exception you expect.", node.lineno,
                     "PY-EXC-BARE")
        # except ...: pass  -> silently swallowed error
        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            self.add(Dimension.MAINTAINABILITY, Severity.MINOR,
                     "Silently swallowed exception",
                     "This except block does nothing, hiding failures.",
                     "At minimum log the error, or handle it.", node.lineno,
                     "PY-EXC-PASS")
        self.generic_visit(node)

    def visit_Global(self, node: ast.Global):  # noqa: N802
        self.add(Dimension.MAINTAINABILITY, Severity.MINOR, "Use of `global`",
                 "Mutable global state makes behaviour hard to trace and test.",
                 "Pass state explicitly or wrap it in a class.", node.lineno,
                 "PY-GLOBAL")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):  # noqa: N802
        func = node.func
        if isinstance(func, ast.Name) and func.id == "print":
            self.add(Dimension.MAINTAINABILITY, Severity.INFO,
                     "`print` left in code",
                     "A stray print is usually a leftover debug statement.",
                     "Use the `logging` module so output can be controlled.",
                     node.lineno, "PY-PRINT")
        if isinstance(func, ast.Name) and func.id == "eval":
            self.add(Dimension.MAINTAINABILITY, Severity.CRITICAL,
                     "Use of `eval`",
                     "`eval` executes arbitrary code — a serious security risk if "
                     "any input is untrusted.",
                     "Replace with `ast.literal_eval` or explicit parsing.",
                     node.lineno, "PY-EVAL")
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant):  # noqa: N802
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            self._magic_number(node.value, node.lineno, node)

    def _magic_number(self, value, line, node=None):
        if value is None or value in _MAGIC_OK:
            return
        if node is not None and id(node) in self.named_constant_ids:
            return
        # Only flag once per line to avoid noise.
        if any(f.line == line and f.rule_id == "PY-MAGIC" for f in self.findings):
            return
        self.add(Dimension.READABILITY, Severity.INFO, "Magic number",
                 f"The literal `{value}` has no name explaining its meaning.",
                 "Extract it into a named constant.", line, "PY-MAGIC")


def _collect_named_constants(tree: ast.AST) -> set[int]:
    """Find literals that are being *named* by an assignment.

    `RATE = 0.05` or `LIMITS = {"a": 10}` give the number a name, so they should
    not be reported as magic numbers — but `total = price * 1.2` leaves 1.2 inline
    and is still flagged.
    """
    named: set[int] = set()

    def mark(value):
        if isinstance(value, ast.Constant):
            named.add(id(value))
        elif isinstance(value, (ast.List, ast.Set, ast.Tuple)):
            for elt in value.elts:
                named.add(id(elt))
        elif isinstance(value, ast.Dict):
            for elt in value.values:
                named.add(id(elt))

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and all(
            isinstance(t, ast.Name) for t in node.targets
        ):
            mark(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                and node.value is not None:
            mark(node.value)
    return named


def _to_snake(name: str) -> str:
    out = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    return out


def analyze_python(source: str) -> tuple[list[Finding], dict]:
    lines = source.splitlines()
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        finding = Finding(
            dimension=Dimension.STRUCTURE, severity=Severity.CRITICAL,
            title="Syntax error", message=f"The code does not parse: {exc.msg}.",
            suggestion="Fix the syntax error before the rest can be reviewed.",
            line=exc.lineno, source="static", rule_id="PY-SYNTAX",
        )
        return [finding], _line_metrics(lines, language="Python")

    visitor = _PyVisitor(lines)
    visitor.named_constant_ids = _collect_named_constants(tree)
    visitor.visit(tree)
    findings = visitor.findings
    findings += _line_scan(lines, language="Python")

    metrics = _line_metrics(lines, language="Python")
    metrics.update({
        "functions": visitor.func_count,
        "avg_function_length": round(
            sum(visitor.func_lengths) / len(visitor.func_lengths), 1
        ) if visitor.func_lengths else 0,
        "max_complexity": max(visitor.complexities) if visitor.complexities else 0,
        "avg_complexity": round(
            sum(visitor.complexities) / len(visitor.complexities), 1
        ) if visitor.complexities else 0,
    })
    return findings, metrics


# --------------------------------------------------------------------------- #
# Language-agnostic line scanner (also runs on Python, on top of the AST)
# --------------------------------------------------------------------------- #

_TODO_RE = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")
_DEBUG_JS_RE = re.compile(r"\b(console\.(log|debug)|debugger)\b")
_LOOSE_EQ_RE = re.compile(r"[^=!<>]==[^=]")  # == not part of === / !==
_TRAILING_WS_RE = re.compile(r"[ \t]+$")


def _is_comment(line: str, language: str) -> bool:
    s = line.strip()
    if language == "Python":
        return s.startswith("#")
    return s.startswith("//") or s.startswith("*") or s.startswith("/*")


def _line_scan(lines: list[str], language: str) -> list[Finding]:
    findings: list[Finding] = []
    seen_todo = 0
    mixed_indent = False
    long_lines = 0

    for i, raw in enumerate(lines, start=1):
        # TODO / FIXME markers
        if _TODO_RE.search(raw) and seen_todo < 8:
            marker = _TODO_RE.search(raw).group(1)
            seen_todo += 1
            findings.append(Finding(
                Dimension.MAINTAINABILITY, Severity.INFO, f"{marker} marker",
                f"Unfinished work flagged inline: `{raw.strip()[:80]}`.",
                "Track it in an issue and remove the inline marker.", i,
                "GEN-TODO",
            ))

        # Very long lines
        if len(raw) > 120:
            long_lines += 1
            if long_lines <= 6:
                findings.append(Finding(
                    Dimension.READABILITY, Severity.INFO, "Long line",
                    f"Line is {len(raw)} characters — hard to read without "
                    "horizontal scrolling.",
                    "Wrap or refactor to stay under ~100 columns.", i, "GEN-LINELEN",
                ))

        # Trailing whitespace
        if _TRAILING_WS_RE.search(raw) and len(raw.strip()) > 0:
            # low-noise: only report the first few
            if sum(1 for f in findings if f.rule_id == "GEN-TRAILWS") < 3:
                findings.append(Finding(
                    Dimension.READABILITY, Severity.INFO, "Trailing whitespace",
                    "Trailing spaces create noisy diffs.",
                    "Configure your editor to trim trailing whitespace on save.", i,
                    "GEN-TRAILWS",
                ))

        # Mixed tabs/spaces indentation
        if raw.startswith("\t") and "    " in raw[:8]:
            mixed_indent = True

    if mixed_indent:
        findings.append(Finding(
            Dimension.READABILITY, Severity.MINOR, "Mixed tabs and spaces",
            "The file mixes tab and space indentation, which renders "
            "inconsistently across editors.",
            "Pick one (spaces, per convention) and run a formatter.", None,
            "GEN-MIXINDENT",
        ))

    return findings


def analyze_generic(source: str, language: str) -> tuple[list[Finding], dict]:
    """Best-effort review for non-Python languages using brace/indent heuristics."""
    lines = source.splitlines()
    findings = _line_scan(lines, language=language)

    brace_depth = 0
    func_starts: list[int] = []
    func_count = 0
    js_like = language in ("JavaScript", "TypeScript", "Java", "C", "C++", "C#",
                           "Go", "Rust", "PHP")

    func_decl_re = re.compile(
        r"\b(function|func|def|fn)\b|=>\s*\{|\b[A-Za-z_]\w*\s*\([^;{]*\)\s*\{"
    )

    for i, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if _is_comment(raw, language):
            continue

        if js_like:
            # Loose equality in JS/TS
            if language in ("JavaScript", "TypeScript") and _LOOSE_EQ_RE.search(raw) \
                    and "===" not in raw and "!==" not in raw:
                if sum(1 for f in findings if f.rule_id == "JS-LOOSEEQ") < 5:
                    findings.append(Finding(
                        Dimension.MAINTAINABILITY, Severity.MINOR,
                        "Loose equality (==)",
                        "`==` does type coercion and causes subtle bugs.",
                        "Use strict equality `===` / `!==`.", i, "JS-LOOSEEQ",
                    ))
            # var usage
            if language in ("JavaScript", "TypeScript") and re.match(r"^\s*var\s", raw):
                if sum(1 for f in findings if f.rule_id == "JS-VAR") < 5:
                    findings.append(Finding(
                        Dimension.MAINTAINABILITY, Severity.MINOR,
                        "`var` declaration",
                        "`var` is function-scoped and error-prone.",
                        "Prefer `const` (or `let` when reassigned).", i, "JS-VAR",
                    ))
            # debug leftovers
            if _DEBUG_JS_RE.search(raw):
                findings.append(Finding(
                    Dimension.MAINTAINABILITY, Severity.INFO,
                    "Debug statement left in code",
                    f"`{stripped[:60]}` looks like leftover debugging.",
                    "Remove it or route through a logger.", i, "JS-DEBUG",
                ))

        if func_decl_re.search(stripped):
            func_count += 1
            func_starts.append(i)

        brace_depth += raw.count("{") - raw.count("}")
        if brace_depth >= 5:
            if sum(1 for f in findings if f.rule_id == "GEN-DEEPNEST") < 4:
                findings.append(Finding(
                    Dimension.STRUCTURE, Severity.MINOR, "Deeply nested block",
                    f"Block is nested ~{brace_depth} levels deep here.",
                    "Extract inner blocks into helper functions; return early.", i,
                    "GEN-DEEPNEST",
                ))

    metrics = _line_metrics(lines, language=language)
    metrics["functions"] = func_count
    return findings, metrics


# --------------------------------------------------------------------------- #
# Shared metrics
# --------------------------------------------------------------------------- #

def _line_metrics(lines: list[str], language: str) -> dict:
    total = len(lines)
    blank = sum(1 for ln in lines if not ln.strip())
    comments = sum(1 for ln in lines if _is_comment(ln, language))
    code = total - blank - comments
    comment_density = round(comments / code * 100, 1) if code else 0.0
    return {
        "language": language,
        "total_lines": total,
        "code_lines": code,
        "comment_lines": comments,
        "blank_lines": blank,
        "comment_density": comment_density,
    }


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #

def analyze(source: str, language: str) -> tuple[list[Finding], dict]:
    """Return (findings, metrics) for the given source and language."""
    if not source.strip():
        return [], _line_metrics(source.splitlines(), language)
    if language == "Python":
        return analyze_python(source)
    return analyze_generic(source, language)
