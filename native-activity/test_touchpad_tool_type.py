"""Validated MT tool metadata is private; palm contact retains inert pause."""
import unittest
import test_multi_contact_pause as fixture

def run(body):
 fixture.run('multi_setup();touchpad_limits[0]=(struct tp_limits){0,1000,0,1000,true,0,3,65535};'+body)

class TouchpadToolTypeTests(unittest.TestCase):
 def test_four_finger_metadata_and_repeated_finger_type_are_not_motion(self):
  run(r'''for(int i=0;i<4;i++){assert(event(EV_ABS,ABS_MT_SLOT,i)==0);assert(event(EV_ABS,ABS_MT_TRACKING_ID,10+i)==0);
 assert(event(EV_ABS,ABS_MT_TOOL_TYPE,MT_TOOL_FINGER)==0);assert(event(EV_ABS,ABS_MT_TOOL_TYPE,MT_TOOL_FINGER)==0);}
 assert(event(EV_KEY,BTN_TOUCH,1)==0);assert(event(EV_KEY,BTN_TOOL_QUADTAP,1)==0);assert(event(EV_SYN,SYN_REPORT,0)==0);
 assert(pointer_yielded&&click_pause_sticky&&!motion_notices&&!observation_touchpad_motion_after_arm&&!calibration_touchpad_motion);''')
 def test_palm_without_pointer_bits_stays_busy_until_tracking_release(self):
  run(r'''assert(event(EV_ABS,ABS_MT_TRACKING_ID,10)==0);assert(event(EV_ABS,ABS_MT_TOOL_TYPE,MT_TOOL_PALM)==0);
 assert(event(EV_SYN,SYN_REPORT,0)==0);assert(pointer_yielded&&click_pause_sticky&&tp_active(&touchpad_states[0]));
 for(int i=0;i<20;i++){advance(100);assert(event(EV_SYN,SYN_REPORT,0)==0);assert(pointer_yield_tick(fixture_now)==0);assert(!pointer_quiet);}
 assert(command("RESUMECLICK_1")==-1);assert(event(EV_ABS,ABS_MT_TRACKING_ID,-1)==0);
 advance(2000);assert(pointer_yield_tick(fixture_now)==0);assert(!pointer_quiet); /* unfinished lift frame */
 assert(event(EV_SYN,SYN_REPORT,0)==0);advance(1500);assert(pointer_yield_tick(fixture_now)==0);assert(command("RESUMECLICK_1")==0);
 assert(!motion_notices&&!observation_touchpad_motion_after_arm&&!passive_motion_epoch);''')
 def test_palm_to_finger_remains_sticky_and_mixed_contacts_are_bounded(self):
  run(r'''assert(event(EV_ABS,ABS_MT_TRACKING_ID,10)==0);assert(event(EV_ABS,ABS_MT_TOOL_TYPE,MT_TOOL_PALM)==0);
 assert(event(EV_ABS,ABS_MT_SLOT,1)==0);assert(event(EV_ABS,ABS_MT_TRACKING_ID,11)==0);assert(event(EV_ABS,ABS_MT_TOOL_TYPE,MT_TOOL_FINGER)==0);
 assert(event(EV_KEY,BTN_TOUCH,1)==0);assert(event(EV_KEY,BTN_TOOL_FINGER,1)==0);assert(event(EV_SYN,SYN_REPORT,0)==0);
 assert(event(EV_ABS,ABS_MT_SLOT,0)==0);assert(event(EV_ABS,ABS_MT_TRACKING_ID,-1)==0);assert(event(EV_SYN,SYN_REPORT,0)==0);
 assert(!tp_palm_active(&touchpad_states[0])&&touchpad_states[0].gesture_sticky);
 advance(2000);assert(pointer_yield_tick(fixture_now)==0);assert(!pointer_quiet);
 assert(event(EV_ABS,ABS_MT_SLOT,1)==0);assert(event(EV_ABS,ABS_MT_TOOL_TYPE,MT_TOOL_PALM)==0);assert(event(EV_SYN,SYN_REPORT,0)==0);
 assert(event(EV_ABS,ABS_MT_TOOL_TYPE,MT_TOOL_FINGER)==0);assert(event(EV_SYN,SYN_REPORT,0)==0);
 assert(event(EV_ABS,ABS_X,100)==0);assert(event(EV_ABS,ABS_Y,100)==0);assert(event(EV_SYN,SYN_REPORT,0)==0);
 assert(event(EV_ABS,ABS_X,200)==0);assert(event(EV_SYN,SYN_REPORT,0)==0);assert(!motion_notices&&!observation_touchpad_motion_after_arm);
 assert(event(EV_ABS,ABS_MT_TRACKING_ID,-1)==0);assert(event(EV_KEY,BTN_TOUCH,0)==0);assert(event(EV_KEY,BTN_TOOL_FINGER,0)==0);
 assert(event(EV_SYN,SYN_REPORT,0)==0);advance(1500);assert(pointer_yield_tick(fixture_now)==0);assert(command("RESUMECLICK_1")==0);''')
 def test_palm_touch_without_tool_snapshot_remains_inert_not_quiet(self):
  prefix=fixture.PREFIX.replace('if(physical_contacts){','if(physical_contacts==99){((unsigned char*)p)[BTN_TOUCH/8]|=1U<<(BTN_TOUCH%8);return 0;}if(physical_contacts){')
  fixture.fixture.fixture.run('int main(void){(void)contacts;(void)click_setup;(void)one;(void)two;(void)lift;multi_setup();touchpad_limits[0]=(struct tp_limits){0,1000,0,1000,true,0,3,65535};'+r'''
 assert(event(EV_ABS,ABS_MT_TRACKING_ID,10)==0);assert(event(EV_ABS,ABS_MT_TOOL_TYPE,MT_TOOL_PALM)==0);
 assert(event(EV_KEY,BTN_TOUCH,1)==0);assert(event(EV_SYN,SYN_REPORT,0)==0);physical_contacts=99;
 assert(held_state()==0);advance(2000);assert(pointer_yield_tick(fixture_now)==0);assert(!pointer_quiet&&!motion_notices);return 0;}''',prefix+fixture.PREP)
 def test_pen_unknown_inactive_nonmt_and_unnegotiated_palm_are_rejected(self):
  for value in (1,3,10,-1):
   with self.subTest(value=value):run(f'assert(event(EV_ABS,ABS_MT_TRACKING_ID,10)==0);assert(event(EV_ABS,ABS_MT_TOOL_TYPE,{value})==-1);assert(touchpad_terminal_reject==TP_REJECT_VALUE);')
  run('assert(event(EV_ABS,ABS_MT_TOOL_TYPE,MT_TOOL_FINGER)==-1);assert(touchpad_terminal_reject==TP_REJECT_CONTACT_SLOT);')
  run('touchpad_limits[0].mt=false;assert(event(EV_ABS,ABS_MT_TOOL_TYPE,MT_TOOL_FINGER)==-1);')
  run('multi_contact_mode=false;assert(event(EV_ABS,ABS_MT_TRACKING_ID,10)==0);assert(event(EV_ABS,ABS_MT_TOOL_TYPE,MT_TOOL_PALM)==-1);')
 def test_palm_exception_cannot_invent_contacts_or_accept_bad_frames(self):
  for setup in ('assert(event(EV_KEY,BTN_TOUCH,1)==0);assert(event(EV_KEY,BTN_TOOL_QUADTAP,1)==0);',
                'assert(event(EV_KEY,BTN_TOOL_FINGER,1)==0);'):
   run('assert(event(EV_ABS,ABS_MT_TRACKING_ID,10)==0);assert(event(EV_ABS,ABS_MT_TOOL_TYPE,MT_TOOL_PALM)==0);'+setup+'assert(event(EV_SYN,SYN_REPORT,0)==-1);')
