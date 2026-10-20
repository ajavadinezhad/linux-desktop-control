"""Recognized two-finger contact is a click-aware intervention, never motion proof."""
import unittest
import test_click_pause as click
import test_passive_startup as fixture

PREFIX=click.PREFIX.replace('static int physical_key,physical_contact,physical_button;',
                           'static int physical_key,physical_contact,physical_button,physical_two;')
PREFIX=PREFIX.replace('if(physical_contact){', 'if(physical_two){((unsigned char*)p)[BTN_TOUCH/8]|=1U<<(BTN_TOUCH%8);((unsigned char*)p)[BTN_TOOL_DOUBLETAP/8]|=1U<<(BTN_TOOL_DOUBLETAP%8);}\nif(physical_contact){')
PREP=click.PREP+r'''
static void one(void){
 assert(event(EV_KEY,BTN_TOUCH,1)==0);assert(event(EV_KEY,BTN_TOOL_FINGER,1)==0);
 assert(event(EV_ABS,ABS_X,100)==0);assert(event(EV_ABS,ABS_Y,100)==0);
 assert(event(EV_SYN,SYN_REPORT,0)==0);
}
static void two(void){
 assert(event(EV_KEY,BTN_TOOL_FINGER,0)==0);assert(event(EV_KEY,BTN_TOOL_DOUBLETAP,1)==0);
 assert(event(EV_SYN,SYN_REPORT,0)==0);
}
static void lift(void){
 assert(event(EV_KEY,BTN_TOOL_DOUBLETAP,0)==0);assert(event(EV_KEY,BTN_TOUCH,0)==0);
 assert(event(EV_SYN,SYN_REPORT,0)==0);
}
'''
def run(body):
 fixture.run(body.replace('int main(void){','int main(void){(void)click_setup;(void)one;(void)two;(void)lift;',1),PREFIX+PREP)

class TwoFingerPauseTests(unittest.TestCase):
 def test_stationary_two_fingers_hold_pause_until_lift_and_quiet(self):
  run(r'''int main(void){click_setup(1);passive_selected=passive_armed=true;
 one();two();assert(pointer_yielded&&click_pause_sticky&&click_notices==1&&yield_notices==1);
 for(int i=0;i<20;i++){advance(100);assert(event(EV_SYN,SYN_REPORT,0)==0);assert(pointer_yield_tick(fixture_now)==0);assert(!pointer_quiet);}
 assert(!motion_notices&&!observation_touchpad_motion_after_arm&&!calibration_touchpad_motion&&!passive_motion_epoch);
 assert(command("RESUMECLICK_1")==-1);lift();advance(1499);assert(pointer_yield_tick(fixture_now)==0);assert(!pointer_quiet);
 advance(1);assert(pointer_yield_tick(fixture_now)==0);assert(pointer_quiet);
 assert(command("RESUME_1")==-1);assert(command("RESUMECLICK_1")==0);assert(command("RESUMECLICK_1")==-1);return 0;}''')
 def test_direct_two_contact_then_single_remains_intervention_until_all_lift(self):
  run(r'''int main(void){click_setup(1);passive_selected=passive_armed=true;
 assert(event(EV_KEY,BTN_TOOL_DOUBLETAP,1)==0);assert(event(EV_KEY,BTN_TOUCH,1)==0);
 assert(event(EV_ABS,ABS_X,100)==0);assert(event(EV_ABS,ABS_Y,100)==0);assert(event(EV_SYN,SYN_REPORT,0)==0);
 assert(event(EV_KEY,BTN_TOOL_DOUBLETAP,0)==0);assert(event(EV_KEY,BTN_TOOL_FINGER,1)==0);assert(event(EV_SYN,SYN_REPORT,0)==0);
 assert(event(EV_ABS,ABS_X,400)==0);assert(event(EV_ABS,ABS_Y,400)==0);assert(event(EV_SYN,SYN_REPORT,0)==0);
 assert(event(EV_ABS,ABS_X,500)==0);assert(event(EV_SYN,SYN_REPORT,0)==0);
 assert(click_pause_sticky&&motion_notices==0&&!observation_touchpad_motion_after_arm);
 advance(2000);assert(pointer_yield_tick(fixture_now)==0);assert(!pointer_quiet);
 assert(event(EV_KEY,BTN_TOOL_FINGER,0)==0);assert(event(EV_KEY,BTN_TOUCH,0)==0);
 advance(2000);assert(pointer_yield_tick(fixture_now)==0);assert(!pointer_quiet); /* incomplete final frame */
 assert(event(EV_SYN,SYN_REPORT,0)==0);advance(1500);assert(pointer_yield_tick(fixture_now)==0);assert(command("RESUMECLICK_1")==0);return 0;}''')
 def test_snapshot_only_two_finger_contact_stays_busy_without_motion_credit(self):
  run(r'''int main(void){click_setup(1);passive_selected=passive_armed=true;
 physical_two=1;assert(held_state()==0);assert(touchpad_busy()&&click_pause_sticky&&pointer_yielded);
 advance(3000);assert(pointer_yield_tick(fixture_now)==0);assert(!pointer_quiet);
 physical_two=0;physical_contact=1;assert(held_state()==0);assert(touchpad_busy());
 assert(!motion_notices&&!observation_touchpad_motion_after_arm&&!passive_motion_epoch);
 physical_contact=0;assert(held_state()==0);advance(1500);assert(pointer_yield_tick(fixture_now)==0);
 assert(command("RESUMECLICK_1")==0);return 0;}''')
 def test_invalid_or_default_gestures_remain_refused(self):
  run(r'''int main(void){setup(1);armed=true;arm_time=fixture_now;
 assert(event(EV_KEY,BTN_TOOL_DOUBLETAP,1)==-1);assert(!click_pause_sticky);return 0;}''')
  for body in [
   'one();assert(event(EV_KEY,BTN_TOOL_DOUBLETAP,1)==0);assert(event(EV_SYN,SYN_REPORT,0)==-1);',
   'one();two();assert(event(EV_KEY,BTN_TOOL_TRIPLETAP,1)==-1);',
   'one();two();assert(event(EV_SYN,SYN_DROPPED,0)==-1);',
   'physical_two=physical_contact=1;assert(held_state()==-1);',
   'one();two();assert(event(EV_REL,REL_WHEEL,1)==-1);',
  ]:
   with self.subTest(body=body):run('int main(void){click_setup(1);'+body+'return 0;}')
 def test_two_slots_in_either_event_order_and_duplicate_or_third_ids_refused(self):
  for tool_first in (False,True):
   body=r'''int main(void){click_setup(1);passive_selected=passive_armed=true;
 touchpad_limits[0]=(struct tp_limits){0,1000,0,1000,true,0,3,65535};
 assert(event(EV_ABS,ABS_MT_TRACKING_ID,10)==0);one();
 ORDER
 assert(event(EV_SYN,SYN_REPORT,0)==0);assert(click_pause_sticky&&!motion_notices);
 assert(event(EV_ABS,ABS_MT_POSITION_X,200)==0);assert(event(EV_ABS,ABS_MT_POSITION_Y,200)==0);
 assert(event(EV_SYN,SYN_REPORT,0)==0);assert(!observation_touchpad_motion_after_arm);
 assert(event(EV_ABS,ABS_MT_TRACKING_ID,-1)==0);assert(event(EV_KEY,BTN_TOOL_DOUBLETAP,0)==0);
 assert(event(EV_KEY,BTN_TOOL_FINGER,1)==0);assert(event(EV_SYN,SYN_REPORT,0)==0);
 assert(event(EV_ABS,ABS_MT_SLOT,0)==0);assert(event(EV_ABS,ABS_MT_TRACKING_ID,-1)==0);
 assert(event(EV_KEY,BTN_TOOL_FINGER,0)==0);assert(event(EV_KEY,BTN_TOUCH,0)==0);assert(event(EV_SYN,SYN_REPORT,0)==0);
 advance(1500);assert(pointer_yield_tick(fixture_now)==0);assert(command("RESUMECLICK_1")==0);return 0;}'''
   slot='assert(event(EV_ABS,ABS_MT_SLOT,1)==0);assert(event(EV_ABS,ABS_MT_TRACKING_ID,11)==0);'
   tool='assert(event(EV_KEY,BTN_TOOL_FINGER,0)==0);assert(event(EV_KEY,BTN_TOOL_DOUBLETAP,1)==0);'
   with self.subTest(tool_first=tool_first):run(body.replace('ORDER',tool+slot if tool_first else slot+tool))
  for code in [
   'assert(event(EV_ABS,ABS_MT_SLOT,1)==0);assert(event(EV_ABS,ABS_MT_TRACKING_ID,10)==-1);',
   'assert(event(EV_ABS,ABS_MT_SLOT,1)==0);assert(event(EV_ABS,ABS_MT_TRACKING_ID,11)==0);assert(event(EV_ABS,ABS_MT_SLOT,2)==0);assert(event(EV_ABS,ABS_MT_TRACKING_ID,12)==-1);',
  ]:
   run('int main(void){click_setup(1);touchpad_limits[0]=(struct tp_limits){0,1000,0,1000,true,0,3,65535};assert(event(EV_ABS,ABS_MT_TRACKING_ID,10)==0);'+code+'return 0;}')
 def test_stale_epoch_queued_input_lease_and_heartbeat_still_refuse_resume(self):
  for failure in ('pending=1;', 'fixture_now=session_time+120000;heartbeat=fixture_now;', 'fixture_now=heartbeat+1000;'):
   run(r'''int main(void){click_setup(1);one();two();lift();advance(1500);assert(pointer_yield_tick(fixture_now)==0);
 assert(command("RESUMECLICK_0")==-1);FAILURE
 assert(command("RESUMECLICK_1")==-1);assert(pointer_yielded&&click_pause_sticky);return 0;}'''.replace('FAILURE',failure))
