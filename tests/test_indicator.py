import json,pathlib,subprocess,unittest,os,shutil
from types import SimpleNamespace as NS
import importlib.util
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('indicator_test',ROOT/'plugins/linux-desktop-control/indicator_bridge.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Reply:
 def __init__(self,*values):self.values=values
 def unpack(self):return self.values
class Bus:
 def __init__(self):self.calls=[];self.reject=None
 def call_sync(self,dest,path,iface,method,args,*other):
  self.calls.append((dest,path,iface,method,args.unpack()))
  if self.reject==method:raise RuntimeError('disconnected')
  if method=='GetNameOwner':return Reply(':1.9')
  if method=='GetDiagnostics':return Reply('{"protocol_version":1}')
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
  const global={get_pointer:()=>[300,200]};
  const GLib={PRIORITY_DEFAULT:0,SOURCE_CONTINUE:true,SOURCE_REMOVE:false,get_monotonic_time:()=>now,timeout_add:(_p,_t,fn)=>{timers.set(next,fn);return next++},source_remove:id=>timers.delete(id),Variant:class{constructor(_sig,value){this.value=value}}};
  const Gio={DBus:{session:{}},BusNameWatcherFlags:{NONE:0},bus_watch_name_on_connection:(_b,_n,_f,_a,fn)=>{watches.set(next,fn);return next++},bus_unwatch_name:id=>watches.delete(id),DBusExportedObject:{wrapJSObject:()=>({export(){},unexport(){}})}};
  """
  script=fixture+source+"\nconst i=new DesktopIndicator();i.enable();let reply;const invocation={get_sender:()=>':1.9',return_value:v=>reply=v.value};const nonce='a'.repeat(32);\n"+body
  r=subprocess.run([node,'-e',script],text=True,capture_output=True,timeout=5);self.assertEqual(r.returncode,0,r.stderr)
 def test_label_is_click_through_shown_only_during_authenticated_activity(self):
  self.run_js("assert.equal(actors.length,1);const label=actors[0];assert.equal(label.reactive,false);assert.equal(label.can_focus,false);i.BindAsync([nonce],invocation);i.UpdateAsync(['wrong',true],invocation);assert.equal(label.visible,false);i.UpdateAsync([nonce,true],invocation);assert.equal(label.text,'Mouse is being controlled by ChatGPT');assert.equal(label.visible,true);assert.deepEqual(label.position,[200,226]);i.UpdateAsync([nonce,false],invocation);assert.equal(label.visible,false);i.disable();")
 def test_lock_owner_loss_and_lease_expiry_hide_label(self):
  self.run_js("const label=actors[0];i.BindAsync([nonce],invocation);i.UpdateAsync([nonce,true],invocation);Main.sessionMode.isLocked=true;i._render();assert.equal(label.visible,false);Main.sessionMode.isLocked=false;i._render();assert.equal(label.visible,true);now=4000000;timers.values().next().value();assert.equal(label.visible,false);assert.equal(i._owner,null);i.BindAsync([nonce],invocation);i.UpdateAsync([nonce,true],invocation);watches.values().next().value();assert.equal(label.visible,false);i.disable();assert.equal(label.destroyed,true);assert.equal(timers.size,0);")
 def test_render_error_removes_visible_label_without_cursor_mutation(self):
  self.run_js("const label=actors[0];i.BindAsync([nonce],invocation);i.UpdateAsync([nonce,true],invocation);global.get_pointer=()=>{throw Error('unavailable')};Gio.bus_unwatch_name=()=>{throw Error('watch failure')};assert.equal(timers.values().next().value(),false);assert.equal(label.visible,false);i.BindAsync([nonce],invocation);assert.deepEqual(reply,[false]);i.UpdateAsync([nonce,true],invocation);assert.deepEqual(reply,[false]);assert.equal(label.visible,false);assert.equal(i._owner,null);i.disable();assert.equal(label.destroyed,true);")
