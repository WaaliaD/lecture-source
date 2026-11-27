from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from progress import complete, start

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


MEDIA = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".mp3", ".m4a", ".ogg", ".flac", ".aac", ".wav"}


def lecture_name(folder: Path) -> str:
    values = {}
    for line in (folder / "_meta.yaml").read_text(encoding="utf-8").splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip().strip('"')
    subject = values.get("subject_id") or values.get("id", "lecture").split("_", 1)[0]
    date = values.get("date", "unknown-date")
    time = values.get("time", "unknown-time").replace(":", "-")
    return f"{subject}_{date}_{time}"


def output_name(base: str, index: int) -> str:
    return f"{base}.wav" if index == 1 else f"{base}_{index:02d}.wav"


def is_normalized(path: Path, base: str) -> bool:
    return path.suffix.lower() == ".wav" and (
        path.stem == base or (path.stem.startswith(base + "_") and path.stem[len(base) + 1:].isdigit())
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("lecture_folder", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    folder = args.lecture_folder.expanduser().resolve()
    if not args.dry_run:
        start(folder, 3)
    source = folder / "source"
    if not args.dry_run:
        source.mkdir(exist_ok=True)
    base = lecture_name(folder)
    existing_wav = sorted(path for path in source.glob("*.wav") if path.is_file())
    root_files = sorted(x for x in folder.iterdir() if x.is_file() and x.suffix.lower() in MEDIA)
    source_files = sorted(x for x in source.iterdir() if x.is_file() and x.suffix.lower() in MEDIA)
    files = root_files + [x for x in source_files if x not in root_files]
    files = [x for x in files if not is_normalized(x, base)]
    if not files:
        print("Новых аудио- или видеофайлов нет; этап пропущен")
        if not args.dry_run:
            complete(folder, 3)
        return 0
    ffmpeg = shutil.which("ffmpeg")
    if not args.dry_run and not ffmpeg:
        if existing_wav:
            print("FFmpeg не найден; использую уже готовые WAV и пропускаю конвертацию видео")
            files = []
        else:
            parser.error("FFmpeg не найден в PATH и готового WAV нет")
    existing = sorted(x for x in source.glob(f"{base}*.wav") if x.is_file())
    next_index = len(existing) + 1
    for media in files:
        output = source / output_name(base, next_index)
        while output.exists():
            next_index += 1
            output = source / output_name(base, next_index)
        print(f"{media.name} -> {output.name}")
        if not args.dry_run:
            subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-nostdin",
                    "-i",
                    str(media),
                    "-map",
                    "0:a:0",
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-c:a",
                    "pcm_s16le",
                    str(output),
                ],
                check=True,
            )
            if media.parent == folder:
                original_target = source / media.name
                if original_target != output and not original_target.exists():
                    shutil.move(str(media), str(original_target))
        next_index += 1
    if not args.dry_run:
        complete(folder, 3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
