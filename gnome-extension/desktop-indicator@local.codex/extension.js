import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
const PATH='/org/codex/DesktopIndicator', IFACE='org.codex.DesktopIndicator';
const XML=`<node><interface name="${IFACE}"><method name="Bind"><arg type="s" direction="in"/><arg type="b" direction="out"/></method><method name="Update"><arg type="s" direction="in"/><arg type="b" direction="in"/><arg type="b" direction="out"/></method><method name="Unbind"><arg type="s" direction="in"/><arg type="b" direction="out"/></method><method name="GetDiagnostics"><arg type="s" direction="out"/></method></interface></node>`;
export default class DesktopIndicator extends Extension {
    enable() {
        this._owner=null;this._nonce=null;this._active=false;this._watch=0;this._failed=false;
        this._label=new St.Label({text:'Mouse is being controlled by ChatGPT',style_class:'codex-control-indicator',reactive:false,can_focus:false,visible:false});
        // Not tracked as chrome: no reserved workarea or input region.
        Main.uiGroup.add_child(this._label);
        this._export=Gio.DBusExportedObject.wrapJSObject(XML,this);this._export.export(Gio.DBus.session,PATH);
        this._timer=GLib.timeout_add(GLib.PRIORITY_DEFAULT,50,()=>{
            try {
                if(this._owner&&GLib.get_monotonic_time()-this._updated>3000000)this._clear();
                this._render();return GLib.SOURCE_CONTINUE;
            } catch (_) { this._failed=true; this._clear(); this._timer=0; return GLib.SOURCE_REMOVE; }
        });
    }
    _authorized(nonce,invocation){return this._owner===invocation.get_sender()&&nonce===this._nonce;}
    BindAsync([nonce],invocation){
        const sender=invocation.get_sender();let ok=!this._failed&&typeof nonce==='string'&&/^[a-f0-9]{32}$/.test(nonce)&&(!this._owner||(this._owner===sender&&this._nonce===nonce));
        if(ok&&!this._owner){this._owner=sender;this._nonce=nonce;this._updated=GLib.get_monotonic_time();this._watch=Gio.bus_watch_name_on_connection(Gio.DBus.session,sender,Gio.BusNameWatcherFlags.NONE,null,()=>this._clear());}
        invocation.return_value(new GLib.Variant('(b)',[ok]));
    }
    UpdateAsync([nonce,active],invocation){const ok=!this._failed&&this._authorized(nonce,invocation);if(ok){this._active=active===true;this._updated=GLib.get_monotonic_time();this._render();}invocation.return_value(new GLib.Variant('(b)',[ok]));}
    UnbindAsync([nonce],invocation){const ok=this._authorized(nonce,invocation);if(ok)this._clear();invocation.return_value(new GLib.Variant('(b)',[ok]));}
    _render(){
        if(!this._label)return;
        if(!this._owner||!this._active||Main.modalCount>0||Main.overview.visible||Main.sessionMode.isLocked||Main.sessionMode.isGreeter){this._label.hide();return;}
        // Read position only. Never capture input, alter the sprite or hide/warp the real cursor.
        const [x,y]=global.get_pointer();const m=Main.layoutManager.monitors.find(m=>x>=m.x&&x<m.x+m.width&&y>=m.y&&y<m.y+m.height);
        if(!m){this._label.hide();return;}
        const width=this._label.get_preferred_width(-1)[1],height=this._label.get_preferred_height(width)[1];
        this._label.set_position(Math.max(m.x,Math.min(x-width/2,m.x+m.width-width)),Math.max(m.y,Math.min(y+26,m.y+m.height-height)));this._label.show();
    }
    GetDiagnostics(){return JSON.stringify({protocol_version:1,failed:this._failed,active:this._active,visible:this._label.visible,reactive:false,can_focus:false,owner:this._owner,cursor_style:'system_unchanged',text:'Mouse is being controlled by ChatGPT'});}
    _clear(){const watch=this._watch;this._watch=0;this._owner=null;this._nonce=null;this._active=false;this._label?.hide();if(watch){try{Gio.bus_unwatch_name(watch);}catch(_){/* Visibility and ownership are already cleared. */}}}
    disable(){
        try { this._clear(); } finally {
            if(this._timer){GLib.source_remove(this._timer);this._timer=0;}
            try { this._export?.unexport(); } finally { this._label?.destroy();this._label=null;this._export=null; }
        }
    }
}
