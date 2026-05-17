"""Rename the inner Python package claw_companion -> frankie.

What this script does:
- Moves src/claw_companion/ to src/frankie/ (git-mv-style: removes old, writes new)
- Rewrites every .py / .toml / .sh / .service / .ps1 / .json / .md text file that
  references claw_companion or claw-companion or "Claw Companion"
- Updates pyproject.toml [project].name + ruff src paths
- Updates systemd unit + deploy.sh + watch.ps1

What it does NOT do:
- Rename the outer repo directory C:\\Users\\sudar\\claw-companion (deferred,
  cosmetic, breaks tool paths). Same for /home/rpclaw/claw-companion on the Pi.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(r"C:\Users\sudar\claw-companion")
OLD_PKG_DIR = ROOT / "src" / "claw_companion"
NEW_PKG_DIR = ROOT / "src" / "frankie"

# Directories to skip when scanning for text edits.
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "data", ".mypy_cache", ".ruff_cache", ".pytest_cache"}

# Files we'll process (by extension).
TEXT_EXTS = {".py", ".toml", ".sh", ".service", ".ps1", ".json", ".md", ".cfg", ".ini", ".yaml", ".yml"}

# Substitutions applied in order to every text file in scope. Order matters
# so the more specific patterns hit before the broader ones.
SUBS: list[tuple[str, str]] = [
    (r"\bclaw_companion\b", "frankie"),
    (r"\bclaw-companion\b", "frankie"),
    (r"Claw Companion", "Frankie"),
    (r"claw companion", "Frankie"),
]


def move_package() -> None:
    if not OLD_PKG_DIR.exists():
        print(f"old package already gone: {OLD_PKG_DIR}")
        return
    if NEW_PKG_DIR.exists():
        print(f"new package already exists: {NEW_PKG_DIR} — removing before move")
        shutil.rmtree(NEW_PKG_DIR)
    shutil.move(str(OLD_PKG_DIR), str(NEW_PKG_DIR))
    print(f"moved {OLD_PKG_DIR} -> {NEW_PKG_DIR}")


def rewrite_text_files() -> int:
    changed = 0
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_EXTS:
            continue
        # Skip THIS script and the scripts/_ rename script itself.
        if path.name == Path(__file__).name:
            continue
        try:
            original = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new = original
        for pattern, replacement in SUBS:
            new = re.sub(pattern, replacement, new)
        if new != original:
            path.write_text(new, encoding="utf-8")
            changed += 1
            print(f"edited: {path.relative_to(ROOT)}")
    return changed


def main() -> int:
    move_package()
    n = rewrite_text_files()
    print(f"\n{n} text files updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
