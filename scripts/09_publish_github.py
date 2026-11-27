from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PUBLISH_PATHS = ["02_vault", ".github/workflows/pages.yml"]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run(*command: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=ROOT, check=check, text=True)


def current_branch() -> str:
    return subprocess.run(
        ("git", "branch", "--show-current"),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Закоммитить и опубликовать vault в GitHub.")
    parser.add_argument("--message")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--branch")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--no-push", dest="push", action="store_false")
    parser.add_argument("--skip-export", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.set_defaults(push=True)
    args = parser.parse_args()
    if not (ROOT / ".git").is_dir():
        parser.error(f"Git-репозиторий не найден: {ROOT}")
    branch = args.branch or current_branch()
    if not branch:
        parser.error("Не удалось определить текущую ветку")
    if args.push and not args.dry_run and not run("git", "remote", "get-url", args.remote, check=False).returncode == 0:
        parser.error(f"Git remote не найден: {args.remote}")
    if not args.skip_export:
        export_command = [sys.executable, str(ROOT / "03_app/scripts/08_publish_vault.py")]
        if args.dry_run:
            export_command.append("--dry-run")
        run(*export_command)
    if args.dry_run:
        run("git", "status", "--short", "--", *PUBLISH_PATHS)
        print(f"Ветка: {branch}; remote: {args.remote}; push: {'yes' if args.push else 'no'}")
        return 0
    run("git", "add", "--", *PUBLISH_PATHS)
    staged = run("git", "diff", "--cached", "--quiet", check=False)
    if staged.returncode == 0:
        print("Изменений для публикации нет")
        return 0
    message = args.message or f"Update lecture vault: {datetime.now().astimezone():%Y-%m-%d %H:%M}"
    run("git", "commit", "-m", message)
    if args.push:
        run("git", "push", args.remote, branch)
        print(f"Опубликовано: {args.remote}/{branch}")
    else:
        print("Коммит создан локально; для отправки используйте --push")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
