from __future__ import annotations
import argparse, re, sys
from datetime import datetime
from pathlib import Path
from progress import complete

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

NAME_RE = re.compile(r"^(\d{4})[-.](\d{2})[-.](\d{2})_(\d{2})[-.](\d{2})$")

def subject_meta(folder: Path) -> dict[str, object]:
    path = folder / "_context" / "_meta.yaml"
    if not path.is_file(): raise FileNotFoundError(f"Не найден файл метаданных предмета: {path}")
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" not in line: continue
        key, value = line.split(":", 1); value = value.strip().strip('"')
        result[key.strip()] = int(value) if value.isdigit() else value
    required = {"id", "name", "semester", "subject_number"}
    if not required <= result.keys(): raise ValueError(f"В {path} отсутствуют поля: {', '.join(sorted(required - result.keys()))}")
    return result

def main() -> int:
    parser = argparse.ArgumentParser(description="Создать _meta.yaml в корне лекции.")
    parser.add_argument("lecture_folder", type=Path); parser.add_argument("--force", action="store_true")
    args = parser.parse_args(); folder = args.lecture_folder.expanduser().resolve()
    match = NAME_RE.fullmatch(folder.name)
    if not folder.is_dir(): parser.error(f"Папка лекции не найдена: {folder}")
    if not match: parser.error("Имя папки должно быть YYYY-MM-DD_HH-mm")
    output = folder / "_meta.yaml"
    if output.exists() and not args.force: parser.error(f"Файл уже существует: {output}; используйте --force")
    meta = subject_meta(folder.parent); date = datetime.strptime("-".join(match.groups()[:3]), "%Y-%m-%d").date().isoformat(); time = f"{match.group(4)}-{match.group(5)}"
    existing = []
    for path in folder.parent.iterdir():
        candidate = path / "_meta.yaml"
        if path.is_dir() and path != folder and NAME_RE.fullmatch(path.name) and candidate.is_file():
            for line in candidate.read_text(encoding="utf-8").splitlines():
                if line.startswith("lecture_number:") and line.split(":", 1)[1].strip().isdigit(): existing.append(int(line.split(":", 1)[1]))
    output.write_text("\n".join([f'id: "{meta["id"]}_{date}_{time}"', f'subject_id: "{meta["id"]}"', f'subject_name: "{meta["name"]}"', f'subject_number: {meta["subject_number"]}', f'semester: {meta["semester"]}', f'lecture_number: {max(existing, default=0)+1}', f'date: "{date}"', f'time: "{time}"', ""]), encoding="utf-8")
    complete(folder, 1)
    print(f"Created: {output}"); return 0
if __name__ == "__main__": raise SystemExit(main())
