from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from progress import complete, start

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "03_app/whisper/build/bin/Release/whisper-cli.exe"
MODEL = ROOT / "03_app/whisper/models/ggml-large-v3-turbo.bin"
VAD = ROOT / "03_app/whisper/models/ggml-silero-v6.2.0.bin"
ID = re.compile(r'^id:\s*"(?P<id>[^"]+)"$')


def lecture_id(folder: Path) -> str:
    meta = folder / "_meta.yaml"
    for line in meta.read_text(encoding="utf-8").splitlines():
        match = ID.match(line.strip())
        if match:
            return match.group("id")
    raise ValueError("В _meta.yaml отсутствует id")


def vocabulary_prompt(path: Path) -> str:
    lines: list[str] = []
    size = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or size + len(line) + 2 > 500:
            break
        lines.append(line)
        size += len(line) + 2
    return "; ".join(lines)


def transcribe_file(source: Path, transcript_dir: Path, prompt: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="lectory_whisper_") as temporary:
        temporary_dir = Path(temporary)
        staged_audio = temporary_dir / "input.wav"
        staged_output = temporary_dir / "result"
        shutil.copy2(source, staged_audio)
        command = [
            str(CLI),
            "-m",
            str(MODEL),
            "-f",
            "input.wav",
            "-oj",
            "-of",
            "result",
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
        if prompt:
            command += ["--prompt", prompt]
        print(f"Whisper: {source.name}", flush=True)
        runtime_env = os.environ.copy()
        # Старый стабильный whisper.cpp не знает ключ -dev. Ограничиваем
        # Vulkan-устройства через штатный аналог CUDA_VISIBLE_DEVICES:
        # индекс 0 — RX 9070 XT в конфигурации пользователя.
        runtime_env["GGML_VK_VISIBLE_DEVICES"] = os.environ.get(
            "LECTORY_WHISPER_DEVICE", "0"
        )
        # AMD Vulkan driver может падать на cooperative-matrix shader path.
        # GPU остаётся включённым, отключаются только эти оптимизации.
        for flag in (
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
            runtime_env[flag] = "1"
        completed = subprocess.run(command, cwd=temporary_dir, check=False, env=runtime_env)
        if completed.returncode != 0:
            raise RuntimeError(
                f"whisper-cli завершился с кодом {completed.returncode} для {source.name}"
            )
        result_path = staged_output.with_suffix(".json")
        if not result_path.is_file():
            raise RuntimeError(f"Whisper не создал JSON для {source.name}")
        destination = transcript_dir / f"{source.stem}.json"
        shutil.copy2(result_path, destination)
        return json.loads(result_path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("lecture_folder", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    folder = args.lecture_folder.expanduser().resolve()
    if not args.dry_run:
        start(folder, 4)
    files = sorted((folder / "source").glob("*.wav"))
    if not files:
        print("В source нет WAV-файлов; этап транскрипции пропущен")
        if not args.dry_run:
            complete(folder, 4)
        return 0
    vocabulary = folder.parent / "_context/vocabulary.txt"
    prompt = vocabulary_prompt(vocabulary) if vocabulary.is_file() else ""
    if args.dry_run:
        print(f"WAV: {len(files)}; vocabulary: {'yes' if prompt else 'no'}; model: {MODEL}")
        return 0
    if not CLI.is_file():
        parser.error(f"Не найден Whisper CLI: {CLI}")
    if not MODEL.is_file():
        parser.error(f"Не найдена Whisper model: {MODEL}")
    if not VAD.is_file():
        parser.error(f"Не найдена VAD model: {VAD}")
    transcript_dir = folder / "transcript"
    transcript_dir.mkdir(exist_ok=True)
    items = []
    for index, source in enumerate(files, 1):
        print(f"[{index}/{len(files)}]", flush=True)
        raw = transcribe_file(source, transcript_dir, prompt)
        items.append({"source": source.name, "raw": raw})
    output_dir = folder / "json"
    output_dir.mkdir(exist_ok=True)
    output = {
        "lecture_id": lecture_id(folder),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": str(MODEL),
        "items": items,
    }
    (output_dir / "transcript.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Готово: {output_dir / 'transcript.json'}", flush=True)
    complete(folder, 4)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
