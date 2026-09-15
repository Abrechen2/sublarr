"""Reject local state before backend sources enter a runtime image layer.

Independent of .dockerignore: a missing or regressed ignore rule must fail a
build instead of publishing development credentials. Only paths are reported.
"""

import sys
from fnmatch import fnmatchcase
from pathlib import Path

source = Path(sys.argv[1]).resolve()
forbidden_directories = {
    "instance",
    "dev",
    "tests",
    "__tests__",
    "htmlcov",
    "coverage",
    "venv",
    ".venv",
    "log",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".benchmarks",
    "test-results",
}
forbidden_files = (
    "*.db*",
    "*.sqlite*",
    ".env",
    ".env.*",
    ".encryption_key",
    "*.log",
    ".coverage*",
    "coverage.*",
)
rejected = []
for path in source.rglob("*"):
    name = path.name.casefold()
    forbidden = path.is_dir() and name in forbidden_directories
    forbidden |= any(fnmatchcase(name, pattern) for pattern in forbidden_files)
    # Also detect SQLite databases renamed without their usual extension.
    if path.is_file() and not forbidden:
        with path.open("rb") as handle:
            forbidden = handle.read(16) == b"SQLite format 3\x00"
    if forbidden:
        rejected.append(path.relative_to(source).as_posix())

if rejected:
    print("Unsafe backend build context; exclude these paths in .dockerignore:")
    print("\n".join(sorted(rejected)))
    raise SystemExit(1)
print("Backend source audit passed: no local databases or development artifacts.")
