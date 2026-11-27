from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from progress import complete, start

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


TESSERACT = (Path("C:/Program Files/Tesseract-OCR/tesseract.exe"), Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"))


def tesseract():
    return shutil.which("tesseract") or next((str(path) for path in TESSERACT if path.is_file()), None)


def pdftoppm():
    executable = shutil.which("pdftoppm")
    if executable:
        return executable
    root = Path.home() / ".cache/codex-runtimes"
    return next((str(path) for path in root.glob("**/pdftoppm.exe") if path.is_file()), None) if root.is_dir() else None


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


def ocr(pdf: Path, languages: str):
    renderer = tesseract()
    converter = pdftoppm()
    if not renderer or not converter:
        raise FileNotFoundError("Для PDF нужны pdftoppm и tesseract")
    with tempfile.TemporaryDirectory(prefix="lectory-ocr-") as temporary:
        prefix = str(Path(temporary) / "page")
        subprocess.run([converter, "-r", "180", "-png", str(pdf), prefix], check=True, capture_output=True)
        pages = []
        for image in sorted(Path(temporary).glob("page-*.png")):
            output = image.with_suffix("")
            subprocess.run([renderer, str(image), str(output), "-l", languages, "--psm", "6"], check=True, capture_output=True)
            pages.append(output.with_suffix(".txt").read_text(encoding="utf-8", errors="replace").strip())
        return pages


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
    parser.add_argument("--languages", default="rus+eng")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    folder = args.lecture_folder.expanduser().resolve()
    if not args.dry_run:
        start(folder, 5)
    files = sorted(set(folder.glob("*.pdf")) | set((folder / "source").glob("*.pdf")))
    if not files:
        if args.dry_run:
            print("PDF: not found; step skipped")
            return 0
        output = folder / "json/pdf.json"
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps({"created_at": datetime.now(timezone.utc).isoformat(), "backend": {"text": None, "ocr": None}, "items": []}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        complete(folder, 5)
        return 0
    if args.dry_run:
        print(f"PDF: {len(files)}; OCR: {'available' if tesseract() and pdftoppm() else 'not available'}")
        return 0
    items = []
    base = lecture_name(folder)
    for index, pdf in enumerate(files, 1):
        pages = ocr(pdf, args.languages)
        final = pdf
        desired = folder / "source" / (f"{base}.pdf" if index == 1 else f"{base}_{index:02d}.pdf")
        if pdf != desired:
            desired.parent.mkdir(exist_ok=True)
            final = target(desired)
            shutil.move(str(pdf), str(final))
        items.append({"path": final.relative_to(folder).as_posix(), "title": final.stem, "pages": [{"number": page, "text": text, "ocr_text": text} for page, text in enumerate(pages, 1)]})
    output = folder / "json/pdf.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps({"created_at": datetime.now(timezone.utc).isoformat(), "backend": {"text": None, "ocr": "pdftoppm+tesseract"}, "items": items}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Created: {output}")
    complete(folder, 5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
