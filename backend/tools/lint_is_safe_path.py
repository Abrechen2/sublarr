"""AST linter — flag reversed is_safe_path(base, candidate) calls.

Sublarr's `security_utils.is_safe_path(candidate, base_dir)` takes the
user-supplied candidate first and the trusted base directory second.
Reversing the two arguments turns the gate into a no-op (or worse, a
universally-passing check) — see commits b03e305b (remux) and the cleanup
audit on 2026-04-30 for past instances.

This linter walks every Python file under backend/ and flags any
`is_safe_path(...)` call whose first positional argument looks like a
trust-base name and whose second looks like a user-controlled path.

Heuristic: classify each argument by the variable name. The known sets
were grown empirically from the codebase. Anything outside both sets is
"unknown" and we don't flag it.

Exit code 1 on any reversed call, 0 otherwise. Designed for pre-commit
and CI.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# Variable names that name a TRUST BOUNDARY (allowed as 2nd arg).
BASE_NAMES = {
    "media_path",
    "config_dir",
    "cache_dir",
    "trash_root",
    "tessdata_dir",
    "_trash_root",
    "_hooks_dir",
    "_batch_dir",
    "_video_root",
    "_media_path",
    "base_dir",
    "base",
    "root",
    "trust_root",
    "allowed_root",
    "scripts_root",
    "config_root",
}
# Names that hint at USER-CONTROLLED candidate paths (not allowed as 2nd arg).
CANDIDATE_NAMES = {
    "path",
    "file_path",
    "subtitle_path",
    "video_path",
    "output_path",
    "input_path",
    "tmp_path",
    "mapped_path",
    "target",
    "target_path",
    "script_path",
    "remote_path",
    "local_path",
    "backup_path",
    "remux_path",
    "trashed",
    "original",
    "candidate",
    "user_path",
    "fp",
    "f",
    "raw_path",
    "src",
    "dst",
    "src_path",
    "dst_path",
    "source_path",
    "dest_path",
}


def _classify(node: ast.AST) -> str:
    """Return 'base', 'candidate', or 'unknown' for an argument node."""
    # Bare name: foo
    if isinstance(node, ast.Name):
        if node.id in BASE_NAMES:
            return "base"
        if node.id in CANDIDATE_NAMES:
            return "candidate"
        # Suffix heuristic — anything ending _root or _dir leans base
        if node.id.endswith(("_root", "_dir")):
            return "base"
        if node.id.endswith("_path"):
            return "candidate"
        return "unknown"
    # Attribute: settings.media_path / s.config_dir
    if isinstance(node, ast.Attribute):
        if node.attr in BASE_NAMES or node.attr.endswith(("_root", "_dir")):
            return "base"
        if node.attr in CANDIDATE_NAMES or node.attr.endswith("_path"):
            return "candidate"
        return "unknown"
    # getattr(settings, "media_path", "/media")
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and isinstance(node.args[1].value, str)
    ):
        return _classify(ast.Name(id=node.args[1].value, ctx=ast.Load()))
    # String literal — bases sometimes appear as "/media" or similar.
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        # Plain absolute paths only — leans base. user-controlled strings
        # would normally arrive as variables, not literals.
        if node.value.startswith("/"):
            return "base"
        return "unknown"
    return "unknown"


class IsSafePathChecker(ast.NodeVisitor):
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.violations: list[tuple[int, str, str]] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 — ast API
        # Match is_safe_path(...) and security_utils.is_safe_path(...)
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
        else:
            self.generic_visit(node)
            return

        if name == "is_safe_path" and len(node.args) >= 2:
            first_kind = _classify(node.args[0])
            second_kind = _classify(node.args[1])
            if first_kind == "base" and second_kind == "candidate":
                self.violations.append(
                    (
                        node.lineno,
                        ast.unparse(node.args[0]),
                        ast.unparse(node.args[1]),
                    )
                )
        self.generic_visit(node)


_SKIP_DIR_PARTS = {"venv", ".venv", "site-packages", "__pycache__", "node_modules"}


def scan(root: Path) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    for py in root.rglob("*.py"):
        # Skip the linter itself, vendored deps, virtualenvs, build artifacts.
        parts = set(py.parts)
        if parts & _SKIP_DIR_PARTS:
            continue
        rel = py.relative_to(root).as_posix()
        if rel.startswith("tools/lint_is_safe_path") or rel.startswith("tests/"):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except (SyntaxError, UnicodeDecodeError):
            continue
        checker = IsSafePathChecker(py)
        checker.visit(tree)
        for line, first, second in checker.violations:
            findings.append((py, line, first, second))
    return findings


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent.parent
    findings = scan(root)
    if not findings:
        print(f"is_safe_path linter: clean ({root})")
        return 0
    print(f"is_safe_path linter: {len(findings)} reversed-arg violation(s):")
    for path, line, first, second in findings:
        rel = path.relative_to(root.parent) if path.is_absolute() else path
        print(f"  {rel}:{line}: is_safe_path({first}, {second})")
        print("    -> first arg looks like a TRUST BASE; second looks USER-CONTROLLED.")
        print("       Expected: is_safe_path(candidate, base_dir).")
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv))
