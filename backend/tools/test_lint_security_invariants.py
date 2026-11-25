"""Self-test for the security-invariants AST linter (Forgejo #10).

Run with: ``python tools/test_lint_security_invariants.py``.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lint_security_invariants import scan  # noqa: E402

# fmt: off
CLEAN = '''
import subprocess
from sqlalchemy import text

def ok(conn, name):
    conn.execute(text("SELECT * FROM t WHERE name = :n"), {"n": name})
    conn.execute(text(f"SELECT 1 FROM {TABLE}"))  # sql-identifiers-only
    row = (
        conn
        .execute(
            text(f"SELECT 1 FROM {TABLE} WHERE id=:id"), {"id": 1}
        )  # sql-identifiers-only
        .fetchone()
    )
    subprocess.run(["ffprobe", name], check=True)
    subprocess.run(["true"], shell=False)
'''

SQL_FSTRING = '''
from sqlalchemy import text
def bad(conn, name):
    conn.execute(text(f"SELECT * FROM t WHERE name = '{name}'"))
'''

SQL_CONCAT = '''
def bad(cur, name):
    cur.execute("DELETE FROM t WHERE name = '" + name + "'")
'''

SQL_FORMAT = '''
def bad(cur, name):
    cur.execute("SELECT {}".format(name))
'''

SHELL_TRUE = '''
import subprocess
def bad(cmd):
    subprocess.run(cmd, shell=True)
'''

OS_SYSTEM = '''
import os
def bad(cmd):
    os.system(cmd)
'''
# fmt: on


def _scan(files: dict[str, str]) -> list[tuple[str, str]]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, body in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        return [(p.relative_to(root).as_posix(), rule) for p, _line, rule in scan(root)]


def main() -> int:
    cases = {
        "clean.py": (CLEAN, []),
        "sql_fstring.py": (SQL_FSTRING, ["sql"]),
        "sql_concat.py": (SQL_CONCAT, ["sql"]),
        "sql_format.py": (SQL_FORMAT, ["sql"]),
        "shell_true.py": (SHELL_TRUE, ["shell"]),
        "os_system.py": (OS_SYSTEM, ["shell"]),
        "db/migrations/versions/m.py": (SQL_FSTRING, []),
    }
    failed = 0
    for name, (body, expected) in cases.items():
        got = [rule for _path, rule in _scan({name: body})]
        if got != expected:
            print(f"FAIL {name}: expected {expected}, got {got}")
            failed += 1
    if failed:
        return 1
    print(f"security-invariants linter self-test: {len(cases)} cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
