"""Pure foreground task checkpointing; never schedules, captures or replays input.

A running executor must feed status and explicitly record its fresh observation.
A toolbar click cannot wake an idle model: another user turn is then required.
Only caller-supplied nonsecret summaries belong here; no credentials/action payloads.
"""
from dataclasses import dataclass,asdict

@dataclass(frozen=True)
class Checkpoint:
    intent:str
    completed_summary:str
    next_step:str
    result_id:str|None
    epoch:int

class TaskContinuation:
    def __init__(self):
        self.checkpoint=None
        self.observed_epoch=None
        self.observation_id=None
        self.reconciled_result=None
        self.terminal=False

    def save(self,intent,completed_summary,next_step,result_id,epoch):
        for value in (intent,completed_summary,next_step):
            if not isinstance(value,str) or len(value)>1000:raise ValueError('Use bounded nonsecret summaries only')
        if not intent.strip() or not next_step.strip():raise ValueError('Keep the intent and remaining step explicit')
        if result_id is not None and (not isinstance(result_id,str) or len(result_id)>128):raise ValueError('Invalid bounded result ID')
        if not isinstance(epoch,int) or isinstance(epoch,bool) or epoch<0:raise ValueError('Invalid epoch')
        self.checkpoint=Checkpoint(intent,completed_summary,next_step,result_id,epoch)
        return asdict(self.checkpoint)

    def record_observation(self,epoch,observation_id=None):
        """Call only after inspecting a fresh assistant-visible image at this epoch."""
        if not isinstance(epoch,int) or isinstance(epoch,bool) or epoch<0:raise ValueError('Invalid epoch')
        if observation_id is not None and (not isinstance(observation_id,str) or not observation_id or len(observation_id)>128):raise ValueError('Invalid observation ID')
        self.observed_epoch=epoch
        self.observation_id=observation_id

    def mark_reconciled(self,result_id):
        """Caller has checked which partial effects actually happened; never retries."""
        if not isinstance(result_id,str) or not result_id or len(result_id)>128:raise ValueError('A bounded result ID is required')
        self.reconciled_result=result_id

    def classify(self,status):
        state=status.get('control_state','stopped')
        epoch=status.get('control_epoch')
        base={'capture':False,'input':False,'automatic_retry':False}
        if self.terminal or state=='stopped':
            self.terminal=True
            return dict(base,decision='end',reason='Stopped; never automatically start another session')
        if state in ('paused','pausing','stopping'):
            self.observed_epoch=None;self.observation_id=None
            return dict(base,decision='wait',reason='Human has control; status only',pending=True)
        if state in ('starting','resuming'):
            self.observed_epoch=None;self.observation_id=None
            return dict(base,decision='wait',reason='Wait for personal GNOME consent',pending=True)
        if state!='active':return dict(base,decision='wait',reason='Unknown control state',pending=True)
        recovery=status.get('recovery') or {}
        required=recovery.get('inspection_required') is True
        token=recovery.get('observation_id')
        if (status.get('ready_to_observe') or self.observed_epoch!=epoch or
            (required and (not token or token!=self.observation_id))):
            return dict(base,decision='observe',capture=True,reason='Inspect a fresh screen before planning; acknowledge its recovery token',pending=True)
        result=recovery.get('last_result') or {}
        if result.get('outcome')=='effects_uncertain' and (not result.get('result_id') or self.reconciled_result!=result['result_id']):
            return dict(base,decision='reconcile',reason='Determine completed effects from the fresh app state before planning',result_id=result.get('result_id'),pending=True)
        if self.checkpoint is None:return dict(base,decision='wait',reason='No task intent checkpoint; consult the conversation',pending=True)
        return dict(base,decision='plan_from_current_state',pending=True,
                    checkpoint=asdict(self.checkpoint),
                    recovery_observation_id=self.observation_id if required else None,
                    reason='Continue remaining intent using current UI; construct a new action, never replay a cached action')
