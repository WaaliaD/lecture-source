from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_DIR = Path(r"C:\Users\Timur\Desktop\РАНХиГС")
DEFAULT_OUTPUT_DIR_NAME = "transcripts"
CLI = ROOT / "03_app" / "whisper" / "build" / "bin" / "Release" / "whisper-cli.exe"
MODEL = ROOT / "03_app" / "whisper" / "models" / "ggml-large-v3-turbo.bin"
VAD = ROOT / "03_app" / "whisper" / "models" / "ggml-silero-v6.2.0.bin"
MEDIA_EXTENSIONS = {
    ".aac",
    ".avi",
    ".flac",
    ".m4a",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".ogg",
    ".opus",
    ".wav",
    ".webm",
    ".wma",
}


def find_ffmpeg() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    package_root = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
    if package_root.is_dir():
        candidate = next((path for path in package_root.glob("**/ffmpeg.exe") if path.is_file()), None)
        if candidate:
            return str(candidate)
    return None


def media_files(input_dir: Path, output_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in input_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in MEDIA_EXTENSIONS:
            continue
        try:
            path.relative_to(output_dir)
        except ValueError:
            files.append(path)
    return sorted(files, key=lambda path: str(path).casefold())


def runtime_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["GGML_VK_VISIBLE_DEVICES"] = os.environ.get("LECTORY_WHISPER_DEVICE", "0")
    for name in (
        "GGML_VK_DISABLE_COOPMAT",
        "GGML_VK_DISABLE_COOPMAT2",
        "GGML_VK_DISABLE_COOPMAT2_DECODE_VECTOR",
        "GGML_VK_DISABLE_INTEGER_DOT_PRODUCT",
        "GGML_VK_DISABLE_BFLOAT16",
        "GGML_VK_DISABLE_DOT2",
        "GGML_VK_DISABLE_F16",
        "GGML_VK_DISABLE_ASYNC",
        "GGML_VK_DISABLE_GRAPH_OPTIMIZE",
        "GGML_VK_DISABLE_FUSION",
        "GGML_VK_DISABLE_MMVQ",
        "GGML_VK_SERIALIZE_SUBMISSIONS",
        "GGML_VK_DISABLE_HOST_VISIBLE_VIDMEM",
    ):
        environment[name] = "1"
    return environment


def transcribe(source: Path, destination: Path, ffmpeg: str, environment: dict[str, str]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lectory_whisper_") as temporary:
        work_dir = Path(temporary)
        wav_path = work_dir / "input.wav"
        output_base = work_dir / "transcript"
        conversion = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(wav_path),
        ]
        subprocess.run(conversion, check=True, env=environment)
        whisper = [
            str(CLI),
            "-m",
            str(MODEL),
            "-f",
            str(wav_path),
            "-oj",
            "-of",
            str(output_base),
            "-l",
            "ru",
            "--no-fallback",
            "--temperature",
            "0",
            "--temperature-inc",
            "0",
            "--suppress-nst",
            "--no-speech-thold",
            "0.4",
            "--vad",
            "--vad-model",
            str(VAD),
            "--no-flash-attn",
        ]
        subprocess.run(whisper, check=True, env=environment)
        result = output_base.with_suffix(".json")
        if not result.is_file():
            raise RuntimeError("whisper-cli не создал JSON-файл")
        temporary_destination = destination.with_name(f"{destination.name}.part")
        shutil.copy2(result, temporary_destination)
        temporary_destination.replace(destination)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Последовательно транскрибирует все аудио- и видеофайлы папки."
    )
    parser.add_argument("input_dir", nargs="?", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--force", action="store_true", help="перезаписать готовые JSON")
    parser.add_argument("--dry-run", action="store_true", help="только показать очередь")
    args = parser.parse_args()

    input_dir = args.input_dir.expanduser().resolve()
    output_dir = (args.output_dir or input_dir / DEFAULT_OUTPUT_DIR_NAME).expanduser().resolve()
    if not input_dir.is_dir():
        parser.error(f"Папка не найдена: {input_dir}")
    if output_dir == input_dir:
        parser.error("--output-dir не может совпадать с исходной папкой")
    files = media_files(input_dir, output_dir)
    if not files:
        print("Аудио- и видеофайлы не найдены")
        return 0
    queue: list[tuple[Path, Path]] = []
    for source in files:
        relative = source.relative_to(input_dir)
        destination = output_dir / relative.parent / f"{relative.name}.json"
        if args.force or not destination.is_file():
            queue.append((source, destination))
    print(f"Найдено файлов: {len(files)}; к запуску: {len(queue)}; готовые пропущены: {len(files) - len(queue)}")
    for index, (source, destination) in enumerate(queue, 1):
        print(f"[{index}/{len(queue)}] {source.relative_to(input_dir)} -> {destination.relative_to(input_dir)}")
    if args.dry_run or not queue:
        return 0

    for path, label in ((CLI, "Whisper CLI"), (MODEL, "модель Whisper"), (VAD, "модель VAD")):
        if not path.is_file():
            parser.error(f"Не найден {label}: {path}")
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        parser.error("Не найден ffmpeg: он нужен для временного преобразования аудио в WAV")

    environment = runtime_environment()
    failures: list[Path] = []
    for index, (source, destination) in enumerate(queue, 1):
        print(f"[{index}/{len(queue)}] Транскрибация: {source.relative_to(input_dir)}", flush=True)
        try:
            transcribe(source, destination, ffmpeg, environment)
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            failures.append(source)
            print(f"Ошибка: {source.name}: {error}", file=sys.stderr, flush=True)
    print(f"Готово: {len(queue) - len(failures)} из {len(queue)}; результаты: {output_dir}")
    if failures:
        print("Не обработаны:", file=sys.stderr)
        for source in failures:
            print(f"- {source}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
