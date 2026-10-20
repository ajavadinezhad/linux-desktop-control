"""Intermediate key snapshots must pause, not terminate a valid tool transition."""
import unittest
import test_two_finger_pause as two

PREFIX = two.PREFIX.replace('static int physical_key,', 'static int snapshots[4],snapshot_count,snapshot_index,expire_snapshot;static int physical_key,')
PREFIX = PREFIX.replace('memset(p,0,(KEY_MAX+8)/8);', r'''
memset(p,0,(KEY_MAX+8)/8);
if(snapshot_count){
 int mask=snapshots[snapshot_index<snapshot_count?snapshot_index:snapshot_count-1];
 snapshot_index++;
 if(mask&1)((unsigned char*)p)[BTN_TOUCH/8]|=1U<<(BTN_TOUCH%8);
 if(mask&2)((unsigned char*)p)[BTN_TOOL_FINGER/8]|=1U<<(BTN_TOOL_FINGER%8);
 if(mask&4)((unsigned char*)p)[BTN_TOOL_DOUBLETAP/8]|=1U<<(BTN_TOOL_DOUBLETAP%8);
 if(mask&8)((unsigned char*)p)[BTN_TOOL_TRIPLETAP/8]|=1U<<(BTN_TOOL_TRIPLETAP%8);
 if(mask&16)((unsigned char*)p)[KEY_LEFTSHIFT/8]|=1U<<(KEY_LEFTSHIFT%8);
 if(mask&32)((unsigned char*)p)[BTN_SIDE/8]|=1U<<(BTN_SIDE%8);
 if(expire_snapshot)fixture_now+=1000;
 return 0;
}
''', 1)

def run(body):
 two.fixture.run('int main(void){(void)click_setup;(void)one;(void)two;(void)lift;'+body+'return 0;}', PREFIX+two.PREP)

class SnapshotRetryTests(unittest.TestCase):
 def test_real_held_state_accepts_intermediate_one_to_two_and_two_to_one(self):
  for transient, final in ((1,5),(7,3),(1,0)):
   with self.subTest(transient=transient,final=final):
    run(f'''click_setup(1);snapshots[0]={transient};snapshots[1]={final};snapshot_count=2;
 assert(held_state()==0);assert(snapshot_index==2);assert(pointer_yielded&&click_pause_sticky&&!pointer_quiet);
 assert(!motion_notices&&!observation_touchpad_motion_after_arm&&!passive_motion_epoch);
 snapshots[0]=0;snapshot_count=1;snapshot_index=0;assert(held_state()==0);
 advance(1499);assert(pointer_yield_tick(fixture_now)==0);assert(!pointer_quiet);
 advance(1);assert(pointer_yield_tick(fixture_now)==0);assert(command("RESUMECLICK_1")==0);''')
 def test_persistent_contradiction_is_bounded_and_fatal(self):
  run('click_setup(1);snapshots[0]=7;snapshot_count=1;assert(held_state()==-1);assert(snapshot_index==3);assert(pointer_yielded&&!pointer_quiet);')
 def test_deadline_stops_retry_and_default_mode_never_retries(self):
  run('click_setup(1);snapshots[0]=1;snapshots[1]=5;snapshot_count=2;expire_snapshot=1;assert(held_state()==-1);assert(snapshot_index==1);')
  run('setup(1);armed=true;arm_time=fixture_now;snapshots[0]=1;snapshots[1]=3;snapshot_count=2;assert(held_state()==-1);assert(snapshot_index==1);')
 def test_unsupported_three_contact_bitmap_remains_terminal(self):
  for mask in (9,17,33):
   with self.subTest(mask=mask):
    run(f'click_setup(1);snapshots[0]={mask};snapshots[1]=0;snapshot_count=2;assert(held_state()==-1);assert(snapshot_index==1);')
