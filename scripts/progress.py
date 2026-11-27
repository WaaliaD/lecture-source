from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "lectures.md"
STAGES = {
    1: "Создание метаданных",
    2: "Связь видео и скриншотов",
    3: "Создание WAV",
    4: "Транскрипция",
    5: "OCR PDF",
    6: "Сборка итогового JSON",
    7: "Создание Markdown",
}


def read_meta(folder: Path) -> dict[str, str]:
    path = folder / "_meta.yaml"
    if not path.is_file():
        return {}
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" not in line or not line.strip() or line.lstrip().startswith("#"):
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip().strip('"')
    return result


def marker_path(folder: Path) -> str:
    return folder.relative_to(ROOT).as_posix()


def row(folder: Path, meta: dict[str, str], status: str, passed: list[str]) -> str:
    marker = f"<!-- lecture:path={marker_path(folder)};passed={','.join(passed)};status={status} -->"
    subject = f"{meta.get('semester', '')}-{meta.get('subject_number', '')} {meta.get('subject_name', '')}".strip()
    return f"| {folder.name} | `{subject}` | `{status}` | {', '.join(passed) or '—'} | {marker}"


def heading(meta: dict[str, str]) -> str:
    return f"## {meta.get('subject_id', '')} {meta.get('subject_name', '')}".strip()


def update(folder: Path, stage: int, complete: bool = False) -> None:
    meta = read_meta(folder)
    if not meta:
        return
    relative = marker_path(folder)
    text = REGISTRY.read_text(encoding="utf-8") if REGISTRY.is_file() else "# Лекции\n"
    pattern = re.compile(rf"^\|.*<!-- lecture:path={re.escape(relative)};passed=([^;]*);status=(.*?) -->\s*$", re.MULTILINE)
    match = pattern.search(text)
    if match:
        passed = [item for item in match.group(1).split(",") if item]
    else:
        passed = []
    stage_value = f"{stage:02d}"
    if complete and stage_value not in passed:
        passed.append(stage_value)
    status = "Готово" if stage == 7 and complete else f"Этап {stage_value}: {STAGES[stage]}"
    new_row = row(folder, meta, status, passed)
    if match:
        text = text[:match.start()] + new_row + text[match.end():]
    else:
        group = heading(meta)
        group_match = re.search(rf"^## {re.escape(group[3:])}\s*$", text, re.MULTILINE)
        if not group_match:
            if not text.endswith("\n"):
                text += "\n"
            text += f"\n{group}\n\n| Лекция | Предмет | Статус | Пройдено |\n|---|---|---|---|\n{new_row}\n"
        else:
            next_group = re.search(r"^## ", text[group_match.end():], re.MULTILINE)
            insert_at = group_match.end() + (next_group.start() if next_group else len(text[group_match.end():]))
            block = text[group_match.end():insert_at]
            if "| Лекция | Предмет | Статус | Пройдено |" not in block:
                block = "\n\n| Лекция | Предмет | Статус | Пройдено |\n|---|---|---|---|\n" + block.lstrip("\n")
            if not block.endswith("\n"):
                block += "\n"
            text = text[:group_match.end()] + block + new_row + "\n" + text[insert_at:]
    REGISTRY.write_text(text.rstrip() + "\n", encoding="utf-8")


def start(folder: Path, stage: int) -> None:
    update(folder, stage, complete=False)


def complete(folder: Path, stage: int) -> None:
    update(folder, stage, complete=True)
