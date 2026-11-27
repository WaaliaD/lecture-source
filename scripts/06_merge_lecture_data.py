from __future__ import annotations
import argparse,json,shutil,subprocess,sys
import tempfile
from datetime import datetime,timezone
from pathlib import Path
from progress import complete, start

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TESS=(Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"))
def load(path,required=True):
 if not path.is_file():
  if required:raise FileNotFoundError(f"Не найден файл: {path}")
  return {}
 value=json.loads(path.read_text(encoding="utf-8"))
 if not isinstance(value,dict):raise ValueError(f"Ожидался JSON-объект: {path}")
 return value
def meta(folder):
 path=folder/"_meta.yaml"
 if not path.is_file():raise FileNotFoundError(f"Не найден файл: {path}")
 result={}
 for line in path.read_text(encoding="utf-8").splitlines():
  if not line.strip() or ":" not in line:continue
  key,value=line.split(":",1);value=value.strip().strip('"');result[key.strip()]=int(value) if value.lstrip("-").isdigit() else value
 return result
def lid(folder):
 value=meta(folder).get("id")
 if not value:raise ValueError("В _meta.yaml отсутствует id")
 return str(value)
def tess():return shutil.which("tesseract") or next((str(p) for p in TESS if p.is_file()),None)
def ocr(path,exe):
 if not exe or not path.is_file():return ""
 temporary=None
 try:
  # Windows-сборка Tesseract не всегда принимает Unicode-пути.
  with tempfile.NamedTemporaryFile(prefix="lectory_",suffix=path.suffix,delete=False) as handle:
   temporary=Path(handle.name)
  shutil.copyfile(path,temporary)
  return subprocess.run([exe,str(temporary),"stdout","-l","rus+eng","--psm","6"],check=True,capture_output=True,text=True,encoding="utf-8",errors="replace").stdout.strip()
 except (OSError,subprocess.SubprocessError) as error:
  print(f"OCR не выполнен для {path.name}: {error}",file=sys.stderr)
  return ""
 finally:
  if temporary:temporary.unlink(missing_ok=True)
def main():
 p=argparse.ArgumentParser();p.add_argument("lecture_folder",type=Path);p.add_argument("--dry-run",action="store_true");a=p.parse_args();folder=a.lecture_folder.expanduser().resolve();
 if not a.dry_run:start(folder,6)
 timing=load(folder/"json/video-screenshot-timings.json",False);transcript=load(folder/"json/transcript.json",False);pdf=load(folder/"json/pdf.json",False);shots=timing.get("screenshots",[]);exe=tess()
 if a.dry_run:print(f"Transcript: preserved; screenshots: {len(shots)}; PDF items: {len(pdf.get('items',[]))}; OCR: {'available' if exe else 'not available'}");return 0
 merged=[]
 for item in shots:
  rel=item.get("screenshot_path");content=item.get("content","") or ocr(folder/str(rel),exe) if rel else item.get("content","")
  merged.append({"file_name":Path(str(rel)).name if rel else None,"path":rel,"video_file_name":Path(str(item["video_path"])).name if item.get("video_path") else None,"video_path":item.get("video_path"),"timestamp_seconds":item.get("timestamp_seconds"),"screenshot_datetime":item.get("screenshot_datetime"),"video_start_datetime":item.get("video_start_datetime"),"ocr":content})
 out=folder/"json"/f"{lid(folder)}.json";out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps({"id":lid(folder),"created_at":datetime.now(timezone.utc).isoformat(),"meta":meta(folder),"transcript":transcript,"screenshots":merged,"pdf":pdf},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 transcript_dir=folder/"transcript"
 if transcript_dir.is_dir():
  shutil.rmtree(transcript_dir)
  print(f"Удалена временная папка: {transcript_dir}")
 complete(folder,6)
 print(f"Created lecture JSON: {out}");return 0
if __name__ == "__main__":raise SystemExit(main())
