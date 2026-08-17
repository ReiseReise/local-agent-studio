from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".css",
    ".env",
    ".example",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
SKIP_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", "dist", "build"}
FORBIDDEN = {
    "macOS absolute user path": re.compile(r"/Users/[^/\s]+/"),
    "Windows absolute user path": re.compile(r"[A-Za-z]:\\Users\\[^%\\\s]+\\"),
    "workspace private path": re.compile(r"Nutstore Files|00_数字分身"),
    "private test contact": re.compile(r"关关|关会雪"),
    "WeChat identifier": re.compile(r"\bwxid_[A-Za-z0-9_-]+\b"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "common live token": re.compile(r"\b(?:sk|ghp|github_pat)_[A-Za-z0-9_-]{16,}\b"),
}


def candidate_files() -> list[Path]:
    git = shutil.which("git")
    if git:
        result = subprocess.run(  # noqa: S603 - executable path is resolved by shutil.which
            [git, "ls-files"], cwd=ROOT, text=True, capture_output=True, check=False
        )
        if result.returncode == 0 and result.stdout.strip():
            return [ROOT / line for line in result.stdout.splitlines() if line]
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file() and not any(part in SKIP_PARTS for part in path.relative_to(ROOT).parts)
    ]


def main() -> int:
    failures: list[str] = []
    for path in candidate_files():
        relative = path.relative_to(ROOT)
        if path.is_symlink():
            failures.append(f"{relative}: symlink is not allowed in the public source tree")
            continue
        if path.stat().st_size > 5 * 1024 * 1024:
            failures.append(f"{relative}: file exceeds the 5 MiB public source limit")
        if relative == Path("scripts/check_public_repo.py"):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {
            ".gitignore",
            ".env.example",
            "LICENSE",
            "NOTICE",
        }:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            failures.append(f"{relative}: expected text file is not UTF-8")
            continue
        for label, pattern in FORBIDDEN.items():
            if pattern.search(content):
                failures.append(f"{relative}: contains {label}")
    if failures:
        print("PUBLIC REPOSITORY CHECK FAILED", file=sys.stderr)
        print(*failures, sep="\n", file=sys.stderr)
        return 1
    print("PUBLIC REPOSITORY CHECK PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
