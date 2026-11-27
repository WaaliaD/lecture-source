from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from progress import complete, start

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


VIDEO = {".mp4", ".mkv", ".mov", ".webm", ".avi"}
IMAGE = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_RE = re.compile(r"(?P<date>\d{4}-\d{2}-\d{2})[ _](?P<time>\d{2}[-:]\d{2}[-:]\d{2})")
SHOT_RE = re.compile(r"Screenshot[ _]+(?P<date>\d{4}-\d{2}-\d{2})[ _](?P<time>\d{2}[-:]\d{2}[-:]\d{2})", re.I)
TESSERACT = (Path("C:/Program Files/Tesseract-OCR/tesseract.exe"), Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"))


def timestamp(name: str, screenshot: bool):
    match = (SHOT_RE if screenshot else VIDEO_RE).search(name)
    return datetime.strptime(
        f"{match['date']} {match['time'].replace('-', ':')}",
        "%Y-%m-%d %H:%M:%S",
    ) if match else None


def tesseract():
    return shutil.which("tesseract") or next((str(path) for path in TESSERACT if path.is_file()), None)


def ocr(path: Path) -> str:
    executable = tesseract()
    if not executable:
        print("OCR пропущен: Tesseract не найден", file=sys.stderr)
        return ""
    temporary = None
    try:
        # Windows-сборка Tesseract не всегда принимает Unicode-пути.
        # Копируем изображение во временный ASCII-путь и удаляем копию после OCR.
        with tempfile.NamedTemporaryFile(prefix="lectory_", suffix=path.suffix, delete=False) as handle:
            temporary = Path(handle.name)
        shutil.copyfile(path, temporary)
        result = subprocess.run(
            [executable, str(temporary), "stdout", "-l", "rus+eng", "--psm", "6"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        print(f"OCR не выполнен для {path.name}: {error}", file=sys.stderr)
        return ""
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def duration(path: Path):
    executable = shutil.which("ffprobe")
    if not executable:
        return None
    try:
        return float(subprocess.run(
            [executable, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def target(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 10000):
        candidate = path.with_name(f"{path.stem}_{index:02d}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Не удалось подобрать имя для {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("lecture_folder", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    folder = args.lecture_folder.expanduser().resolve()
    if not args.dry_run:
        start(folder, 2)
    source = folder / "source"
    fragments = source / "fragments"
    videos = [{"path": path, "start": timestamp(path.name, False), "duration": duration(path)} for path in folder.iterdir() if path.is_file() and path.suffix.lower() in VIDEO]
    root_shots = [path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in IMAGE]
    stored_shots = [path for path in fragments.iterdir() if path.is_file() and path.suffix.lower() in IMAGE] if fragments.is_dir() else []
    shot_paths = list(dict.fromkeys(root_shots + stored_shots))
    shots = [{"path": path, "in_root": path.parent == folder, "time": timestamp(path.name, True), "content": "" if args.dry_run else ocr(path)} for path in shot_paths]
    videos.sort(key=lambda item: item["start"] or datetime.max)
    shots.sort(key=lambda item: item["time"] or datetime.max)
    items = []
    warnings = []
    for shot in shots:
        candidates = [video for video in videos if video["start"] and shot["time"] and video["start"] <= shot["time"]]
        video = candidates[-1] if candidates else None
        if video and video["duration"] is not None and (shot["time"] - video["start"]).total_seconds() > video["duration"] + 2:
            video = None
        if not video:
            warnings.append(f"Не найдено видео для {shot['path'].name}")
        items.append({
            "screenshot_path": f"source/fragments/{shot['path'].name}",
            "screenshot_datetime": shot["time"].isoformat(sep=" ") if shot["time"] else None,
            "video_path": f"source/{video['path'].name}" if video else None,
            "video_start_datetime": video["start"].isoformat(sep=" ") if video and video["start"] else None,
            "timestamp_seconds": round((shot["time"] - video["start"]).total_seconds(), 3) if video and shot["time"] and video["start"] else None,
            "content": shot["content"],
        })
    print(f"Videos: {len(videos)}; screenshots: {len(shots)}; matched: {sum(item['timestamp_seconds'] is not None for item in items)}")
    if args.dry_run:
        return 0
    source.mkdir(exist_ok=True)
    if shots:
        fragments.mkdir(parents=True, exist_ok=True)
    elif fragments.is_dir() and not any(fragments.iterdir()):
        fragments.rmdir()
    for video in videos:
        shutil.move(str(video["path"]), str(target(source / video["path"].name)))
    if shots:
        for shot in shots:
            if not shot["in_root"]:
                continue
            shutil.move(str(shot["path"]), str(target(fragments / shot["path"].name)))
    output = folder / "json/video-screenshot-timings.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps({"videos": [{"path": f"source/{video['path'].name}", "start_datetime": video["start"].isoformat(sep=" ") if video["start"] else None, "duration_seconds": video["duration"]} for video in videos], "screenshots": items, "warnings": warnings}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    complete(folder, 2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
