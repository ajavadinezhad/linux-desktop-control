#!/usr/bin/python3
"""Remove only this extension and its enabled-list entry. Sources are retained."""
import json,pathlib,shutil
from gi.repository import Gio,GLib
UUID='desktop-toolbar@local.codex'
settings=Gio.Settings.new('org.gnome.shell')
settings.set_strv('enabled-extensions',[x for x in settings.get_strv('enabled-extensions') if x!=UUID]);Gio.Settings.sync()
try:
 bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
 bus.call_sync('org.gnome.Shell.Extensions','/org/gnome/Shell/Extensions','org.gnome.Shell.Extensions','DisableExtension',GLib.Variant('(s)',(UUID,)),None,Gio.DBusCallFlags.NONE,1000,None)
except Exception:pass
target=pathlib.Path.home()/'.local/share/gnome-shell/extensions'/UUID
if target.exists():
 if json.loads((target/'metadata.json').read_text()).get('uuid')!=UUID:raise SystemExit('Unexpected metadata; folder retained')
 shutil.rmtree(target)
print('Desktop toolbar extension disabled and removed. Other extensions unchanged.')
