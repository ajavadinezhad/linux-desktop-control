"""Foreground-context fences, not physical-input provenance or atomic dispatch."""
import math
class WindowGuard:
 def __init__(self,bridge,baseline,cancel):
  self.bridge=bridge;self.baseline=self.signature(baseline);self.cancel=cancel;self.failed=False
  if not baseline.get('available'):raise RuntimeError('Foreground observation unavailable')
 @staticmethod
 def signature(context):
  rect=context.get('rect');epoch=context.get('epoch');identity=context.get('window_id');kind=context.get('kind')
  if context.get('available') is not True or not isinstance(epoch,int) or isinstance(epoch,bool) or epoch<0 or not isinstance(identity,str) or not identity or kind not in ('window','overview') or not isinstance(rect,list) or len(rect)!=4 or not all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in rect) or rect[2]<=0 or rect[3]<=0:raise RuntimeError('Invalid foreground observation')
  return (identity,epoch,tuple(rect),kind)
 def fail(self):
  self.failed=True;self.cancel();raise RuntimeError('Foreground target changed or became unavailable; remaining input cancelled. Session must close; wait for explicit readiness.')
 def check(self):
  if self.failed:self.fail()
  try:current=self.signature(self.bridge.context())
  except Exception:self.fail()
  if current!=self.baseline:self.fail()
 def changed(self,epoch):
  # No D-Bus cleanup on this signal thread; cancellation wakes the input worker.
  if epoch>self.baseline[1]:self.failed=True;self.cancel()
 def validate_points(self,action,offset=(0,0)):
  x,y,w,h=self.baseline[2]
  def inside(px,py):
   if not (x<=px+offset[0]<x+w and y<=py+offset[1]<y+h):raise ValueError('Input point is outside the observed foreground window')
  def visit(step):
   if 'x' in step and 'y' in step:inside(step['x'],step['y'])
   if isinstance(step.get('focus'),dict):inside(step['focus'].get('x'),step['focus'].get('y'))
   for point in step.get('path',[]):inside(*point)
   for child in step.get('steps',[]):visit(child)
  visit(action)

def validate_transition(action):
 # A deliberate focus change is one gesture with no remaining batch or text.
 if action.get('type')=='click' and action.get('button','left')=='left' and action.get('count',1)==1 and 'focus' not in action:return
 if action.get('type')=='keys' and 'focus' not in action:
  keys=action.get('keys')
  if keys in (['Super'],['Super_L'],['Return'],['Enter'],['Ctrl','s'],['Ctrl','Shift','s'],['Ctrl','o']):return
 raise ValueError('A focus transition permits only one left click or launcher/Return or Ctrl+s/Ctrl+Shift+s/Ctrl+o chord; no text, drag, scroll or sequence')

def pointer_local(context,geometry):
 pointer=context.get('pointer')
 if not isinstance(geometry,dict) or not all(isinstance(geometry.get(k),(int,float)) and not isinstance(geometry.get(k),bool) and math.isfinite(geometry[k]) for k in ('x','y','width','height')) or geometry['width']<=0 or geometry['height']<=0:raise RuntimeError('Selected monitor mapping unavailable; pointer input refused')
 if not isinstance(pointer,(list,tuple)) or len(pointer)!=2 or not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in pointer):raise RuntimeError('Fresh system pointer position unavailable; pointer input refused')
 x,y=pointer[0]-geometry['x'],pointer[1]-geometry['y']
 if not (0<=x<geometry['width'] and 0<=y<geometry['height']):raise RuntimeError('System pointer is outside the shared monitor; pointer input refused')
 return (x,y)
