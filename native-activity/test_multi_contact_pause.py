"""Explicitly negotiated 1..4 contact pause, never gesture or motion authority."""
import unittest
import test_two_finger_pause as fixture

PREFIX=fixture.PREFIX.replace('static int physical_key,', 'static int physical_contacts, snapshot_step, snapshot_script, snapshot_masks[3];static int physical_key,')
PREFIX=PREFIX.replace('if(physical_two){',r'''
if(snapshot_script){
 int mask=snapshot_masks[snapshot_step<2?snapshot_step:2];snapshot_step++;
 if(mask&1)((unsigned char*)p)[BTN_TOUCH/8]|=1U<<(BTN_TOUCH%8);
 if(mask&2)((unsigned char*)p)[BTN_TOOL_FINGER/8]|=1U<<(BTN_TOOL_FINGER%8);
 if(mask&4)((unsigned char*)p)[BTN_TOOL_DOUBLETAP/8]|=1U<<(BTN_TOOL_DOUBLETAP%8);
 if(mask&8)((unsigned char*)p)[BTN_TOOL_TRIPLETAP/8]|=1U<<(BTN_TOOL_TRIPLETAP%8);
 if(mask&16)((unsigned char*)p)[BTN_TOOL_QUADTAP/8]|=1U<<(BTN_TOOL_QUADTAP%8);
 return 0;
}
if(physical_contacts){
 int tool=physical_contacts==1?BTN_TOOL_FINGER:(physical_contacts==2?BTN_TOOL_DOUBLETAP:(physical_contacts==3?BTN_TOOL_TRIPLETAP:(physical_contacts==4?BTN_TOOL_QUADTAP:BTN_TOOL_QUINTTAP)));
 ((unsigned char*)p)[BTN_TOUCH/8]|=1U<<(BTN_TOUCH%8);((unsigned char*)p)[tool/8]|=1U<<(tool%8);
}
if(physical_two){''',1)
PREP=fixture.PREP+r'''
static int previous;
static int tool(int n){return n==1?BTN_TOOL_FINGER:(n==2?BTN_TOOL_DOUBLETAP:(n==3?BTN_TOOL_TRIPLETAP:BTN_TOOL_QUADTAP));}
static void multi_setup(void){setup(1);assert(command("CLICKPAUSE1")==0);assert(command("MULTICONTACT1")==0);assert(!strcmp(reply,"MULTICONTACT1_OK\n"));armed=true;arm_time=fixture_now;}
static void contacts(int n){
 if(previous)assert(event(EV_KEY,tool(previous),0)==0);
 if(!previous&&n)assert(event(EV_KEY,BTN_TOUCH,1)==0);
 if(n)assert(event(EV_KEY,tool(n),1)==0);
 if(previous&&!n)assert(event(EV_KEY,BTN_TOUCH,0)==0);
 previous=n;assert(event(EV_SYN,SYN_REPORT,0)==0);
}
'''
def run(body):
 fixture.fixture.run('int main(void){(void)multi_setup;(void)contacts;(void)click_setup;(void)one;(void)two;(void)lift;'+body+'return 0;}',PREFIX+PREP)

class MultiContactTests(unittest.TestCase):
 def test_stationary_transition_four_to_one_holds_until_all_lift(self):
  run(r'''multi_setup();contacts(1);contacts(4);contacts(3);contacts(2);contacts(1);
 for(int i=0;i<20;i++){advance(100);assert(event(EV_SYN,SYN_REPORT,0)==0);assert(pointer_yield_tick(fixture_now)==0);assert(!pointer_quiet);}
 assert(pointer_yielded&&click_pause_sticky&&click_notices==1&&!motion_notices&&!observation_touchpad_motion_after_arm&&!passive_motion_epoch);
 contacts(0);advance(1499);assert(pointer_yield_tick(fixture_now)==0);assert(!pointer_quiet);
 advance(1);assert(pointer_yield_tick(fixture_now)==0);assert(command("RESUMECLICK_1")==0);''')
 def test_mt_four_slots_in_both_tool_event_orders(self):
  for tool_first in (False,True):
   add='for(int i=0;i<4;i++){assert(event(EV_ABS,ABS_MT_SLOT,i)==0);assert(event(EV_ABS,ABS_MT_TRACKING_ID,100+i)==0);}'
   bits='assert(event(EV_KEY,BTN_TOUCH,1)==0);assert(event(EV_KEY,BTN_TOOL_QUADTAP,1)==0);'
   run(r'''multi_setup();touchpad_limits[0]=(struct tp_limits){0,1000,0,1000,true,0,3,65535};ORDER
 assert(event(EV_SYN,SYN_REPORT,0)==0);assert(pointer_yielded&&click_pause_sticky);
 for(int n=3;n>=0;n--){assert(event(EV_ABS,ABS_MT_SLOT,n)==0);assert(event(EV_ABS,ABS_MT_TRACKING_ID,-1)==0);
 assert(event(EV_KEY,tool(n+1),0)==0);if(n)assert(event(EV_KEY,tool(n),1)==0);else assert(event(EV_KEY,BTN_TOUCH,0)==0);
 advance(2000);assert(pointer_yield_tick(fixture_now)==0);assert(!pointer_quiet);
 assert(event(EV_SYN,SYN_REPORT,0)==0);}
 advance(1500);assert(pointer_yield_tick(fixture_now)==0);assert(command("RESUMECLICK_1")==0);assert(!motion_notices);'''.replace('ORDER',bits+add if tool_first else add+bits))
 def test_snapshot_counts_and_ambiguous_reread_never_prove_motion(self):
  run(r'''multi_setup();for(int n=4;n>0;n--){physical_contacts=n;assert(held_state()==0);advance(2000);assert(pointer_yield_tick(fixture_now)==0);assert(!pointer_quiet);}
 physical_contacts=0;assert(held_state()==0);advance(1500);assert(pointer_yield_tick(fixture_now)==0);assert(command("RESUMECLICK_1")==0);assert(!motion_notices&&!passive_motion_epoch);''')
  for ambiguous,stable in ((1,9),(1,17),(25,9),(11,3)):
   with self.subTest(ambiguous=ambiguous,stable=stable):
    run(f'multi_setup();snapshot_script=1;snapshot_masks[0]={ambiguous};snapshot_masks[1]={stable};assert(held_state()==0);assert(snapshot_step==2);assert(pointer_yielded&&click_pause_sticky&&!pointer_quiet&&!motion_notices);')
  run('multi_setup();snapshot_script=1;snapshot_masks[0]=snapshot_masks[1]=snapshot_masks[2]=25;assert(held_state()==-1);assert(snapshot_step==3);')
 def test_five_duplicate_tracking_unsupported_scroll_and_bad_frames_fail(self):
  for body in ('physical_contacts=5;assert(held_state()!=0);assert(held_intervention()!=0);',
               'contacts(4);assert(event(EV_KEY,BTN_TOOL_QUINTTAP,1)==-1);',
               'contacts(4);assert(event(EV_REL,REL_WHEEL,1)==-1);',
               'contacts(4);assert(event(EV_SYN,SYN_DROPPED,0)==-1);',
               'contacts(4);assert(event(EV_KEY,BTN_TOOL_TRIPLETAP,1)==0);assert(event(EV_SYN,SYN_REPORT,0)==-1);'):
   with self.subTest(body=body):run('multi_setup();'+body)
  run(r'''multi_setup();touchpad_limits[0]=(struct tp_limits){0,1000,0,1000,true,0,5,65535};
 for(int i=0;i<4;i++){assert(event(EV_ABS,ABS_MT_SLOT,i)==0);assert(event(EV_ABS,ABS_MT_TRACKING_ID,i)==0);}
 assert(event(EV_ABS,ABS_MT_SLOT,4)==0);assert(event(EV_ABS,ABS_MT_TRACKING_ID,4)==-1);''')
 def test_negotiation_default_legacy_and_expiry_remain_strict(self):
  run('setup(1);assert(command("MULTICONTACT1")==-1);assert(command("CLICKPAUSE1")==0);assert(command("MULTICONTACT1")==0);assert(command("MULTICONTACT1")==-1);armed=true;assert(command("MULTICONTACT1")==-1);')
  run('click_setup(1);assert(event(EV_KEY,BTN_TOOL_TRIPLETAP,1)==-1);')
  run('setup(0);assert(command("CLICKPAUSE1")==0);assert(command("MULTICONTACT1")==-1);')
  run('multi_setup();contacts(4);contacts(0);advance(1500);assert(pointer_yield_tick(fixture_now)==0);pending=1;assert(command("RESUMECLICK_1")==-1);assert(command("CLOSE")==2);')
