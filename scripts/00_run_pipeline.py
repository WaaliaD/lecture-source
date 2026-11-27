from __future__ import annotations
import argparse,os,shutil,subprocess,sys
from pathlib import Path
SCRIPTS=["01_create_lecture_meta.py","02_bind_video_screenshots.py","03_extract_audio.py","04_transcribe_turbo.py","05_extract_pdf.py","06_merge_lecture_data.py"]
def tool(name):
 found=shutil.which(name)
 if found:return found
 filename=f"{name}.exe"
 roots=[Path.home()/"AppData/Local/Microsoft/WinGet/Packages",Path("C:/ProgramData/chocolatey/bin")]
 direct=[
  roots[0]/"Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.1-full_build/bin"/filename,
  roots[0]/"Gyan.FFmpeg.Shared_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.2-full_build-shared/bin"/filename,
 ]
 for candidate in direct:
  if candidate.is_file():return str(candidate)
 for root in roots:
  if root.is_dir():
   matches=root.glob(f"**/{filename}")
   candidate=next((x for x in matches if x.is_file()),None)
   if candidate:return str(candidate)
 return None
def tess():return shutil.which("tesseract") or next((str(p) for p in (Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe")) if p.is_file()),None)
def ppm():
 p=shutil.which("pdftoppm")
 if p:return p
 root=Path.home()/".cache/codex-runtimes";return next((str(x) for x in root.glob("**/pdftoppm.exe") if x.is_file()),None) if root.is_dir() else None
def check(folder):
 errors=[];media={".mp4",".mkv",".mov",".webm",".avi",".mp3",".m4a",".ogg",".flac",".aac",".wav"};source=folder/"source";has_media=any(x.is_file() and x.suffix.lower() in media for x in folder.iterdir()) or (source.is_dir() and any(x.is_file() and x.suffix.lower() in media for x in source.iterdir()))
 has_presentation=any(x.is_file() and x.suffix.lower()==".pdf" for x in folder.iterdir()) or (source.is_dir() and any(x.is_file() and x.suffix.lower()==".pdf" for x in source.iterdir()))
 if not has_media and not has_presentation:errors.append("Не найдено аудио, видео или PDF-презентация в корне лекции либо source/")
 video={".mp4",".mkv",".mov",".webm",".avi"}
 all_media=[x for base in (folder,source) if base.is_dir() for x in base.iterdir() if x.is_file() and x.suffix.lower() in media]
 has_wav=any(x.suffix.lower()==".wav" for x in all_media)
 if any(x.suffix.lower() != ".wav" for x in all_media) and not has_wav and not tool("ffmpeg"):
  errors.append("Не найдено приложение в PATH: ffmpeg (нужно для конвертации аудио/видео)")
 root_videos=[x for x in folder.iterdir() if x.is_file() and x.suffix.lower() in video]
 root_images=[x for x in folder.iterdir() if x.is_file() and x.suffix.lower() in {".png",".jpg",".jpeg",".webp"}]
 if root_videos and root_images and not tool("ffprobe"):
  errors.append("Не найдено приложение в PATH: ffprobe (нужно для привязки кадров к видео)")
 root=Path(__file__).resolve().parents[2]
 if has_media:
  for path,label in ((root/"03_app/whisper/build/bin/Release/whisper-cli.exe","Whisper CLI"),(root/"03_app/whisper/models/ggml-large-v3-turbo.bin","Whisper model"),(root/"03_app/whisper/models/ggml-silero-v6.2.0.bin","VAD model")):
   if not path.is_file():errors.append(f"Не найден {label}: {path}")
 if has_presentation and not ppm():errors.append("Найден PDF, но не найден pdftoppm")
 if has_presentation and not tess():errors.append("Найден PDF, но не найден tesseract")
 return errors
def resolve_folder(value):
 folder=value.expanduser()
 if folder.is_dir():return folder.resolve()
 if "?" in str(folder) or "*" in str(folder):
  matches=[item for item in folder.parent.glob(folder.name) if item.is_dir()]
  if len(matches)==1:return matches[0].resolve()
 return folder.resolve()
def main():
 p=argparse.ArgumentParser();p.add_argument("lecture_folder",type=Path);p.add_argument("--dry-run",action="store_true");p.add_argument("--force-meta",action="store_true");a=p.parse_args();folder=resolve_folder(a.lecture_folder)
 if not folder.is_dir():p.error(f"Папка не найдена: {folder}")
 errors=check(folder)
 if errors:
  print("Проверка окружения не пройдена:",file=sys.stderr);[print(f"- {x}",file=sys.stderr) for x in errors];return 2
 for name in SCRIPTS:
  if name=="04_transcribe_turbo.py" and not any(x.is_file() and x.suffix.lower() in {".mp4",".mkv",".mov",".webm",".avi",".mp3",".m4a",".ogg",".flac",".aac",".wav"} for x in folder.iterdir()) and not ((folder/"source").is_dir() and any(x.is_file() and x.suffix.lower() in {".mp4",".mkv",".mov",".webm",".avi",".mp3",".m4a",".ogg",".flac",".aac",".wav"} for x in (folder/"source").iterdir())):
   print("\n=== 04_transcribe_turbo.py ===\nПропуск: аудио или видео отсутствует; используется только презентация",flush=True)
   continue
  cmd=[sys.executable,str(Path(__file__).with_name(name)),str(folder)]
  if a.dry_run and name in {"02_bind_video_screenshots.py","03_extract_audio.py","04_transcribe_turbo.py","05_extract_pdf.py","06_merge_lecture_data.py"}:cmd.append("--dry-run")
  if name=="01_create_lecture_meta.py" and a.force_meta:cmd.append("--force")
  print(f"\n=== {name} ===",flush=True)
  try:
   env=os.environ.copy()
   for executable in (tool("ffmpeg"),tool("ffprobe")):
    if executable:
     env["Path"]=str(Path(executable).parent)+os.pathsep+env.get("Path","")
   # Рабочая Vulkan-сборка использует первый адаптер, это RX 9070 XT.
   # Задаём его здесь, чтобы запуск через 00 не зависел от переменных
   # окружения, оставшихся от ручных тестов.
   if name=="04_transcribe_turbo.py":env["LECTORY_WHISPER_DEVICE"]="0"
   subprocess.run(cmd,check=True,env=env)
  except (OSError,subprocess.SubprocessError) as e:print(f"Pipeline остановлен без traceback: {e}",file=sys.stderr);return 1
 print("\nPipeline completed");return 0
if __name__ == "__main__":raise SystemExit(main())
