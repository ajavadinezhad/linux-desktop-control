import Gio from 'gi://Gio';
import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import St from 'gi://St';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as Config from 'resource:///org/gnome/shell/misc/config.js';
const PATH='/org/codex/DesktopIndicator', IFACE='org.codex.DesktopIndicator';
const XML=`<node><interface name="${IFACE}"><method name="Bind"><arg type="s" direction="in"/><arg type="b" direction="out"/></method><method name="Update"><arg type="s" direction="in"/><arg type="b" direction="in"/><arg type="b" direction="out"/></method><method name="Unbind"><arg type="s" direction="in"/><arg type="b" direction="out"/></method><method name="GetContext"><arg type="s" direction="in"/><arg type="s" direction="out"/></method><signal name="ContextChanged"><arg type="s"/><arg type="u"/></signal><method name="SetPhysicalGuard"><arg type="s" direction="in"/><arg type="b" direction="in"/><arg type="b" direction="out"/></method><method name="GetAuthState"><arg type="s" direction="in"/><arg type="s" direction="out"/></method><method name="GetDiagnostics"><arg type="s" direction="out"/></method></interface></node>`;
export default class DesktopIndicator extends Extension {
    enable() {
        this._owner=null;this._nonce=null;this._active=false;this._watch=0;this._failed=false;
        this._physicalGuard=false;this._physicalActivity=false;this._physicalFilter=0;
        this._focusEpoch=0;this._windowSignals=[];this._contextStamp='';
        this._authOriginWindow=null;this._authDialog=null;this._authAttemptId=null;
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
                this._syncPhysicalFilter();this._contextChanged(false);this._render();return GLib.SOURCE_CONTINUE;
            } catch (_) { this._failed=true; this._clear(); this._timer=0; return GLib.SOURCE_REMOVE; }
        });
    }
    _authorized(nonce,invocation){return this._owner===invocation.get_sender()&&nonce===this._nonce;}
    BindAsync([nonce],invocation){
        const sender=invocation.get_sender();let ok=!this._failed&&typeof nonce==='string'&&/^[a-f0-9]{32}$/.test(nonce)&&(!this._owner||(this._owner===sender&&this._nonce===nonce));
        if(ok&&!this._owner){this._owner=sender;this._nonce=nonce;this._updated=GLib.get_monotonic_time();this._watch=Gio.bus_watch_name_on_connection(Gio.DBus.session,sender,Gio.BusNameWatcherFlags.NONE,null,()=>this._clear());}
        invocation.return_value(new GLib.Variant('(b)',[ok]));
    }
    UpdateAsync([nonce,active],invocation){const ok=!this._failed&&this._authorized(nonce,invocation);if(ok){this._active=active===true;this._updated=GLib.get_monotonic_time();this._syncPhysicalFilter();this._render();}invocation.return_value(new GLib.Variant('(b)',[ok]));}
    UnbindAsync([nonce],invocation){const ok=this._authorized(nonce,invocation);if(ok)this._clear();invocation.return_value(new GLib.Variant('(b)',[ok]));}
    _physicalCapable(){return typeof Clutter.event_add_filter==='function'&&typeof Clutter.event_remove_filter==='function';}
    _protected(){return Main.sessionMode.isLocked||Main.sessionMode.isGreeter||Main.modalCount>1||(Main.modalCount>0&&!Main.overview.visible);}
    _removePhysicalFilter(){
        const id=this._physicalFilter;this._physicalFilter=0;
        if(id){try{Clutter.event_remove_filter(id);}catch(_){this._failed=true;}}
    }
    _syncPhysicalFilter(){
        if(this._protected()){this._physicalGuard=false;this._removePhysicalFilter();return;}
        if(this._failed||!this._owner||!this._active||!this._physicalGuard||this._physicalActivity){this._removePhysicalFilter();return;}
        if(!this._physicalFilter){
            try{
                this._physicalFilter=Clutter.event_add_filter(global.stage,(event)=>{
                    // Session-only source metadata. Never inspect keys, buttons, text or position.
                    // A native device node means source activity, not proof of human provenance.
                    try{
                        if(!this._failed&&this._owner&&this._active&&this._physicalGuard&&!this._physicalActivity){
                            if(this._protected()){this._physicalGuard=false;this._removePhysicalFilter();this._contextChanged(false,true);}
                            else {const device=event.get_source_device();if(device?.get_device_node()){
                                this._physicalActivity=true;this._removePhysicalFilter();this._contextChanged(false,true);
                            }}
                        }
                    }catch(_){this._failed=true;this._removePhysicalFilter();try{this._contextChanged(false,true);}catch(_){}}
                    finally{return Clutter.EVENT_PROPAGATE;}
                });
                if(!this._physicalFilter)throw Error('Activity observer unavailable');
            }catch(_){this._failed=true;this._removePhysicalFilter();this._contextChanged(false,true);}
        }
    }
    SetPhysicalGuardAsync([nonce,enabled],invocation){
        let ok=!this._failed&&this._authorized(nonce,invocation)&&typeof enabled==='boolean';
        if(ok&&enabled)ok=this._physicalCapable()&&!this._protected()&&!this._physicalActivity;
        if(ok){this._physicalGuard=enabled;this._syncPhysicalFilter();ok=!this._failed;}
        invocation.return_value(new GLib.Variant('(b)',[ok]));
    }
    _render(){
        if(!this._label)return;
        if(!this._owner||!this._active||(Main.modalCount>1||(Main.modalCount>0&&!Main.overview.visible))||Main.sessionMode.isLocked||Main.sessionMode.isGreeter){this._label.hide();return;}
        // Read position only. Never capture input, alter the sprite or hide/warp the real cursor.
        const [x,y]=global.get_pointer();const m=Main.layoutManager.monitors.find(m=>x>=m.x&&x<m.x+m.width&&y>=m.y&&y<m.y+m.height);
        if(!m){this._label.hide();return;}
        const width=this._label.get_preferred_width(-1)[1],height=this._label.get_preferred_height(width)[1];
        this._label.set_position(Math.max(m.x,Math.min(x-width/2,m.x+m.width-width)),Math.max(m.y,Math.min(y+26,m.y+m.height-height)));this._label.show();
    }
    _authCapable(){
        // GNOME 51 private internals, deliberately version gated. No wrapping,
        // method invocation, authentication signal or session interaction.
        try {
            return typeof Config!=='undefined'&&/^51(?:\.|$)/.test(Config.PACKAGE_VERSION)&&
                Main.componentManager?._allComponents?.polkitAgent!==undefined&&
                Object.hasOwn(Main.componentManager._allComponents.polkitAgent,'_currentDialog')&&
                Array.isArray(Main.modalActorFocusStack)&&
                typeof Main.sessionMode.isLocked==='boolean'&&typeof Main.sessionMode.isGreeter==='boolean';
        } catch (_) {return false;}
    }
    _authStateData(){
        const blocked=reason=>({auth_state:'blocked',auth_available:false,reason,action_category:'none',attempt_id:null,origin_window_id:null,dialog_phase:'none',epoch:this._focusEpoch});
        if(this._failed)return blocked('observer-unavailable');
        if(Main.sessionMode.isLocked)return blocked('locked');
        if(Main.sessionMode.isGreeter)return blocked('greeter');
        if(!this._authCapable())return blocked('auth-observer-unsupported');
        try {
            let dialog=Main.componentManager._allComponents.polkitAgent._currentDialog;
            const stack=Main.modalActorFocusStack;
            const w=global.display.focus_window;
            // GNOME clears _currentDialog immediately after close(), before
            // the closing actor's fade completes. Retain only our trusted actor.
            if(dialog===null&&this._authDialog){
                const previous=this._authDialog;
                if(previous.state===3&&previous.visible===true)dialog=previous;
                else if(previous.state!==1&&previous.visible!==false)return blocked('modal-mismatch');
            }
            if(Main.modalCount===0&&stack.length===0&&dialog===null&&!Main.overview.visible){
                const origin=w&&w!==this._invalidWindow?String(w.get_stable_sequence()):null;
                return {auth_state:'none',auth_available:false,reason:'none',action_category:'none',attempt_id:this._authAttemptId,origin_window_id:origin,dialog_phase:'none',epoch:this._focusEpoch};
            }
            // Trust the exact GNOME Polkit agent actor, never an action-name
            // allowlist. This authorizes waiting only: the human alone approves.
            const category='system-authentication';
            const sole=Main.modalCount===1&&stack.length===1&&stack[0]?.actor===dialog;
            const noModal=Main.modalCount===0&&stack.length===0;
            const phase=dialog?.state===0?'opened':dialog?.state===2?'opening':
                dialog?.state===3?'closing':dialog?.state===1?'pending':null;
            if(!dialog)return blocked('polkit-dialog-unavailable');
            if(!this._authOriginWindow||this._authOriginWindow===this._invalidWindow)return blocked('origin-unavailable');
            if(w!==null&&w!==this._authOriginWindow)return blocked('origin-changed');
            if(Main.overview.visible||!phase||
                ((phase==='opened'||phase==='opening')?(!sole||dialog.visible!==true):!(sole||noModal)))
                return blocked('modal-mismatch');
            if(this._authDialog!==dialog){
                const token=GLib.uuid_string_random().replaceAll('-','');
                if(!/^[a-f0-9]{32}$/.test(token))return blocked('auth-observer-unavailable');
                this._authDialog=dialog;this._authAttemptId=token;
            }
            const visible=phase==='opened'||phase==='opening';
            return {auth_state:visible?'visible':'pending',auth_available:true,reason:'auth-prompt',action_category:category,attempt_id:this._authAttemptId,origin_window_id:String(this._authOriginWindow.get_stable_sequence()),dialog_phase:phase,epoch:this._focusEpoch};
        } catch (_) {return blocked('auth-observer-unavailable');}
    }
    GetAuthStateAsync([nonce],invocation){
        const data=this._authorized(nonce,invocation)?this._authStateData():{auth_state:'blocked',auth_available:false,reason:'unavailable',action_category:'none',attempt_id:null,origin_window_id:null,dialog_phase:'none',epoch:this._focusEpoch};
        invocation.return_value(new GLib.Variant('(s)',[JSON.stringify(data)]));
    }
    _contextData(){
        if(this._failed)return {available:false,epoch:this._focusEpoch,reason:'unavailable'};
        if(Main.sessionMode.isLocked)return {available:false,epoch:this._focusEpoch,reason:'locked'};
        if(Main.sessionMode.isGreeter)return {available:false,epoch:this._focusEpoch,reason:'greeter'};
        if(this._physicalActivity)return {available:false,epoch:this._focusEpoch,reason:'device-source-activity'};
        if(Main.modalCount>1||(Main.modalCount>0&&!Main.overview.visible)){
            const auth=this._authStateData();
            return auth.auth_available?{available:false,epoch:this._focusEpoch,reason:'auth-prompt',auth_available:true,auth_attempt_id:auth.attempt_id,auth_action_category:auth.action_category,auth_origin_window_id:auth.origin_window_id}:{available:false,epoch:this._focusEpoch,reason:'system-ui'};
        }
        if(Main.overview.visible){const m=Main.layoutManager.primaryMonitor;if(!m)return {available:false,epoch:this._focusEpoch};return {available:true,window_id:'shell-overview',epoch:this._focusEpoch,kind:'overview',rect:[m.x,m.y,m.width,m.height]};}
        const w=global.display.focus_window;if(!w||w===this._invalidWindow)return {available:false,epoch:this._focusEpoch,reason:'no-foreground-window'};
        this._authOriginWindow=w;
        const r=w.get_frame_rect();return {available:true,window_id:String(w.get_stable_sequence()),epoch:this._focusEpoch,kind:'window',rect:[r.x,r.y,r.width,r.height]};
    }
    _contextChanged(rebind,force=false){
        if(this._protected()){this._physicalGuard=false;this._removePhysicalFilter();}
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
    GetDiagnostics(){return JSON.stringify({protocol_version:2,pointer_snapshot:true,auth_wait_protocol:this._authCapable()?3:0,auth_origin_binding:'contextual-window-only',physical_activity_candidate:this._physicalCapable(),physical_activity_opt_in:this._physicalGuard,physical_activity_latched:this._physicalActivity,failed:this._failed,active:this._active,visible:this._label.visible,reactive:false,can_focus:false,owner:this._owner,cursor_style:'system_unchanged',text:'Mouse is being controlled by ChatGPT'});}
    _clear(){this._authOriginWindow=null;this._authDialog=null;this._authAttemptId=null;this._physicalGuard=false;this._removePhysicalFilter();this._physicalActivity=false;const watch=this._watch;this._watch=0;this._owner=null;this._nonce=null;this._active=false;this._label?.hide();if(watch){try{Gio.bus_unwatch_name(watch);}catch(_){/* Visibility and ownership are already cleared. */}}}
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
