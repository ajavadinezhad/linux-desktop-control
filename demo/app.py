#!/usr/bin/python3
# Manual isolated fixture only. Never launch this before live desktop consent or use it as consent evidence.
"""Disposable GTK4 witness for real assistant target-identity regressions.

This app does not inject OS input. A command file changes only its own widgets,
so a dialog can vanish/change AFTER an observed token without another tool
invalidating that token. All text is test content; never open user documents.
"""
import argparse,json,os,re
from pathlib import Path
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib

class Fixture(Gtk.Application):
    def __init__(self,root):
        super().__init__(application_id='org.codex.TargetGuardScratch.p'+str(os.getpid()))
        self.root=root;self.window=None;self.dialog=None;self.entry=None
        self.generation=0;self.last_seq=-1;self.protected=False;self.saved=[]
    def do_activate(self):
        if self.window:self.window.present();return
        self.window=Gtk.ApplicationWindow(application=self,title='Linux Desktop Control — live scratch demo')
        self.window.set_default_size(1280,720);self.window.maximize()
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        box.set_margin_top(20);box.set_margin_bottom(20);box.set_margin_start(20);box.set_margin_end(20)
        box.append(Gtk.Label(label='LIVE GNOME DEMO • Disposable text only'))
        self.view=Gtk.TextView();self.view.set_monospace(True);self.view.set_vexpand(True)
        scroll=Gtk.ScrolledWindow();scroll.set_child(self.view);scroll.set_vexpand(True);box.append(scroll)
        button=Gtk.Button(label='Open scratch Save dialog');button.connect('clicked',lambda *_:self.open_dialog());box.append(button)
        self.label=Gtk.Label(label='Ready');box.append(self.label);self.window.set_child(box)
        self.window.present();self.view.grab_focus();GLib.timeout_add(100,self.poll);self.witness()
    def open_dialog(self):
        if self.dialog:self.dialog.destroy()
        self.generation+=1;self.protected=False
        dialog=Gtk.Window(title='Scratch Save dialog '+str(self.generation),transient_for=self.window,modal=True)
        dialog.set_application(self);dialog.set_default_size(540,220)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16)
        for side in ('top','bottom','start','end'):getattr(box,'set_margin_'+side)(20)
        box.append(Gtk.Label(label='Disposable filename (simple .txt basename only)'))
        self.entry=Gtk.Entry();box.append(self.entry)
        save=Gtk.Button(label='Save scratch text');save.connect('clicked',lambda *_:self.save());box.append(save)
        dialog.set_child(box);dialog.connect('close-request',self.closed);self.dialog=dialog
        dialog.present();self.entry.grab_focus();self.witness()
    def closed(self,*args):
        self.dialog=None;self.entry=None;self.protected=False;self.witness();return False
    def close_dialog(self):
        dialog=self.dialog;self.dialog=None;self.entry=None;self.protected=False
        if dialog:dialog.destroy()
        self.witness()
    def save(self):
        name=self.entry.get_text() if self.entry and not self.protected else ''
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,60}\.txt',name):
            self.label.set_text('Refused invalid scratch filename');return
        dest=self.root/'saved'/name
        if dest.exists():self.label.set_text('Refused existing scratch file');return
        buf=self.view.get_buffer();text=buf.get_text(buf.get_start_iter(),buf.get_end_iter(),False)
        dest.write_text(text,encoding='utf-8');self.saved.append(name);self.label.set_text('Saved '+name);self.close_dialog()
    def witness(self):
        if not self.window:return
        buf=self.view.get_buffer()
        data={'pid':os.getpid(),'last_seq':self.last_seq,'generation':self.generation,
              'dialog_visible':self.dialog is not None and self.dialog.get_visible(),
              'protected':self.protected,'main_text':buf.get_text(buf.get_start_iter(),buf.get_end_iter(),False),
              'filename':self.entry.get_text() if self.entry and not self.protected else None,'saved':list(self.saved)}
        path=self.root/'witness.json';temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data));temp.replace(path)
    def poll(self):
        path=self.root/'command.json'
        try:
            command=json.loads(path.read_text()) if path.exists() else {}
            seq=command.get('seq',-1);op=command.get('op')
            if isinstance(seq,int) and not isinstance(seq,bool) and seq>self.last_seq:
                self.last_seq=seq
                if op=='open':self.open_dialog()
                elif op=='close':self.close_dialog()
                elif op=='replace':self.close_dialog();self.open_dialog()
                elif op=='protect' and self.entry:self.protected=True;self.entry.set_visibility(False)
                elif op=='quit':self.quit();return False
            self.witness()
        except (OSError,ValueError,TypeError):pass
        return True

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--work-dir',required=True);args=parser.parse_args()
    root=Path(args.work_dir).resolve();root.mkdir(parents=True,exist_ok=True);(root/'saved').mkdir(exist_ok=True)
    Fixture(root).run([])
