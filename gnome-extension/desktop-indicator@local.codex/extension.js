import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
const PATH='/org/codex/DesktopIndicator', IFACE='org.codex.DesktopIndicator';
const XML=`<node><interface name="${IFACE}"><method name="Bind"><arg type="s" direction="in"/><arg type="b" direction="out"/></method><method name="Update"><arg type="s" direction="in"/><arg type="b" direction="in"/><arg type="b" direction="out"/></method><method name="Unbind"><arg type="s" direction="in"/><arg type="b" direction="out"/></method><method name="GetContext"><arg type="s" direction="in"/><arg type="s" direction="out"/></method><signal name="ContextChanged"><arg type="s"/><arg type="u"/></signal><method name="GetDiagnostics"><arg type="s" direction="out"/></method></interface></node>`;
export default class DesktopIndicator extends Extension {
    enable() {
        this._owner=null;this._nonce=null;this._active=false;this._watch=0;this._failed=false;
        this._focusEpoch=0;this._windowSignals=[];this._contextStamp='';
        this._focusSignal=global.display.connect('notify::focus-window',()=>this._contextChanged(true));
        this._overviewSignals=['showing','hiding'].map(name=>Main.overview.connect(name,()=>this._contextChanged(false,true)));
        this._modeSignal=Main.sessionMode.connect('updated',()=>this._contextChanged(false,true));
        this._contextChanged(true);
        this._label=new St.Label({text:'Mouse is being controlled by ChatGPT',style_class:'codex-control-indicator',reactive:false,can_focus:false,visible:false});
        // Not tracked as chrome: no reserved workarea or input region.
        Main.uiGroup.add_child(this._label);
        this._export=Gio.DBusExportedObject.wrapJSObject(XML,this);this._export.export(Gio.DBus.session,PATH);
        this._timer=GLib.timeout_add(GLib.PRIORITY_DEFAULT,50,()=>{
            try {
                if(this._owner&&GLib.get_monotonic_time()-this._updated>3000000)this._clear();
                this._contextChanged(false);this._render();return GLib.SOURCE_CONTINUE;
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
        if(!this._owner||!this._active||(Main.modalCount>1||(Main.modalCount>0&&!Main.overview.visible))||Main.sessionMode.isLocked||Main.sessionMode.isGreeter){this._label.hide();return;}
        // Read position only. Never capture input, alter the sprite or hide/warp the real cursor.
        const [x,y]=global.get_pointer();const m=Main.layoutManager.monitors.find(m=>x>=m.x&&x<m.x+m.width&&y>=m.y&&y<m.y+m.height);
        if(!m){this._label.hide();return;}
        const width=this._label.get_preferred_width(-1)[1],height=this._label.get_preferred_height(width)[1];
        this._label.set_position(Math.max(m.x,Math.min(x-width/2,m.x+m.width-width)),Math.max(m.y,Math.min(y+26,m.y+m.height-height)));this._label.show();
    }
    _contextData(){
        if(this._failed||Main.sessionMode.isLocked||Main.sessionMode.isGreeter||Main.modalCount>1||(Main.modalCount>0&&!Main.overview.visible))return {available:false,epoch:this._focusEpoch,reason:'system-ui'};
        if(Main.overview.visible){const m=Main.layoutManager.primaryMonitor;if(!m)return {available:false,epoch:this._focusEpoch};return {available:true,window_id:'shell-overview',epoch:this._focusEpoch,kind:'overview',rect:[m.x,m.y,m.width,m.height]};}
        const w=global.display.focus_window;if(!w||w===this._invalidWindow)return {available:false,epoch:this._focusEpoch,reason:'no-foreground-window'};
        const r=w.get_frame_rect();return {available:true,window_id:String(w.get_stable_sequence()),epoch:this._focusEpoch,kind:'window',rect:[r.x,r.y,r.width,r.height]};
    }
    _contextChanged(rebind,force=false){
        if(rebind){
            for(const [window,id] of this._windowSignals){try{window.disconnect(id);}catch(_){}}
            this._windowSignals=[];const w=global.display.focus_window;
            if(w)for(const name of ['position-changed','size-changed','unmanaging','unmanaged','workspace-changed','highest-scale-monitor-changed'])this._windowSignals.push([w,w.connect(name,()=>{if(name==='unmanaged'||name==='unmanaging')this._invalidWindow=w;this._contextChanged(false,true);})]);
        }
        const data=this._contextData();delete data.epoch;const stamp=JSON.stringify(data);
        if(rebind||force||stamp!==this._contextStamp){
            this._contextStamp=stamp;this._focusEpoch++;
            if(this._owner)Gio.DBus.session.emit_signal(this._owner,PATH,IFACE,'ContextChanged',new GLib.Variant('(su)',[this._nonce,this._focusEpoch]));
        }
    }
    GetContextAsync([nonce],invocation){
        if(!this._authorized(nonce,invocation)||this._failed){invocation.return_value(new GLib.Variant('(s)',[JSON.stringify({available:false,reason:'unavailable'})]));return;}
        this._contextChanged(false);const data=this._contextData();if(data.available)data.pointer=global.get_pointer().slice(0,2);invocation.return_value(new GLib.Variant('(s)',[JSON.stringify(data)]));
    }
    GetDiagnostics(){return JSON.stringify({protocol_version:2,pointer_snapshot:true,failed:this._failed,active:this._active,visible:this._label.visible,reactive:false,can_focus:false,owner:this._owner,cursor_style:'system_unchanged',text:'Mouse is being controlled by ChatGPT'});}
    _clear(){const watch=this._watch;this._watch=0;this._owner=null;this._nonce=null;this._active=false;this._label?.hide();if(watch){try{Gio.bus_unwatch_name(watch);}catch(_){/* Visibility and ownership are already cleared. */}}}
    disable(){
        const clean=fn=>{try{fn();}catch(_){}};
        clean(()=>this._clear());
        if(this._focusSignal)clean(()=>global.display.disconnect(this._focusSignal));
        for(const id of this._overviewSignals??[])clean(()=>Main.overview.disconnect(id));
        if(this._modeSignal)clean(()=>Main.sessionMode.disconnect(this._modeSignal));
        for(const [window,id] of this._windowSignals??[])clean(()=>window.disconnect(id));
        if(this._timer)clean(()=>GLib.source_remove(this._timer));
        clean(()=>this._export?.unexport());clean(()=>this._label?.destroy());
        this._windowSignals=[];this._focusSignal=0;this._timer=0;this._label=null;this._export=null;
    }
}
