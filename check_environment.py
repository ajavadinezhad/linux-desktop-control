#!/usr/bin/python3
"""Read-only installation preflight. Never opens sharing or changes settings."""
import argparse,json,os,pathlib,shutil,subprocess,sys

PROBE="""import gi,json,ctypes.util
results={}
for namespace,version in [('Gio','2.0'),('Gst','1.0')]:
 try:
  gi.require_version(namespace,version)
  __import__('gi.repository',fromlist=[namespace]);results[namespace]=True
 except Exception as error:results[namespace]=str(error)
if results.get('Gst') is True:
 from gi.repository import Gst
 Gst.init(None)
 results['elements']={name:bool(Gst.ElementFactory.find(name)) for name in ['pipewiresrc','queue','videorate','videoconvert','pngenc','appsink']}
results['xkbcommon']=bool(ctypes.util.find_library('xkbcommon'))
try:
 gi.require_version('Atspi','2.0');from gi.repository import Atspi;results['Atspi']=True
except Exception:results['Atspi']=False
print(json.dumps(results))
"""

def check_environment(env=None,run=subprocess.run,which=shutil.which):
 env=dict(os.environ if env is None else env);checks=[]
 def add(name,ok,detail,required=True):checks.append({'name':name,'ok':bool(ok),'required':required,'detail':detail})
 add('session',env.get('XDG_SESSION_TYPE')=='wayland' or bool(env.get('WAYLAND_DISPLAY')),'A GNOME Wayland session is required.')
 shell=which('gnome-shell')
 if shell:
  try:
   result=run([shell,'--version'],capture_output=True,text=True,timeout=5,env=env)
   version=result.stdout.strip();ok=result.returncode==0 and version.startswith('GNOME Shell 51.')
   add('gnome-shell',ok,version or 'Unable to read GNOME Shell version; only 51 is validated.')
  except (OSError,subprocess.TimeoutExpired) as error:add('gnome-shell',False,str(error))
 else:add('gnome-shell',False,'gnome-shell was not found; only GNOME Shell 51 is validated.')
 codex=env.get('CODEX_BIN','/usr/lib/chatgpt/resources/codex')
 resolved=which(codex)
 add('codex',bool(resolved),'Codex executable: '+codex+'. Set CODEX_BIN to an executable path if needed.')
 try:
  result=run(['/usr/bin/python3','-c',PROBE],capture_output=True,text=True,timeout=10,env=env)
  if result.returncode:raise ValueError('System Python dependency probe failed: '+result.stderr[-500:])
  data=json.loads(result.stdout)
  for name in ('Gio','Gst','xkbcommon'):add(name,data.get(name) is True,'System dependency '+name+' must be available.')
  for name in ('pipewiresrc','queue','videorate','videoconvert','pngenc','appsink'):
   add('gstreamer:'+name,data.get('elements',{}).get(name) is True,'Required GStreamer element: '+name)
  add('Atspi',data.get('Atspi') is True,'Optional accessibility target guards; visual control remains available.',required=False)
 except (OSError,ValueError,subprocess.TimeoutExpired) as error:add('python-dependencies',False,str(error))
 return {'ready':all(c['ok'] for c in checks if c['required']),'checks':checks,'changed_settings':False,'requested_sharing':False}

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--json',action='store_true');args=parser.parse_args();result=check_environment()
 if args.json:print(json.dumps(result,indent=2))
 else:
  for c in result['checks']:
   print(('OK' if c['ok'] else 'MISSING' if c['required'] else 'OPTIONAL')+': '+c['name']+' — '+c['detail'])
  print('Environment checks passed; portal checks still run before sharing.' if result['ready'] else 'Installation stopped before changes. Resolve the missing requirements and retry.')
 return 0 if result['ready'] else 1
if __name__=='__main__':sys.exit(main())
