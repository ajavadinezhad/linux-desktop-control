"""Opt-in click pause/quiet handshake against real C, fake input only."""
import unittest
import test_passive_startup as fixture
PREFIX=fixture.PREFIX.replace('static int physical_key,physical_contact;','static int physical_key,physical_contact,physical_button;')
PREFIX=PREFIX.replace('if(physical_key)', 'if(physical_button)((unsigned char*)p)[physical_button/8]|=1U<<(physical_button%8);\nif(physical_key)')
PREFIX=PREFIX.replace('static int motion_notices;', 'static int motion_notices;static int click_notices,yield_notices;')
PREFIX=PREFIX.replace('if(n>=7&&!memcmp(p,"MOTION_",7))motion_notices++;','if(n>=8&&!memcmp(p,"CLICKED_",8))click_notices++;if(n>=8&&!memcmp(p,"YIELDED_",8))yield_notices++;if(n>=7&&!memcmp(p,"MOTION_",7))motion_notices++;')
PREP=r'''
static void click_setup(int pad){
 setup(pad);assert(command("CLICKPAUSE1")==0);assert(!strcmp(reply,"CLICKPAUSE1_OK\n"));
 armed=true;arm_time=fixture_now;
}
'''
def run(body):
 fixture.run(body.replace('int main(void){','int main(void){(void)click_setup;',1),PREFIX+PREP)

class ClickPauseTests(unittest.TestCase):
 def test_supported_clicks_pause_release_quiet_and_click_aware_resume(self):
  for button in ['BTN_LEFT','BTN_RIGHT','BTN_MIDDLE']:
   with self.subTest(button=button):run(r'''int main(void){
 click_setup(0);assert(event(EV_KEY,BUTTON,1)==0);assert(pointer_yielded&&click_pause_sticky&&pointer_epoch==1);
 assert(!strcmp(reply,"CLICKED_1\n")&&click_notices==1&&yield_notices==1);
 assert(command("RESUMECLICK_1")==-1);assert(event(EV_KEY,BUTTON,0)==0);
 advance(1499);assert(pointer_yield_tick(fixture_now)==0);assert(!pointer_quiet);
 advance(1);assert(pointer_yield_tick(fixture_now)==0);assert(pointer_quiet);
 assert(command("RESUME_1")==-1);assert(command("RESUMECLICK_1")==0);
 assert(!strcmp(reply,"ARMED_1\n")&&!click_pause_sticky&&!pointer_yielded);
 assert(command("RESUMECLICK_1")==-1);return 0;}'''.replace('BUTTON',button))
 def test_snapshot_held_supported_click_pauses_but_keyboard_and_other_buttons_still_terminal(self):
  for button in ['BTN_LEFT','BTN_RIGHT','BTN_MIDDLE']:
   with self.subTest(button=button):run(r'''int main(void){
 click_setup(0);physical_button=BUTTON;assert(held_state()==1);assert(held_intervention()==0);
 assert(pointer_yielded&&click_pause_sticky&&click_notices==1);
 advance(2000);assert(pointer_yield_tick(fixture_now)==0);assert(!pointer_quiet);
 assert(held_state()==1);assert(held_intervention()==0);assert(click_notices==1);
 physical_button=0;advance(1500);assert(pointer_yield_tick(fixture_now)==0);assert(pointer_quiet);
 assert(command("RESUMECLICK_1")==0);return 0;}'''.replace('BUTTON',button))
  run(r'''int main(void){click_setup(0);physical_key=1;physical_button=BTN_LEFT;
 assert(held_state()==1&&held_other_input&&held_admitted_click);assert(held_intervention()==1);assert(!pointer_yielded);
 physical_key=0;physical_button=BTN_SIDE;assert(held_state()==1);assert(held_intervention()==1);return 0;}''')
 def test_click_during_motion_pause_same_epoch_and_sticky_across_new_motion_epoch(self):
  run(r'''int main(void){click_setup(0);
 assert(event(EV_REL,REL_X,2)==0);assert(pointer_epoch==1&&!click_pause_sticky);
 assert(event(EV_KEY,BTN_LEFT,1)==0);assert(pointer_epoch==1&&click_notices==1&&yield_notices==1);
 assert(event(EV_KEY,BTN_LEFT,0)==0);advance(1500);assert(pointer_yield_tick(fixture_now)==0);assert(pointer_quiet);
 assert(event(EV_REL,REL_Y,1)==0);assert(pointer_epoch==2&&click_pause_sticky&&click_notices==2&&yield_notices==2);
 advance(1500);assert(pointer_yield_tick(fixture_now)==0);assert(command("RESUME_2")==-1);
 assert(command("RESUMECLICK_1")==-1);assert(command("RESUMECLICK_2")==0);return 0;}''')
 def test_default_close_legacy_mode_and_strict_negotiation(self):
  run(r'''int main(void){setup(0);armed=true;arm_time=fixture_now;
 assert(command("CLICKPAUSE1")==-1);assert(event(EV_KEY,BTN_LEFT,1)==1);assert(!pointer_yielded);
 armed=false;assert(command("CLICKPAUSE1")==0);assert(command("CLICKPAUSE1")==-1);
 armed=true;assert(command("RESUMECLICK_1")==-1);return 0;}''')
  run(r'''int main(void){device_count=1;heartbeat=session_time=fixture_now;
 assert(command("CLICKPAUSE1")==-1);assert(command("MODEYIELD")==0);assert(command("CLICKPAUSE1")==-1);return 0;}''')
 def test_keyboard_wheel_other_button_and_dropped_unknown_remain_terminal(self):
  for kind,code,val,result in [('EV_KEY','KEY_A',1,1),('EV_KEY','BTN_SIDE',1,1),('EV_KEY','BTN_LEFT',2,1),('EV_REL','REL_WHEEL',1,1),('EV_SYN','SYN_DROPPED',0,-1),('EV_SW','SW_LID',1,1)]:
   with self.subTest(code=code):run('int main(void){click_setup(0);assert(event('+kind+','+code+','+str(val)+')=='+str(result)+');assert(click_notices==0);return 0;}')
 def test_touchpad_buttons_pause_without_unsupported_gesture_or_motion_credit(self):
  run(r'''int main(void){click_setup(1);passive_selected=passive_armed=true;
 assert(event(EV_KEY,BTN_LEFT,1)==0);assert(event(EV_KEY,BTN_LEFT,0)==0);
 assert(event(EV_SYN,SYN_REPORT,0)==0);assert(click_notices==1&&motion_notices==0);
 advance(1500);assert(pointer_yield_tick(fixture_now)==0);assert(command("RESUMECLICK_1")==0);return 0;}''')
 def test_auth_wait_keeps_click_activity_private_and_does_not_gain_sticky_pause(self):
  run(r'''int main(void){setup(0);assert(command("CLICKPAUSE1")==0);assert(command("AUTHMODE1")==0);armed=true;arm_time=fixture_now;
 assert(command("AUTHWAIT_1")==0);assert(event(EV_KEY,BTN_LEFT,1)==0);assert(event(EV_KEY,BTN_LEFT,0)==0);
 assert(event(EV_SYN,SYN_REPORT,0)==0);assert(click_notices==0&&!click_pause_sticky&&!pointer_yielded);
 assert(command("AUTHEND_1")==0);advance(1500);assert(auth_tick(fixture_now)==0);assert(armed);
 assert(event(EV_KEY,BTN_LEFT,1)==0);assert(click_notices==1);return 0;}''')
 def test_expired_lease_held_input_or_pending_queue_never_resume(self):
  run(r'''int main(void){click_setup(0);assert(event(EV_KEY,BTN_RIGHT,1)==0);assert(event(EV_KEY,BTN_RIGHT,0)==0);
 advance(1500);assert(pointer_yield_tick(fixture_now)==0);physical_button=BTN_RIGHT;
 assert(command("RESUMECLICK_1")==-1);physical_button=0;pending=1;
 assert(command("RESUMECLICK_1")==-1);pending=0;
 fixture_now=session_time+120000;heartbeat=fixture_now;assert(command("RESUMECLICK_1")==-1);
 assert(click_pause_sticky&&pointer_yielded);return 0;}''')

 def test_click_resume_refuses_input_queued_during_final_session_watch(self):
  import pathlib
  source=pathlib.Path(__file__).with_name('broker.c').read_text()
  source=source.replace('#include "touchpad.h"','#include "'+str(pathlib.Path(__file__).with_name('touchpad.h'))+'"')
  source=source.replace('#include "confinement.h"',"""
static int inject_watch;
static bool session_watch_ok(void){if(inject_watch==1)pending=1;if(inject_watch==2)fixture_now=121000;return true;}
static void session_watch_stop_io(void){}
static int session_watch_fd(void){return 20;}
static int confine_collector(void){return 0;}
""")
  marker='#include "'+str(pathlib.Path(__file__).with_name('broker.c'))+'"'
  prefix=PREFIX.replace(marker,'#define LDC_NATIVE_WATCH 1\n'+source)+PREP
  for injection in (1,2):
   body=r"""int main(void){(void)click_setup;
 click_setup(0);assert(event(EV_KEY,BTN_LEFT,1)==0);assert(event(EV_KEY,BTN_LEFT,0)==0);
 advance(1500);assert(pointer_yield_tick(fixture_now)==0);assert(pointer_quiet);strcpy(reply,"UNCHANGED");
 inject_watch=INJECTION;assert(command("RESUMECLICK_1")==-1);
 assert(click_pause_sticky&&pointer_yielded&&!strcmp(reply,"UNCHANGED"));return 0;}
""".replace('INJECTION',str(injection))
   with self.subTest(injection=injection):fixture.run(body,prefix)
