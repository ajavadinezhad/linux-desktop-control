#!/usr/bin/python3
"""Install validated candidate assets only. Never activate a desktop preference."""
import hashlib,json,os,shutil,struct,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
source=ROOT/'cursor-theme/CodexGlow-Yaru-candidate'
hash=hashlib.sha256()
for entry in sorted(source.rglob('*')):
 if entry.is_file() or entry.is_symlink():
  hash.update(str(entry.relative_to(source)).encode())
  hash.update(os.readlink(entry).encode() if entry.is_symlink() else entry.read_bytes())
name='CodexGlow-Yaru-'+hash.hexdigest()[:16]
manifest=json.loads((source/'manifest.json').read_text())
for entry in (source/'cursors').iterdir():
 if not entry.resolve().is_relative_to(source.resolve()):raise SystemExit('Unsafe alias')
 if entry.is_symlink() or entry.suffix in ('.cur','.ani'):continue
 data=entry.read_bytes()
 if len(data)>16*1024*1024 or len(data)<16:raise SystemExit('Invalid cursor size')
 magic,header,version,count=struct.unpack_from('<4I',data)
 if magic!=0x72756358 or header<16 or not 0<count<=1024 or header+count*12>len(data):raise SystemExit('Invalid cursor header')
 frames=[]
 for i in range(count):
  kind,size,offset=struct.unpack_from('<3I',data,header+i*12)
  if kind!=0xfffd0002:continue
  if offset+36>len(data):raise SystemExit('Truncated cursor')
  ch,ct,sub,cv,w,h,x,y,delay=struct.unpack_from('<9I',data,offset)
  end=offset+ch+w*h*4
  if ch<36 or ct!=kind or not 0<w<=512 or not 0<h<=512 or x>=w or y>=h or end>len(data) or not any(data[offset+ch+3:end:4]):raise SystemExit('Blank/invalid cursor')
  frames.append(dict(size=size,width=w,height=h,hotspot=[x,y],delay=delay))
 if frames!=manifest[entry.name]['frames']:raise SystemExit('Cursor geometry mismatch')
icons=Path.home()/'.local/share/icons';icons.mkdir(parents=True,exist_ok=True)
dest=icons/name
if not dest.exists():
 temp=Path(tempfile.mkdtemp(prefix='.codex-glow-',dir=icons));shutil.rmtree(temp)
 try:
  shutil.copytree(source,temp,symlinks=True)
  (temp/'index.theme').write_text('[Icon Theme]\nName='+name+'\nComment=Temporary actual cursor glow derived from Yaru\n')
  os.replace(temp,dest)
 finally:
  if temp.exists():shutil.rmtree(temp)
config={'theme':name,'theme_root':str(icons),'state_dir':str(Path.home()/'.local/state/linux-desktop-control/cursor-theme')}
p=ROOT/'plugins/linux-desktop-control/cursor_theme_config.json';p.write_text(json.dumps(config,indent=2)+'\n')
print(json.dumps({'installed_theme':name,'activated':False}))
