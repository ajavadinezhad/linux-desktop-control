"""Opt-in keyboard intervention retains consent; no key payload crosses protocol."""
import unittest
import test_two_finger_pause as fixture

PREP=fixture.PREP+r'''
static void key_setup(void){
 setup(1);assert(command("CLICKPAUSE1")==0);assert(command("KEYPAUSE1")==0);
 assert(!strcmp(reply,"KEYPAUSE1_OK\n"));armed=true;arm_time=fixture_now;
}
static void sync_frame(void){assert(event(EV_SYN,SYN_REPORT,0)==0);}
'''
def run(body):
 fixture.fixture.run('int main(void){(void)key_setup;(void)sync_frame;(void)click_setup;(void)one;(void)two;(void)lift;'+body+'return 0;}',fixture.PREFIX+PREP)

class KeyPauseTests(unittest.TestCase):
 def test_alt_tab_press_repeat_and_release_wait_for_quiet_and_frame(self):
  run(r'''key_setup();assert(event(EV_MSC,MSC_SCAN,56)==0);assert(event(EV_KEY,KEY_LEFTALT,1)==0);sync_frame();
 assert(pointer_yielded&&click_pause_sticky&&!pointer_quiet&&click_notices==1);
 assert(event(EV_MSC,MSC_SCAN,15)==0);assert(event(EV_KEY,KEY_TAB,1)==0);assert(event(EV_KEY,KEY_TAB,2)==0);sync_frame();
 physical_key=1;advance(2000);assert(pointer_yield_tick(fixture_now)==0);assert(!pointer_quiet);
 physical_key=0;assert(event(EV_KEY,KEY_TAB,0)==0);assert(event(EV_KEY,KEY_LEFTALT,0)==0);
 advance(2000);assert(pointer_yield_tick(fixture_now)==0);assert(!pointer_quiet); /* release frame unfinished */
 sync_frame();assert(pointer_yield_tick(fixture_now)==0);assert(pointer_quiet);
 assert(command("RESUME_1")==-1);assert(command("RESUMECLICK_1")==0);
 assert(!motion_notices&&!observation_touchpad_motion_after_arm&&!passive_motion_epoch);''')
 def test_held_snapshot_keeps_pause_until_released(self):
  run(r'''key_setup();physical_key=1;assert(held_state()==1);assert(held_intervention()==0);
 advance(2000);assert(pointer_yield_tick(fixture_now)==0);assert(!pointer_quiet);
 physical_key=0;advance(1499);assert(pointer_yield_tick(fixture_now)==0);assert(!pointer_quiet);
 advance(1);assert(pointer_yield_tick(fixture_now)==0);assert(command("RESUMECLICK_1")==0);''')
 def test_scan_metadata_pauses_and_partial_frame_blocks_quiet(self):
  run(r'''key_setup();assert(event(EV_MSC,MSC_SCAN,123456)==0);
 assert(pointer_yielded&&click_pause_sticky&&!motion_notices);advance(2000);
 assert(pointer_yield_tick(fixture_now)==0);assert(!pointer_quiet);assert(command("RESUMECLICK_1")==-1);
 sync_frame();assert(pointer_yield_tick(fixture_now)==0);assert(pointer_quiet);assert(command("RESUMECLICK_1")==0);''')
  run('key_setup();assert(event(EV_MSC,MSC_SERIAL,1)!=0);')
  run('click_setup(1);assert(event(EV_MSC,MSC_SCAN,1)!=0);')
  run('key_setup();arm_time=fixture_now+1;assert(event(EV_MSC,MSC_SCAN,1)==-1);')
 def test_default_and_negotiation_are_strict(self):
  run('setup(1);assert(command("KEYPAUSE1")==-1);assert(command("CLICKPAUSE1")==0);assert(command("KEYPAUSE1")==0);assert(command("KEYPAUSE1")==-1);armed=true;assert(command("KEYPAUSE1")==-1);')
  run('click_setup(1);assert(event(EV_KEY,KEY_A,1)!=0);')
 def test_malformed_stale_power_scroll_and_dropped_remain_terminal(self):
  for action in ('event(EV_KEY,KEY_A,3)','event(EV_KEY,KEY_POWER,1)','event(EV_REL,REL_WHEEL,1)','event(EV_SYN,SYN_DROPPED,0)'):
   with self.subTest(action=action):run('key_setup();assert('+action+'!=0);')
  run('key_setup();arm_time=fixture_now+1;assert(event(EV_KEY,KEY_A,1)==-1);')
 def test_keyboard_on_unadmitted_pointer_device_is_not_accepted(self):
  run('key_setup();device_categories[0]=CATEGORY_POINTER;assert(event(EV_KEY,KEY_A,1)!=0);physical_key=1;assert(held_state()==1);assert(held_intervention()!=0);')
 def test_new_input_after_quiet_blocks_resume_and_close_remains_terminal(self):
  run(r'''key_setup();assert(event(EV_KEY,KEY_A,1)==0);assert(event(EV_KEY,KEY_A,0)==0);sync_frame();advance(1500);
 assert(pointer_yield_tick(fixture_now)==0);assert(pointer_quiet);physical_key=1;
 assert(command("RESUMECLICK_1")==-1);assert(command("CLOSE")==2);''')
