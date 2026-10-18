import json,pathlib,subprocess,unittest,shutil,os
ROOT=pathlib.Path(__file__).resolve().parents[1]
NODE=os.environ.get('NODE_BIN') or shutil.which('node') or '/usr/lib/chatgpt/resources/cua_node/bin/node'
MODULE=(ROOT/'gnome-extension/desktop-toolbar@local.codex/feedback.js').as_uri()
class FeedbackTests(unittest.TestCase):
 def js(self,body):
  script="import assert from 'node:assert/strict'; import {feedbackFor,ShortcutRegistry} from "+json.dumps(MODULE)+";\n"+body
  r=subprocess.run([NODE,'--input-type=module','-e',script],capture_output=True,text=True,timeout=5)
  self.assertEqual(r.returncode,0,r.stderr)
 def test_ring_never_intercepts_inactive_paused_or_uncertain_control(self):
  self.js("""
  for(const state of ['stopped','paused','pausing','resuming','starting','stopping'])
   assert.equal(feedbackFor(state,'working',true,false,false).visible,false);
  for(const args of [[false,false,false],[true,true,false],[true,false,true]])
   assert.equal(feedbackFor('active','working',...args).visible,false);
  const working=feedbackFor('active','working',true,false,false), ready=feedbackFor('active','waiting_executor',true,false,false);
  assert(working.visible && ready.visible && working.opacity>ready.opacity);
  """)
 def registry(self,body):
  self.js("""
  const callbacks=new Map(),released=[],allowed=[],events=[]; let next=1;
  const display={connect:(_s,fn)=>{callbacks.set(9,fn);return 9}, disconnect:id=>callbacks.delete(id),
   grab_accelerator:()=>next++, ungrab_accelerator:id=>released.push(id)};
  const wm={allowKeybinding:(...args)=>allowed.push(args)}, meta={KeyBindingFlags:{NONE:0},KeyBindingAction:{NONE:0},external_binding_name_for_action:id=>'binding-'+id},shell={ActionMode:{ALL:255,NONE:0}};
  const registry=new ShortcutRegistry(display,wm,meta,shell,event=>events.push(event));
  """+body)
 def test_shortcuts_emit_only_registered_boundary_events(self):
  self.registry("registry.register();callbacks.get(9)(display,99);callbacks.get(9)(display,1);callbacks.get(9)(display,2);assert.deepEqual(events,['pause','stop']);registry.clear();assert.equal(callbacks.size,0);assert.deepEqual(released,[1,2]);assert.equal(registry.bindings.size,0);")
 def test_conflicting_shortcut_is_reported_unavailable_and_not_ungrabbed(self):
  self.registry("display.grab_accelerator=()=>0;registry.register();assert.equal(registry.diagnostics().pause,false);assert.equal(registry.diagnostics().stop,false);registry.clear();assert.equal(released.length,0);")
 def test_registration_failure_releases_partial_shortcuts(self):
  self.registry("display.grab_accelerator=()=>{if(next===2)throw Error('conflict');return next++};registry.register();assert.deepEqual(released,[1]);assert.equal(callbacks.size,0);assert.equal(registry.diagnostics().pause,false);")
 def test_cleanup_failure_does_not_skip_other_resources_and_can_retry(self):
  self.registry("registry.register();let failed=true;display.ungrab_accelerator=id=>{if(id===1&&failed)throw Error('temporary');released.push(id)};registry.clear();assert.deepEqual(released,[2]);assert.equal(callbacks.size,0);assert.equal(registry.diagnostics().cleanup_failed,true);failed=false;registry.clear();assert.equal(registry.bindings.size,0);assert.equal(registry.diagnostics().cleanup_failed,false);")
 def test_repeated_registration_does_not_accumulate_grabs(self):
  self.registry("registry.register();registry.register();assert.deepEqual(released,[1,2]);assert.equal(registry.bindings.size,2);registry.clear();assert.deepEqual(released,[1,2,3,4]);")
