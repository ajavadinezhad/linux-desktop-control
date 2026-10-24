import importlib.util,json,pathlib,subprocess,unittest
from types import SimpleNamespace as NS
p=pathlib.Path(__file__).resolve().parents[1]/'check_environment.py';spec=importlib.util.spec_from_file_location('environment_test',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class EnvironmentTests(unittest.TestCase):
 def check(self,version='GNOME Shell 51.0',data=None,env=None,fail=None):
  if data is None:data={'Gio':True,'Gst':True,'xkbcommon':True,'Atspi':True,'elements':{n:True for n in ('pipewiresrc','queue','videorate','videoconvert','pngenc','appsink')}}
  calls=[]
  def run(args,**kwargs):
   calls.append(args)
   if fail:raise fail
   return NS(returncode=0,stdout=version if args[-1]=='--version' else json.dumps(data),stderr='')
  r=m.check_environment(env={'XDG_SESSION_TYPE':'wayland'} if env is None else env,run=run,which=lambda x:x)
  self.assertFalse(r['changed_settings']);self.assertFalse(r['requested_sharing']);self.assertEqual(len(calls),2)
  return r
 def test_supported_environment_passes_without_portal_or_settings_calls(self):self.assertTrue(self.check()['ready'])
 def test_wrong_session_or_shell_version_refuses_install(self):
  self.assertFalse(self.check(env={'XDG_SESSION_TYPE':'x11'})['ready']);self.assertFalse(self.check(version='GNOME Shell 50.0')['ready'])
 def test_missing_core_element_refuses_install(self):
  self.assertFalse(self.check(data={'Gio':True,'Gst':True,'xkbcommon':True,'elements':{}})['ready'])
 def test_optional_accessibility_does_not_block_visual_control(self):
  r=self.check();data={'Gio':True,'Gst':True,'xkbcommon':True,'elements':{c['name'].split(':',1)[1]:True for c in r['checks'] if c['name'].startswith('gstreamer:')}}
  self.assertTrue(self.check(data=data)['ready'])
 def test_probe_timeout_and_bad_output_fail_closed(self):
  self.assertFalse(self.check(fail=subprocess.TimeoutExpired('probe',5))['ready'])
  def run(*args,**kwargs):return NS(returncode=0,stdout='not json',stderr='')
  self.assertFalse(m.check_environment(env={'WAYLAND_DISPLAY':'wayland-0'},run=run,which=lambda x:x)['ready'])
 def test_missing_executable_is_reported(self):
  r=m.check_environment(env={},run=lambda *a,**k:NS(returncode=1,stdout='',stderr='missing'),which=lambda x:None)
  self.assertFalse(r['ready']);self.assertTrue(any(c['name']=='codex' and not c['ok'] for c in r['checks']))
 def test_installer_preflight_precedes_every_mutation(self):
  s=(p.parent/'install.sh').read_text();check=s.index('/usr/bin/python3 "$root/check_environment.py"\n')
  for mutation in ('/usr/bin/python3 "$root/configure-runtime.py" "$root"',
                   '/usr/bin/python3 "$root/install-indicator.py"',
                   '"$codex_bin" plugin marketplace add', '"$codex_bin" plugin add'):
   self.assertLess(check,s.index(mutation),mutation)
if __name__=='__main__':unittest.main()
