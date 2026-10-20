"""Extracted observer source with fake GNOME51 state; no bus or desktop."""
from pathlib import Path
import os,shutil,subprocess,unittest
ROOT=Path(__file__).resolve().parents[1]
class AuthObserverTests(unittest.TestCase):
 def run_js(self,body):
  source=(ROOT/'gnome-extension/desktop-indicator@local.codex/extension.js').read_text()
  source='\n'.join(x for x in source.splitlines() if not x.startswith('import ')).replace('export default class','class')
  fixture="""
const assert=require('node:assert/strict');class Extension{};
const Config={PACKAGE_VERSION:'51.1'};
let sequence=0;const GLib={uuid_string_random:()=> (++sequence).toString(16).padStart(32,'0'),Variant:class{constructor(sig,value){this.value=value}}};
const window={get_stable_sequence:()=>77,get_frame_rect:()=>({x:0,y:0,width:100,height:100})};
const global={display:{focus_window:window}};
const Main={sessionMode:{isLocked:false,isGreeter:false},overview:{visible:false},modalCount:0,modalActorFocusStack:[],componentManager:{_allComponents:{polkitAgent:{_currentDialog:null}}}};
const Clutter={};
"""
  setup="""
const i=new DesktopIndicator();Object.assign(i,{_failed:false,_focusEpoch:12,_authOriginWindow:window,_authDialog:null,_authAttemptId:null,_label:{visible:false},_owner:':1.7',_nonce:'a'.repeat(32)});
function present(action='org.freedesktop.packagekit.package-install'){
 const dialog={actionId:action,visible:true,state:0};
 for(const secret of ['message','userNames','_cookie','_passwordEntry'])Object.defineProperty(dialog,secret,{get(){throw Error('credential access')}});
 Main.componentManager._allComponents.polkitAgent._currentDialog=dialog;Main.modalCount=1;Main.modalActorFocusStack=[{actor:dialog}];return dialog;
}
"""
  node=os.environ.get('NODE_BIN') or shutil.which('node') or '/usr/lib/chatgpt/resources/cua_node/bin/node'
  result=subprocess.run([node,'-e',fixture+source+setup+body],text=True,capture_output=True,timeout=5)
  self.assertEqual(result.returncode,0,result.stderr)
 def test_exact_polkit_actor_and_attempt_lifetime_no_secrets(self):
  self.run_js("const d=present();const a=i._authStateData();assert.equal(a.auth_state,'visible');assert.equal(a.action_category,'system-authentication');assert.equal(a.origin_window_id,'77');assert.match(a.attempt_id,/^[a-f0-9]{32}$/);assert.equal(i._authStateData().attempt_id,a.attempt_id);assert.equal(i._contextData().available,false);assert.equal(i._contextData().reason,'auth-prompt');present();assert.notEqual(i._authStateData().attempt_id,a.attempt_id);assert.equal(Object.keys(a).sort().join(','),'action_category,attempt_id,auth_available,auth_state,dialog_phase,epoch,origin_window_id,reason');")
 def test_none_and_known_pending_opening_closing_are_bounded_coarse_states(self):
  self.run_js("assert.equal(i._authStateData().auth_state,'none');const d=present('org.debian.apt.install-packages.high-trust-repo');d.state=1;Main.modalCount=0;Main.modalActorFocusStack=[];assert.equal(i._authStateData().auth_state,'pending');d.state=2;Main.modalCount=1;Main.modalActorFocusStack=[{actor:d}];assert.equal(i._authStateData().dialog_phase,'opening');d.state=3;assert.equal(i._authStateData().auth_state,'pending');const token=i._authStateData().attempt_id;d.state=1;d.visible=false;Main.componentManager._allComponents.polkitAgent._currentDialog=null;Main.modalCount=0;Main.modalActorFocusStack=[];assert.equal(i._authStateData().auth_state,'none');assert.equal(i._authStateData().attempt_id,token);")
 def test_untrusted_modal_actor_origin_and_lock_fail_closed(self):
  self.run_js("for(const action of ['io.snapcraft.snapd.manage','org.freedesktop.packagekit.package-install-untrusted','unknown']){present(action);assert.equal(i._authStateData().auth_state,'visible');assert.equal(i._authStateData().action_category,'system-authentication');}present();Main.modalActorFocusStack=[{actor:{}}];assert.equal(i._authStateData().auth_state,'blocked');present();Main.modalCount=2;assert.equal(i._authStateData().auth_state,'blocked');present();global.display.focus_window={};assert.equal(i._authStateData().auth_state,'blocked');global.display.focus_window=window;Main.sessionMode.isLocked=true;assert.equal(i._authStateData().reason,'locked');assert.equal(i._contextData().reason,'locked');Main.sessionMode.isLocked=false;Main.sessionMode.isGreeter=true;assert.equal(i._authStateData().reason,'greeter');")
 def test_version_shape_and_authorization_capability(self):
  self.run_js("assert.equal(JSON.parse(i.GetDiagnostics()).auth_wait_protocol,3);Config.PACKAGE_VERSION='52.0';assert.equal(i._authCapable(),false);assert.equal(i._authStateData().auth_state,'blocked');Config.PACKAGE_VERSION='51.1';let reply;i.GetAuthStateAsync(['wrong'],{get_sender:()=>':1.7',return_value:v=>reply=JSON.parse(v.value[0])});assert.equal(reply.reason,'unavailable');delete Main.componentManager._allComponents.polkitAgent._currentDialog;assert.equal(i._authCapable(),false);")
 def test_shell_modal_null_focus_uses_cached_origin_but_never_another_window(self):
  self.run_js("present();global.display.focus_window=null;let a=i._authStateData();assert.equal(a.auth_state,'visible');assert.equal(a.origin_window_id,'77');assert.equal(i._contextData().reason,'auth-prompt');global.display.focus_window={};assert.equal(i._authStateData().reason,'origin-changed');global.display.focus_window=null;i._invalidWindow=window;assert.equal(i._authStateData().reason,'origin-unavailable');")
 def test_generic_polkit_wait_never_reads_or_classifies_action_name(self):
  self.run_js("const d=present('arbitrary-action');Object.defineProperty(d,'actionId',{get(){throw Error('action identity must remain private')}});const a=i._authStateData();assert.equal(a.auth_state,'visible');assert.equal(a.action_category,'system-authentication');Main.modalActorFocusStack=[{actor:{}}];assert.equal(i._authStateData().reason,'modal-mismatch');")
 def test_actual_gnome_close_order_keeps_pending_until_hidden_or_closed(self):
  self.run_js("const d=present();const a=i._authStateData();d.state=3;Main.modalCount=0;Main.modalActorFocusStack=[];Main.componentManager._allComponents.polkitAgent._currentDialog=null;global.display.focus_window=null;let b=i._authStateData();assert.equal(b.auth_state,'pending');assert.equal(b.dialog_phase,'closing');assert.equal(b.attempt_id,a.attempt_id);assert.equal(b.origin_window_id,'77');d.state=1;d.visible=false;b=i._authStateData();assert.equal(b.auth_state,'none');assert.equal(b.origin_window_id,null);assert.equal(b.attempt_id,a.attempt_id);global.display.focus_window=window;assert.equal(i._authStateData().origin_window_id,'77');")
 def test_untrusted_closing_actor_cannot_be_retained_and_destroyed_access_fails_closed(self):
  self.run_js("let d=present('unknown');Main.modalActorFocusStack=[{actor:{}}];assert.equal(i._authStateData().auth_state,'blocked');d.state=3;Main.componentManager._allComponents.polkitAgent._currentDialog=null;Main.modalCount=0;Main.modalActorFocusStack=[];assert.equal(i._authStateData().auth_state,'none');d=present();i._authStateData();Main.componentManager._allComponents.polkitAgent._currentDialog=null;Object.defineProperty(d,'state',{get(){throw Error('disposed actor')}});assert.equal(i._authStateData().reason,'auth-observer-unavailable');")

 def test_missing_polkit_dialog_is_distinct_from_untrusted_modal_actor(self):
  self.run_js("Main.modalCount=1;Main.modalActorFocusStack=[{actor:{}}];assert.equal(i._authStateData().reason,'polkit-dialog-unavailable');present('unknown');Main.modalActorFocusStack=[{actor:{}}];assert.equal(i._authStateData().reason,'modal-mismatch');")
