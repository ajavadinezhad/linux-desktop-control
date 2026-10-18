#!/usr/bin/python3
"""Copy only the optional passive label extension; never restart the session."""
from pathlib import Path
import shutil,json
ROOT=Path(__file__).resolve().parent;UUID='desktop-indicator@local.codex'
target=Path.home()/'.local/share/gnome-shell/extensions'/UUID
if target.exists() and json.loads((target/'metadata.json').read_text()).get('uuid')!=UUID:raise SystemExit('Unexpected extension directory')
shutil.copytree(ROOT/'gnome-extension'/UUID,target,dirs_exist_ok=True)
print(json.dumps({'installed_path':str(target),'activation':'Enable after manual logout/login if GNOME has not discovered it','session_restarted':False}))
