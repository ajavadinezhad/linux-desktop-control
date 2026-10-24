import json,pathlib,subprocess,unittest,os,shutil
from types import SimpleNamespace as NS
import importlib.util
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('indicator_test',ROOT/'plugins/linux-desktop-control/indicator_bridge.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Reply:
 def __init__(self,*values):self.values=values
 def unpack(self):return self.values
class Bus:
 def signal_subscribe(self,*args):return 1
 def signal_unsubscribe(self,*args):pass
 def __init__(self):self.calls=[];self.reject=None
 def call_sync(self,dest,path,iface,method,args,*other):
  self.calls.append((dest,path,iface,method,args.unpack()))
  if self.reject==method:raise RuntimeError('disconnected')
  if method=='GetNameOwner':return Reply(':1.9')
  if method=='GetDiagnostics':return Reply('{"protocol_version":2,"pointer_snapshot":true}')
  return Reply(True)
class IndicatorBridgeTests(unittest.TestCase):
 def start(self):
  from unittest.mock import patch
  b=Bus();state={'active':True};i=m.IndicatorBridge(lambda:state,b)
  with patch.object(m.threading,'Thread'):i.start()
  return i,b,state
 def test_only_passive_boolean_is_published_to_pinned_owner(self):
  i,b,state=self.start();state['secret']='private';i.update()
  self.assertEqual(b.calls[-1][0],':1.9');self.assertEqual(b.calls[-1][3],'Update');self.assertIs(b.calls[-1][-1][-1],True);self.assertNotIn('private',str(b.calls))
 def test_close_hides_before_unbinding_and_is_idempotent(self):
  i,b,_=self.start();i.close();count=len(b.calls);i.close()
  self.assertEqual(len(b.calls),count);self.assertEqual([c[3] for c in b.calls[-2:]],['Update','Unbind']);self.assertIs(b.calls[-2][-1][-1],False);self.assertFalse(i.bound)
 def test_update_failure_still_attempts_unbind(self):
  i,b,_=self.start();b.reject='Update';i.close();self.assertEqual(b.calls[-1][3],'Unbind');self.assertTrue(i.closed.is_set())
class IndicatorActorTests(unittest.TestCase):
 def run_js(self,body):
  node=os.environ.get('NODE_BIN') or shutil.which('node') or '/usr/lib/chatgpt/resources/cua_node/bin/node'
  source=(ROOT/'gnome-extension/desktop-indicator@local.codex/extension.js').read_text()
  source='\n'.join(x for x in source.splitlines() if not x.startswith('import ')).replace('export default class','class')
  fixture="""
  const assert=require('node:assert/strict'); let now=0,next=1; const timers=new Map(),watches=new Map(),actors=[];
  class Extension{};
  class Label {constructor(props){Object.assign(this,props)}hide(){this.visible=false}show(){this.visible=true}set_position(x,y){this.position=[x,y]}get_preferred_width(){return [200,200]}get_preferred_height(){return [20,20]}destroy(){this.destroyed=true}}
  const St={Label};const Main={uiGroup:{add_child:a=>actors.push(a)},modalCount:0,overview:{visible:false},sessionMode:{isLocked:false,isGreeter:false},layoutManager:{monitors:[{x:0,y:0,width:1000,height:800}]}};
  class Signals {constructor(){this.handlers=new Map();this.seq=100}connect(name,fn){const id=this.seq++;this.handlers.set(id,[name,fn]);return id}disconnect(id){this.handlers.delete(id)}emit(name){for(const [n,fn] of [...this.handlers.values()])if(n===name)fn(this)}}
  const win=Object.assign(new Signals(),{rect:[0,32,1000,768],get_frame_rect(){return {x:this.rect[0],y:this.rect[1],width:this.rect[2],height:this.rect[3]}},get_stable_sequence:()=>1});
  Object.assign(Main.overview,new Signals());Main.overview.connect=Signals.prototype.connect;Main.overview.disconnect=Signals.prototype.disconnect;
  Object.assign(Main.sessionMode,new Signals());Main.sessionMode.connect=Signals.prototype.connect;Main.sessionMode.disconnect=Signals.prototype.disconnect;
  Main.layoutManager.primaryMonitor={x:0,y:0,width:1000,height:800};
  const global={get_pointer:()=>[300,200],display:Object.assign(new Signals(),{focus_window:win})};
  const contextSignals=[];
  const filters=new Map();let filterNext=1;
  const Clutter={EVENT_PROPAGATE:false,event_add_filter:(stage,fn)=>{assert.equal(stage,global.stage);const id=filterNext++;filters.set(id,fn);return id},event_remove_filter:id=>filters.delete(id)};
  const sourceEvent=node=>({get_source_device:()=>node===null?null:{get_device_node:()=>node},get_key_symbol:()=>{throw Error('key read')},get_coords:()=>{throw Error('coordinate read')},get_button:()=>{throw Error('button read')}});


  const GLib={PRIORITY_DEFAULT:0,SOURCE_CONTINUE:true,SOURCE_REMOVE:false,get_monotonic_time:()=>now,timeout_add:(_p,_t,fn)=>{timers.set(next,fn);return next++},source_remove:id=>timers.delete(id),Variant:class{constructor(_sig,value){this.value=value}}};
  const Gio={DBus:{session:{emit_signal:(...args)=>contextSignals.push(args)}},BusNameWatcherFlags:{NONE:0},bus_watch_name_on_connection:(_b,_n,_f,_a,fn)=>{watches.set(next,fn);return next++},bus_unwatch_name:id=>watches.delete(id),DBusExportedObject:{wrapJSObject:()=>({export(){},unexport(){}})}};
  """
  script=fixture+source+"\nconst i=new DesktopIndicator();i.enable();let reply;const invocation={get_sender:()=>':1.9',return_value:v=>reply=v.value};const nonce='a'.repeat(32);\n"+body
  r=subprocess.run([node,'-e',script],text=True,capture_output=True,timeout=5);self.assertEqual(r.returncode,0,r.stderr)
 def test_label_is_click_through_shown_only_during_authenticated_activity(self):
  self.run_js("assert.equal(actors.length,1);const label=actors[0];assert.equal(label.reactive,false);assert.equal(label.can_focus,false);i.BindAsync([nonce],invocation);i.UpdateAsync(['wrong',true],invocation);assert.equal(label.visible,false);i.UpdateAsync([nonce,true],invocation);assert.equal(label.text,'Desktop sharing active');assert.equal(label.visible,true);assert.deepEqual(label.position,[200,226]);i.UpdateAsync([nonce,false],invocation);assert.equal(label.visible,false);i.disable();")
 def test_lock_owner_loss_and_lease_expiry_hide_label(self):
  self.run_js("const label=actors[0];i.BindAsync([nonce],invocation);i.UpdateAsync([nonce,true],invocation);Main.sessionMode.isLocked=true;i._render();assert.equal(label.visible,false);Main.sessionMode.isLocked=false;i._render();assert.equal(label.visible,true);now=4000000;timers.values().next().value();assert.equal(label.visible,false);assert.equal(i._owner,null);i.BindAsync([nonce],invocation);i.UpdateAsync([nonce,true],invocation);watches.values().next().value();assert.equal(label.visible,false);i.disable();assert.equal(label.destroyed,true);assert.equal(timers.size,0);")
 def test_render_error_removes_visible_label_without_cursor_mutation(self):
  self.run_js("const label=actors[0];i.BindAsync([nonce],invocation);i.UpdateAsync([nonce,true],invocation);global.get_pointer=()=>{throw Error('unavailable')};Gio.bus_unwatch_name=()=>{throw Error('watch failure')};assert.equal(timers.values().next().value(),false);assert.equal(label.visible,false);i.BindAsync([nonce],invocation);assert.deepEqual(reply,[false]);i.UpdateAsync([nonce,true],invocation);assert.deepEqual(reply,[false]);assert.equal(label.visible,false);assert.equal(i._owner,null);i.disable();assert.equal(label.destroyed,true);")

 def test_focus_away_and_back_and_geometry_events_advance_context(self):
  self.run_js("i.BindAsync([nonce],invocation);const first=i._focusEpoch;global.display.focus_window=null;global.display.emit('notify::focus-window');global.display.focus_window=win;global.display.emit('notify::focus-window');assert(i._focusEpoch>=first+2);const e=i._focusEpoch;win.rect[2]+=10;win.emit('size-changed');assert(i._focusEpoch>e);assert(contextSignals.length>=3);i.GetContextAsync([nonce],invocation);const data=JSON.parse(reply[0]);assert.equal(data.rect[2],1010);assert(!('title' in data));i.disable();assert.equal(win.handlers.size,0);assert.equal(global.display.handlers.size,0);")
 def test_foreign_modal_overview_lock_and_unmanaged_are_fail_closed(self):
  self.run_js("i.BindAsync([nonce],invocation);Main.modalCount=1;i.GetContextAsync([nonce],invocation);assert.equal(JSON.parse(reply[0]).available,false);Main.modalCount=1;Main.overview.visible=true;i.GetContextAsync([nonce],invocation);assert.equal(JSON.parse(reply[0]).kind,'overview');Main.modalCount=2;i.GetContextAsync([nonce],invocation);assert.equal(JSON.parse(reply[0]).available,false);Main.modalCount=0;Main.overview.visible=false;Main.sessionMode.isLocked=true;i.GetContextAsync([nonce],invocation);assert.equal(JSON.parse(reply[0]).available,false);Main.sessionMode.isLocked=false;win.emit('unmanaging');i.GetContextAsync([nonce],invocation);assert.equal(JSON.parse(reply[0]).available,false);i.disable();")

class IndicatorFailureTests(unittest.TestCase):
 def test_heartbeat_failure_closes_bridge_before_notifying_owner_once(self):
  i,b,_=IndicatorBridgeTests().start();failures=[]
  i.on_failure=lambda:failures.append((i.closed.is_set(),i.bound))
  b.reject='Update'
  from unittest.mock import patch
  with patch.object(i.closed,'wait',return_value=False):i.publish()
  self.assertEqual(failures,[(True,False)]);self.assertEqual(b.calls[-1][3],'Unbind')
 def test_overview_keeps_label_visible_but_foreign_modal_hides_it(self):
  IndicatorActorTests().run_js("i.BindAsync([nonce],invocation);i.UpdateAsync([nonce,true],invocation);Main.overview.visible=true;Main.modalCount=1;Main.overview.emit=Signals.prototype.emit;Main.overview.emit('showing');i._render();assert.equal(actors[0].visible,true);Main.modalCount=2;i._render();assert.equal(actors[0].visible,false);Main.modalCount=0;Main.overview.visible=false;i._render();assert.equal(actors[0].visible,true);i.disable();")

 def test_manually_closed_heartbeat_does_not_report_new_failure(self):
  i,b,_=IndicatorBridgeTests().start();failures=[];i.on_failure=lambda:failures.append(True)
  def update():i.close();raise RuntimeError('retired connection')
  i.update=update
  from unittest.mock import patch
  with patch.object(i.closed,'wait',return_value=False):i.publish()
  self.assertEqual(failures,[])

class PhysicalActivityCandidateTests(unittest.TestCase):
 run_js=IndicatorActorTests.run_js
 def test_default_disabled_authenticated_opt_in_and_passive_latched_activity(self):
  self.run_js("assert.equal(filters.size,0);i.BindAsync([nonce],invocation);i.UpdateAsync([nonce,true],invocation);assert.equal(filters.size,0);i.SetPhysicalGuardAsync(['wrong',true],invocation);assert.deepEqual(reply,[false]);assert.equal(filters.size,0);i.SetPhysicalGuardAsync([nonce,true],invocation);assert.deepEqual(reply,[true]);assert.equal(filters.size,1);const cb=[...filters.values()][0],e=i._focusEpoch;assert.equal(cb(sourceEvent(null)),false);assert.equal(cb(sourceEvent('')),false);assert.equal(i._focusEpoch,e);assert.equal(cb(sourceEvent('/dev/input/event7')),false);assert.equal(i._focusEpoch,e+1);assert.equal(filters.size,0);assert.equal(cb(sourceEvent('/dev/input/event7')),false);assert.equal(i._focusEpoch,e+1);i.GetContextAsync([nonce],invocation);assert.equal(JSON.parse(reply[0]).reason,'device-source-activity');i.SetPhysicalGuardAsync([nonce,true],invocation);assert.deepEqual(reply,[false]);i.disable();")
 def test_activity_candidate_cleanup_paths_and_protected_state(self):
  self.run_js("i.BindAsync([nonce],invocation);i.SetPhysicalGuardAsync([nonce,true],invocation);assert.equal(filters.size,0);i.UpdateAsync([nonce,true],invocation);assert.equal(filters.size,1);i.UpdateAsync([nonce,false],invocation);assert.equal(filters.size,0);i.UpdateAsync([nonce,true],invocation);assert.equal(filters.size,1);Main.sessionMode.isLocked=true;i._contextChanged(false,true);assert.equal(filters.size,0);i.SetPhysicalGuardAsync([nonce,true],invocation);assert.deepEqual(reply,[false]);Main.sessionMode.isLocked=false;i.SetPhysicalGuardAsync([nonce,true],invocation);assert.equal(filters.size,1);now=4000000;timers.values().next().value();assert.equal(filters.size,0);i.BindAsync([nonce],invocation);i.SetPhysicalGuardAsync([nonce,true],invocation);i.UpdateAsync([nonce,true],invocation);assert.equal(filters.size,1);i.UnbindAsync([nonce],invocation);assert.equal(filters.size,0);i.disable();")
 def test_activity_candidate_callback_and_cleanup_failure_latch(self):
  self.run_js("i.BindAsync([nonce],invocation);i.UpdateAsync([nonce,true],invocation);i.SetPhysicalGuardAsync([nonce,true],invocation);const cb=[...filters.values()][0];Clutter.event_remove_filter=()=>{throw Error('remove failed')};assert.equal(cb({get_source_device:()=>{throw Error('unknown source')}}),false);assert.equal(i._failed,true);i.GetContextAsync([nonce],invocation);assert.equal(JSON.parse(reply[0]).available,false);i.SetPhysicalGuardAsync([nonce,true],invocation);assert.deepEqual(reply,[false]);i.UnbindAsync([nonce],invocation);assert.equal(cb(sourceEvent('/dev/input/event7')),false);assert.equal(i._owner,null);i.disable();")

 def test_activity_candidate_owner_loss_disable_and_missing_api(self):
  self.run_js("i.BindAsync([nonce],invocation);i.UpdateAsync([nonce,true],invocation);i.SetPhysicalGuardAsync([nonce,true],invocation);assert.equal(filters.size,1);watches.values().next().value();assert.equal(filters.size,0);i.BindAsync([nonce],invocation);i.UpdateAsync([nonce,true],invocation);Clutter.event_add_filter=undefined;i.SetPhysicalGuardAsync([nonce,true],invocation);assert.deepEqual(reply,[false]);assert.equal(filters.size,0);i.disable();")
 def test_activity_candidate_disable_removes_filter_and_does_not_export_metadata(self):
  self.run_js("i.BindAsync([nonce],invocation);i.UpdateAsync([nonce,true],invocation);i.SetPhysicalGuardAsync([nonce,true],invocation);const cb=[...filters.values()][0];assert.equal(cb(sourceEvent('/dev/input/private-device')),false);assert(!JSON.stringify(contextSignals).includes('/dev/input'));assert(!i.GetDiagnostics().includes('/dev/input'));i.UnbindAsync([nonce],invocation);i.BindAsync([nonce],invocation);i.UpdateAsync([nonce,true],invocation);i.SetPhysicalGuardAsync([nonce,true],invocation);assert.equal(filters.size,1);i.disable();assert.equal(filters.size,0);")
