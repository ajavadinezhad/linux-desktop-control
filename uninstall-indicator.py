#!/usr/bin/python3
"""Remove only the passive desktop indicator."""
from pathlib import Path
import json,shutil
from gi.repository import Gio
UUID='desktop-indicator@local.codex';settings=Gio.Settings.new('org.gnome.shell')
settings.set_strv('enabled-extensions',[x for x in settings.get_strv('enabled-extensions') if x!=UUID]);Gio.Settings.sync()
p=Path.home()/'.local/share/gnome-shell/extensions'/UUID
if p.exists():
 if json.loads((p/'metadata.json').read_text()).get('uuid')!=UUID:raise SystemExit('Unexpected extension directory')
 shutil.rmtree(p)
print('Passive indicator removed; session not restarted.')
