#!/usr/bin/python3
"""Install only this user-scoped extension; never restart the user's session."""
import datetime,json,pathlib,shutil
from gi.repository import Gio,GLib
ROOT=pathlib.Path(__file__).resolve().parent
UUID='desktop-toolbar@local.codex'
source=ROOT/'gnome-extension'/UUID
target=pathlib.Path.home()/'.local/share/gnome-shell/extensions'/UUID
backup=None
if target.exists():
 if not (target/'metadata.json').exists() or json.loads((target/'metadata.json').read_text()).get('uuid')!=UUID:raise SystemExit('Unexpected extension folder; refusing overwrite')
 backup=ROOT/'extension-backups'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')/UUID
 backup.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(target,backup)
shutil.copytree(source,target,dirs_exist_ok=True)
settings=Gio.Settings.new('org.gnome.shell');enabled=settings.get_strv('enabled-extensions')
if UUID not in enabled:settings.set_strv('enabled-extensions',enabled+[UUID]);Gio.Settings.sync()
result={'installed_path':str(target),'backup':str(backup) if backup else None,'activation':'logout/login required','session_restarted':False}
try:
 bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
 info=bus.call_sync('org.gnome.Shell.Extensions','/org/gnome/Shell/Extensions','org.gnome.Shell.Extensions','GetExtensionInfo',GLib.Variant('(s)',(UUID,)),None,Gio.DBusCallFlags.NONE,1000,None).unpack()[0]
 if info:
  accepted=bus.call_sync('org.gnome.Shell.Extensions','/org/gnome/Shell/Extensions','org.gnome.Shell.Extensions','EnableExtension',GLib.Variant('(s)',(UUID,)),None,Gio.DBusCallFlags.NONE,1000,None).unpack()[0]
  result['activation']='requested enable; check toolbar diagnostics' if accepted else 'logout/login required'
except Exception:pass
(ROOT/'TOOLBAR_INSTALL_RESULT.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
