from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LECTURES = ROOT / "01_lectures"
VAULT = ROOT / "02_vault"
IMAGE_LINK = re.compile(r"!\[([^]]*)\]\(([^)]+)\)")
WIKILINK = re.compile(r"!\[\[([^]]+)\]\]")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


@dataclass(frozen=True)
class Lecture:
    source: Path
    subject_dir: Path
    lecture_dir: Path
    title: str
    subject: str
    date: str

    @property
    def target(self) -> Path:
        return VAULT / self.subject_dir.name / self.source.name

    @property
    def marker_path(self) -> str:
        return self.source.relative_to(ROOT).as_posix()

    @property
    def asset_dir(self) -> Path:
        return VAULT / self.subject_dir.name / "assets" / self.source.stem


def frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    result = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line and not line.startswith(" "):
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip().strip('"')
    return result


def display_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return value


def find_lectures() -> list[Lecture]:
    result = []
    if not LECTURES.is_dir():
        return result
    for subject_dir in sorted(LECTURES.iterdir()):
        if not subject_dir.is_dir() or subject_dir.name.startswith("_"):
            continue
        for lecture_dir in sorted(subject_dir.iterdir()):
            if not lecture_dir.is_dir() or lecture_dir.name.startswith("_"):
                continue
            for source in sorted(lecture_dir.glob("*.md")):
                data = frontmatter(source)
                if {"title", "summary", "date", "subject"} <= data.keys():
                    result.append(Lecture(source, subject_dir, lecture_dir, data["title"], data["subject"], data["date"]))
    return result


def copy_assets(lecture: Lecture, content: str) -> str:
    replacements = {}
    links = [match.group(2) for match in IMAGE_LINK.finditer(content)]
    links += [match.group(1) for match in WIKILINK.finditer(content)]
    for link in links:
        clean = link.split("#", 1)[0].split("?", 1)[0]
        if not clean or clean.startswith(("http://", "https://", "data:")):
            continue
        source = (lecture.source.parent / clean).resolve()
        if not source.is_file():
            source = (lecture.lecture_dir / clean).resolve()
        if not source.is_file() or source.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}:
            continue
        lecture.asset_dir.mkdir(parents=True, exist_ok=True)
        destination = lecture.asset_dir / source.name
        shutil.copy2(source, destination)
        replacements[link] = Path("..", "assets", lecture.source.stem, source.name).as_posix()
    for old, new in replacements.items():
        content = content.replace(f"![[{old}]]", f"![{Path(old).stem}]({new})")
        content = content.replace(f"]({old})", f"]({new})")
    return content


def add_layout(content: str) -> str:
    if not content.startswith("---"):
        return content
    end = content.find("\n---", 3)
    if end < 0 or re.search(r"^layout:", content[:end], re.MULTILINE):
        return content
    return content[:end] + "\nlayout: default" + content[end:]


def copy_lectures(lectures: list[Lecture]) -> None:
    for lecture in lectures:
        lecture.target.parent.mkdir(parents=True, exist_ok=True)
        content = lecture.source.read_text(encoding="utf-8")
        lecture.target.write_text(add_layout(copy_assets(lecture, content)), encoding="utf-8")
        print(f"Копия: {lecture.source} -> {lecture.target}")


def previous_order(index: Path) -> list[str]:
    if not index.is_file():
        return []
    return re.findall(r"<!-- lecture:path=([^ ]+) -->", index.read_text(encoding="utf-8"))


def ordered(group: list[Lecture], old_order: list[str]) -> list[Lecture]:
    by_path = {lecture.marker_path: lecture for lecture in group}
    result = [by_path[path] for path in old_order if path in by_path]
    result.extend(lecture for lecture in group if lecture.marker_path not in old_order)
    return result


def write_site_files(lectures: list[Lecture]) -> None:
    VAULT.mkdir(parents=True, exist_ok=True)
    config = VAULT / "_config.yml"
    if not config.exists():
        config.write_text("title: Лекторий\npermalink: pretty\n", encoding="utf-8")
    layouts = VAULT / "_layouts"
    layouts.mkdir(exist_ok=True)
    layout = layouts / "default.html"
    if not layout.exists():
        layout.write_text(
            "<!doctype html>\n<html lang=\"ru\">\n<head>\n<meta charset=\"utf-8\">\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n<title>{{ page.title }} — {{ site.title }}</title>\n<style>body{max-width:900px;margin:40px auto;padding:0 20px;font:16px/1.6 system-ui,sans-serif;color:#222}a{color:#2457a6}pre{overflow:auto;padding:1em;background:#f4f4f4}code{background:#f4f4f4;padding:.1em .25em}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:.4em .7em}.date{color:#666;font-size:.9em}</style>\n</head>\n<body>{% if page.date %}<p class=\"date\">{{ page.date | date: \"%d.%m.%Y %H:%M\" }}</p>{% endif %}{{ content }}</body>\n</html>\n",
            encoding="utf-8",
        )
    index = VAULT / "index.md"
    old_order = previous_order(index)
    groups = {}
    for lecture in lectures:
        groups.setdefault(lecture.subject_dir.name, []).append(lecture)
    lines = ["---", "layout: default", "title: Лекции", "---", "", "# Лекции", ""]
    for subject_name in sorted(groups):
        group = sorted(groups[subject_name], key=lambda lecture: lecture.lecture_dir.name)
        group = ordered(group, old_order)
        title = group[0].subject if group else subject_name.replace("_", " ")
        lines.extend([f"## {title}", ""])
        for lecture in group:
            relative = f"{lecture.subject_dir.name}/{lecture.target.stem}/"
            lines.append(f"- [{lecture.title}]({relative}) — {display_date(lecture.date)} <!-- lecture:path={lecture.marker_path} -->")
        lines.append("")
    index.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"Индекс: {index}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Собрать GitHub Pages vault из всех лекций.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    lectures = find_lectures()
    print(f"Найдено лекций: {len(lectures)}")
    if args.dry_run:
        for lecture in lectures:
            print(f"{lecture.source} -> {lecture.target}")
        return 0
    copy_lectures(lectures)
    write_site_files(lectures)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
