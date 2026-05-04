"""Self-test for the no-new-env-fields AST linter.

Builds a handful of synthetic ``config_settings.py`` variants and asserts
the linter reports the right violations on each.
Run with: ``python tools/test_lint_no_new_env_fields.py``.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lint_no_new_env_fields import lint  # noqa: E402

# fmt: off
GOOD = """
from pydantic import BaseModel
from pydantic_settings import BaseSettings

_ALLOWED_BOOT_FIELDS = frozenset({"port", "api_key"})

class BootSettings(BaseSettings):
    port: int = 5765
    api_key: str = ""

class UISettings(BaseModel):
    items_per_page: int = 25
    target_language: str = "de"

class Settings:
    pass
"""

EXTRA_BOOT_FIELD = """
from pydantic import BaseModel
from pydantic_settings import BaseSettings

_ALLOWED_BOOT_FIELDS = frozenset({"port"})

class BootSettings(BaseSettings):
    port: int = 5765
    smuggled_field: str = ""  # NOT in allowlist

class UISettings(BaseModel):
    foo: int = 1
"""

UI_SUBCLASSES_BASESETTINGS = """
from pydantic_settings import BaseSettings

_ALLOWED_BOOT_FIELDS = frozenset({"port"})

class BootSettings(BaseSettings):
    port: int = 5765

class UISettings(BaseSettings):  # WRONG — would re-enable env loading
    foo: int = 1
"""

OTHER_CLASS_SUBCLASSES_BASESETTINGS = """
from pydantic import BaseModel
from pydantic_settings import BaseSettings

_ALLOWED_BOOT_FIELDS = frozenset({"port"})

class BootSettings(BaseSettings):
    port: int = 5765

class UISettings(BaseModel):
    foo: int = 1

class SneakySettings(BaseSettings):  # WRONG — only BootSettings may
    debug: bool = False
"""

MISSING_ALLOWLIST = """
from pydantic import BaseModel
from pydantic_settings import BaseSettings

class BootSettings(BaseSettings):
    port: int = 5765

class UISettings(BaseModel):
    foo: int = 1
"""

ALLOWLIST_MISSING_FIELD = """
from pydantic import BaseModel
from pydantic_settings import BaseSettings

_ALLOWED_BOOT_FIELDS = frozenset({"port", "api_key"})

class BootSettings(BaseSettings):
    port: int = 5765
    # api_key declared in allowlist but missing on the class

class UISettings(BaseModel):
    foo: int = 1
"""
# fmt: on


def _write(content: str) -> Path:
    fd, name = tempfile.mkstemp(suffix=".py")
    os.close(fd)  # Windows: leaving the fd open blocks the later unlink().
    f = Path(name)
    f.write_text(content, encoding="utf-8")
    return f


def main() -> int:
    failures: list[str] = []

    # 1. GOOD — no violations expected.
    p = _write(GOOD)
    v = lint(p)
    if v:
        failures.append(f"GOOD case must be clean, got {v}")
    p.unlink()

    # 2. Boot field outside allowlist — expect 1 violation mentioning the field.
    p = _write(EXTRA_BOOT_FIELD)
    v = lint(p)
    if not any("smuggled_field" in m for m in v):
        failures.append(f"EXTRA_BOOT_FIELD must flag smuggled_field, got {v}")
    p.unlink()

    # 3. UISettings(BaseSettings) — expect violation about UISettings.
    p = _write(UI_SUBCLASSES_BASESETTINGS)
    v = lint(p)
    if not any("UISettings must NOT subclass BaseSettings" in m for m in v):
        failures.append(f"UI_SUBCLASSES_BASESETTINGS must flag UISettings, got {v}")
    p.unlink()

    # 4. Some other class subclasses BaseSettings — expect violation naming it.
    p = _write(OTHER_CLASS_SUBCLASSES_BASESETTINGS)
    v = lint(p)
    if not any("SneakySettings" in m for m in v):
        failures.append(f"OTHER_CLASS must flag SneakySettings, got {v}")
    p.unlink()

    # 5. Allowlist missing entirely.
    p = _write(MISSING_ALLOWLIST)
    v = lint(p)
    if not any("_ALLOWED_BOOT_FIELDS" in m for m in v):
        failures.append(f"MISSING_ALLOWLIST must flag missing allowlist, got {v}")
    p.unlink()

    # 6. Allowlist names a field BootSettings doesn't declare.
    p = _write(ALLOWLIST_MISSING_FIELD)
    v = lint(p)
    if not any("missing fields" in m for m in v):
        failures.append(f"ALLOWLIST_MISSING_FIELD must flag missing fields, got {v}")
    p.unlink()

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1

    print("no-new-env-fields linter self-test: ok (6 cases checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
