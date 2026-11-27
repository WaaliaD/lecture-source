from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from progress import complete, start


ROOT = Path(__file__).resolve().parents[2]
LECTURES = ROOT / "01_lectures"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Ожидался JSON-объект: {path}")
    return value


def read_meta(folder: Path) -> dict[str, object]:
    path = folder / "_meta.yaml"
    if not path.is_file():
        return {}
    result: dict[str, object] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" not in line or not line.strip() or line.lstrip().startswith("#"):
            continue
        key, value = line.split(":", 1)
        value = value.strip().strip('"')
        result[key.strip()] = int(value) if value.lstrip("-").isdigit() else value
    return result


def render_fallback(data: dict) -> str:
    title = str(data.get("title", "")).strip()
    summary = str(data.get("summary", "")).strip().replace('"', '\\"')
    lines = ["---", f'title: "{title}"', f'summary: "{summary}"', f'date: "{data.get("date", "")}"', f'subject: "{data.get("subject", "")}"', "---", ""]
    lines.extend(f"{index}. {topic.get('title', '')}" for index, topic in enumerate(data.get("topics", [])[:10], 1))
    lines.extend(["", "---", ""])
    for topic in data.get("topics", [])[:10]:
        lines.extend([f"### {topic.get('title', '')}", "", str(topic.get("text", "")), ""])
        for subtopic in topic.get("subtopics", []):
            lines.extend([f"#### {subtopic.get('title', '')}", "", str(subtopic.get("text", "")), ""])
    return "\n".join(lines)


def pairs(folder: Path) -> list[tuple[Path, Path]]:
    json_dir = folder / "json"
    result = []
    for summary in sorted(json_dir.glob("*_summary.json")):
        base = summary.name.removesuffix("_summary.json") + ".json"
        source = json_dir / base
        if source.is_file():
            result.append((source, summary))
    return result


def all_pairs() -> list[tuple[Path, Path, Path]]:
    result = []
    if not LECTURES.is_dir():
        return result
    for subject in sorted(LECTURES.iterdir()):
        if not subject.is_dir() or subject.name.startswith("_"):
            continue
        for lecture in sorted(subject.iterdir()):
            if lecture.is_dir():
                result.extend((lecture, source, summary) for source, summary in pairs(lecture))
    return result


def render(folder: Path, source: Path, summary_path: Path, output: Path | None, dry_run: bool, force: bool) -> None:
    target = output.expanduser().resolve() if output else folder / f"{summary_path.stem.removesuffix('_summary')}.md"
    if target.is_file() and not force:
        print(f"Пропуск: Markdown уже существует: {target}")
        return
    summary = load(summary_path)
    meta = read_meta(folder)
    data = {
        **meta,
        **summary,
        "date": summary.get("date") or (f"{meta.get('date', '')}T{str(meta.get('time', '')).replace('-', ':')}:00" if meta.get("date") else ""),
        "subject": summary.get("subject") or f"{meta.get('semester', '')}.{meta.get('subject_number', '')} {meta.get('subject_name', '')}".strip(),
        "topics": summary.get("topics", [])[:10],
    }
    if dry_run:
        print(f"{folder}: {source.name} + {summary_path.name} -> {target}")
        return
    start(folder, 7)
    template = Path(__file__).resolve().parents[1] / "lecture.md.j2"
    try:
        from jinja2 import Environment, FileSystemLoader
    except ImportError:
        markdown = render_fallback(data)
    else:
        environment = Environment(loader=FileSystemLoader(str(template.parent)), autoescape=False, keep_trailing_newline=True)
        markdown = environment.get_template(template.name).render(**data)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(markdown.rstrip() + "\n", encoding="utf-8")
    complete(folder, 7)
    print(f"Created Markdown: {target}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Создать Markdown из пар lecture JSON + summary JSON.")
    parser.add_argument("lecture_folder", type=Path, nargs="?")
    parser.add_argument("--all", action="store_true", help="обработать все лекции в 01_lectures")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="пересоздать уже существующий Markdown")
    args = parser.parse_args()
    if args.output and (args.all or args.lecture_folder is None):
        parser.error("--output можно использовать только с конкретной папкой лекции")
    if args.lecture_folder is not None and not args.all:
        folder = args.lecture_folder.expanduser().resolve()
        found = [(folder, source, summary) for source, summary in pairs(folder)]
    else:
        found = all_pairs()
    if not found:
        print("Пар lecture JSON + summary JSON не найдено")
        return 0
    failures = []
    for folder, source, summary in found:
        try:
            render(folder, source, summary, args.output, args.dry_run, args.force)
        except Exception as error:
            failures.append((folder, error))
            print(f"Ошибка в {folder}: {error}", file=sys.stderr)
    print(f"Обработано пар: {len(found) - len(failures)} из {len(found)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
