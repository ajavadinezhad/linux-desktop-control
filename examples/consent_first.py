"""Consent-first GUI entry point. No shell/app subprocesses, D-Bus launches or focus changes.

The caller must actually inspect the returned pixels. App launch is through the
observed Shell GUI, one explicit focus transition, followed by fresh inspection.
"""
import json
class ObservedDesktop:
 def __init__(self,client,observation):self.client=client;self.observation=observation;self.used=False
 def open_launcher(self):
  if self.used:raise RuntimeError('Do not replay a launch; inspect a new observation')
  self.used=True
  return self.client.call('desktop_action',{'window_observation_id':self.observation,'focus_transition':True,'action':{'type':'keys','keys':['Super']}})
def begin(client,inspect_pixels):
 result=client.call('desktop_start',{})
 try:
  content=result.get('content',[]);metadata=next(json.loads(c['text']) for c in content if c.get('type')=='text')
  if result.get('isError') or metadata.get('active') is not True or not any(c.get('type')=='image' for c in content):raise RuntimeError('Consent did not produce an active observed desktop')
  window=metadata.get('window_observation',{})
  if window.get('available') is not True or not window.get('observation_id'):raise RuntimeError('No guarded foreground observation')
  if inspect_pixels(result) is not True:raise RuntimeError('Fresh pixels have not been inspected')
  return ObservedDesktop(client,window['observation_id'])
 except Exception:
  client.call('desktop_close',{});raise
