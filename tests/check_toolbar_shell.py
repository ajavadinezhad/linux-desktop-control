#!/usr/bin/python3
"""Real toolbar rendering in a PRIVATE D-Bus/headless GNOME session only. Never host input."""
import os,pathlib,tempfile,subprocess,time,json,threading,shutil,importlib.util
from gi.repository import Gio,GLib
OUT=pathlib.Path(__file__).resolve().parents[1]
ROOT=OUT
(OUT/'test-evidence').mkdir(exist_ok=True)
tmp=tempfile.TemporaryDirectory(prefix='codex-shell-toolbar-');base=pathlib.Path(tmp.name)
extension=base/'data/gnome-shell/extensions/desktop-toolbar@local.codex'
shutil.copytree(OUT/'gnome-extension/desktop-toolbar@local.codex',extension)
# Test-only capabilities exist ONLY in this isolated temporary copy.
javascript=(extension/'extension.js').read_text().replace("import Clutter", "import Shell from 'gi://Shell';\nimport Clutter",1)
javascript=javascript.replace('</interface></node>`', '<method name="TestScreenshot"><arg type="s" direction="in"/><arg type="b" direction="out"/></method><method name="TestClick"><arg type="s" direction="in"/></method><method name="TestDock"/><method name="TestFocus"><arg type="s" direction="out"/></method></interface></node>`')
marker='    _button(label, accessibleName, event) {'
methods='''    async TestScreenshotAsync([path], invocation) {
        try {
            const stream = Gio.File.new_for_path(path).replace(null, false, Gio.FileCreateFlags.REPLACE_DESTINATION, null);
            await new Shell.Screenshot().screenshot(false, stream);
            stream.close(null); invocation.return_value(new GLib.Variant('(b)', [true]));
        } catch (_) { invocation.return_value(new GLib.Variant('(b)', [false])); }
    }
    TestClick(event) {
        const button = {pause: this._pause, continue: this._continue, stop: this._stop}[event];
        if (button) button.emit('clicked', 1);
    }
    TestFocus() {return global.display.focus_window?.title ?? '';}
    TestDock() {
        const m = Main.layoutManager.primaryMonitor;
        this._testDock = new St.Widget({style: 'background-color: #444444;', reactive: false});
        this._testDock.set_position(m.x, m.y+m.height-72);this._testDock.set_size(m.width,72);
        Main.layoutManager.addChrome(this._testDock,{affectsStruts:true,trackFullscreen:false});
    }
'''
javascript=javascript.replace(marker,methods+marker)
(extension/'extension.js').write_text(javascript)
env=dict(os.environ,XDG_DATA_HOME=str(base/'data'),XDG_CONFIG_HOME=str(base/'config'),GSETTINGS_BACKEND='memory')
bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
if bus.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','NameHasOwner',GLib.Variant('(s)',('org.gnome.Shell',)),None,Gio.DBusCallFlags.NONE,1000,None).unpack()[0]:
 raise SystemExit('Refusing to use an existing desktop bus. Run this test under dbus-run-session.')
log=(OUT/'test-evidence/toolbar-nested-shell.log').open('w')
fixture=None
proc=subprocess.Popen(['gnome-shell','--headless','--wayland','--virtual-monitor','1280x720','--wayland-display','codex-toolbar-test'],env=env,stdout=log,stderr=log)
loop=GLib.MainLoop();threading.Thread(target=loop.run,daemon=True).start()
bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
def call(interface,method,signature,args,path='/org/gnome/Shell/Extensions'):
 return bus.call_sync('org.gnome.Shell.Extensions' if interface=='org.gnome.Shell.Extensions' else 'org.gnome.Shell',path,interface,method,GLib.Variant(signature,args),None,Gio.DBusCallFlags.NONE,3000,None).unpack()
result={'scope':'Isolated headless GNOME51 Shell, real extension actors and D-Bus; no host desktop input or consent bypass','checks':{}}
try:
 deadline=time.monotonic()+20
 while True:
  try:
   if call('org.gnome.Shell.Extensions','GetExtensionInfo','(s)',('desktop-toolbar@local.codex',))[0]:break
  except Exception as e:result['last_start_error']=str(e)
  if proc.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Nested Shell not ready; see log')
  time.sleep(.2)
 result['enable']=call('org.gnome.Shell.Extensions','EnableExtension','(s)',('desktop-toolbar@local.codex',))
 time.sleep(1)
 fixture_script=base/'fixture.py'
 fixture_script.write_text("import gi\ngi.require_version('Gtk','3.0')\nfrom gi.repository import Gtk\nw=Gtk.Window(title='Disposable toolbar focus fixture');w.add(Gtk.Label(label='Disposable isolated GNOME toolbar layout test'));w.maximize();w.show_all();w.present();Gtk.main()\n")
 fixture=subprocess.Popen(['/usr/bin/python3',str(fixture_script)],env=dict(env,WAYLAND_DISPLAY='codex-toolbar-test',GDK_BACKEND='wayland'),stdout=log,stderr=log)
 time.sleep(1)
 focus_before=call('org.codex.DesktopToolbar','TestFocus','()',(),path='/org/codex/DesktopToolbar')[0]
 spec=importlib.util.spec_from_file_location('toolbar',OUT/'plugins/linux-desktop-control/toolbar_bridge.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 state={'control_state':'active','control_epoch':0,'portal_closed_confirmed':False}
 events=[];bridge=mod.ToolbarBridge(lambda:state,lambda event,expected_epoch=None:events.append(event),bus)
 bridge.start();time.sleep(1)
 diag=bridge.diagnostics();result['active_diagnostics']=diag
 result['checks']['one_compact_bottom_actor']=diag['visible'] and diag['actors']==1 and 0<diag['rect'][2]<=480 and 0<diag['rect'][3]<=60 and abs(diag['rect'][1]+diag['rect'][3]-720)<2
 result['checks']['reserved_strip']=diag.get('reserves_bottom_strip') is True
 focus_after=call('org.codex.DesktopToolbar','TestFocus','()',(),path='/org/codex/DesktopToolbar')[0]
 result['focus']=[focus_before,focus_after]
 result['checks']['mapping_did_not_steal_focus']=focus_before=='Disposable toolbar focus fixture' and focus_after==focus_before
 result['preview']=call('org.codex.DesktopToolbar','TestScreenshot','(s)',(str(OUT/'TOOLBAR_PREVIEW.png'),),path='/org/codex/DesktopToolbar')
 call('org.codex.DesktopToolbar','TestClick','(s)',('pause',),path='/org/codex/DesktopToolbar');time.sleep(.15)
 result['checks']['real_pause_button_signal']=events==['pause']
 state.update(control_state='paused',control_epoch=1,portal_closed_confirmed=True);bridge._update();time.sleep(.3)
 diag=bridge.diagnostics();result['paused_diagnostics']=diag
 result['checks']['continue_only_paused']=diag['can_continue'] is True and diag['state']=='paused'
 call('org.codex.DesktopToolbar','TestClick','(s)',('continue',),path='/org/codex/DesktopToolbar');time.sleep(.15)
 call('org.codex.DesktopToolbar','TestClick','(s)',('stop',),path='/org/codex/DesktopToolbar');time.sleep(.15)
 result['checks']['real_continue_and_stop_signals']=events==['pause','continue','stop']
 state.update(control_state='stopped');bridge._update();time.sleep(.3)
 result['checks']['hidden_when_stopped']=not bridge.diagnostics()['visible']
 call('org.codex.DesktopToolbar','TestDock','()',(),path='/org/codex/DesktopToolbar');time.sleep(.4)
 state.update(control_state='active');bridge._update();time.sleep(.4)
 dock_diag=bridge.diagnostics();result['dock_diagnostics']=dock_diag
 result['checks']['avoids_existing_dock']=dock_diag['rect'][1]+dock_diag['rect'][3]<=648 and dock_diag['workarea']['y']+dock_diag['workarea']['height']<=dock_diag['rect'][1]
 result['dock_preview']=call('org.codex.DesktopToolbar','TestScreenshot','(s)',(str(OUT/'TOOLBAR_DOCK_PREVIEW.png'),),path='/org/codex/DesktopToolbar')
 bridge.close()
 fixture.terminate();fixture.wait(timeout=3)
 result['errors']=call('org.gnome.Shell.Extensions','GetExtensionErrors','(s)',('desktop-toolbar@local.codex',))
 result['checks']['no_extension_errors']=not result['errors'][0]
 result['result']='passed' if all(result['checks'].values()) else 'failed'
except Exception as e:result['result']='failed';result['error']=str(e)
finally:
 if fixture and fixture.poll() is None:
  fixture.terminate()
  try:fixture.wait(timeout=3)
  except subprocess.TimeoutExpired:fixture.kill();fixture.wait()
 proc.terminate()
 try:proc.wait(timeout=5)
 except subprocess.TimeoutExpired:proc.kill();proc.wait()
 loop.quit();log.close();tmp.cleanup()
 (OUT/'NESTED_TOOLBAR_RESULT.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
