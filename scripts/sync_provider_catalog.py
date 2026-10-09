#!/usr/bin/env python3
"""Compare Sublarr's catalog providers with a checkout of the Bazarr+ catalog.

The bundles in backend/providers/hub/bundles are reviewed copies, never
fetched at runtime. This script is how they are updated: it reports what
changed upstream and copies a bundle across only when asked to by name, so
every update passes through a person reading the diff first.

    git clone https://github.com/LavX/bazarr-provider-catalog /tmp/catalog
    python3 scripts/sync_provider_catalog.py /tmp/catalog            # report
    python3 scripts/sync_provider_catalog.py /tmp/catalog --diff subhd
    python3 scripts/sync_provider_catalog.py /tmp/catalog --apply subhd titulky

Adopting a provider that is not vendored yet works the same way with
--apply; check its dependencies and the exclusion notes in
backend/providers/hub/__init__.py first.
"""

from __future__ import annotations

import argparse
import difflib
import json
import shutil
import subprocess
import sys
from pathlib import Path

BUNDLES = Path(__file__).resolve().parent.parent / "backend" / "providers" / "hub" / "bundles"
SOURCES = BUNDLES / "SOURCES.json"


def _bundle_files(bundle: Path) -> dict[str, bytes]:
    manifest = json.loads((bundle / "provider.json").read_text(encoding="utf-8"))
    names = ["provider.json", *manifest.get("files", {})]
    return {name: (bundle / name).read_bytes() for name in names if (bundle / name).is_file()}


def _catalog_commit(catalog: Path) -> str:
    out = subprocess.run(
        ["git", "-C", str(catalog), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


def report(catalog: Path) -> int:
    upstream = {
        p.name for p in (catalog / "providers").iterdir() if (p / "provider.json").is_file()
    }
    vendored = {p.name for p in BUNDLES.iterdir() if (p / "provider.json").is_file()}
    changed = sorted(
        name
        for name in vendored & upstream
        if _bundle_files(BUNDLES / name) != _bundle_files(catalog / "providers" / name)
    )
    print(f"catalog at {_catalog_commit(catalog)[:12]}")
    print(f"changed upstream ({len(changed)}): {', '.join(changed) or '-'}")
    print(f"removed upstream: {', '.join(sorted(vendored - upstream)) or '-'}")
    print(
        f"not vendored ({len(upstream - vendored)}): {', '.join(sorted(upstream - vendored)) or '-'}"
    )
    return 0


def diff(catalog: Path, name: str) -> int:
    ours = _bundle_files(BUNDLES / name) if (BUNDLES / name).is_dir() else {}
    theirs = _bundle_files(catalog / "providers" / name)
    for file in sorted(set(ours) | set(theirs)):
        a = ours.get(file, b"").decode("utf-8", "replace").splitlines(keepends=True)
        b = theirs.get(file, b"").decode("utf-8", "replace").splitlines(keepends=True)
        sys.stdout.writelines(
            difflib.unified_diff(a, b, f"sublarr/{name}/{file}", f"catalog/{name}/{file}")
        )
    return 0


def apply(catalog: Path, names: list[str]) -> int:
    commit = _catalog_commit(catalog)
    sources = json.loads(SOURCES.read_text(encoding="utf-8"))
    for name in names:
        source = catalog / "providers" / name
        if not (source / "provider.json").is_file():
            print(f"{name}: not in the catalog", file=sys.stderr)
            return 1
        target = BUNDLES / name
        if target.exists():
            shutil.rmtree(target)
        target.mkdir()
        for file, data in _bundle_files(source).items():
            (target / file).write_bytes(data)
        sources["bundles"][name] = commit
        print(f"{name}: copied from {commit[:12]}")
    sources["bundles"] = dict(sorted(sources["bundles"].items()))
    SOURCES.write_text(json.dumps(sources, indent=2) + "\n", encoding="utf-8")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("catalog", type=Path, help="path to a bazarr-provider-catalog checkout")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--diff", metavar="ID", help="show the upstream diff of one bundle")
    group.add_argument(
        "--apply", nargs="+", metavar="ID", help="copy these bundles from the catalog"
    )
    args = parser.parse_args()
    if args.diff:
        return diff(args.catalog, args.diff)
    if args.apply:
        return apply(args.catalog, args.apply)
    return report(args.catalog)


if __name__ == "__main__":
    sys.exit(main())
