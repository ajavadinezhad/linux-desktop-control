"""Expected-authentication helper state, fake I/O only; never real input."""
import unittest
import test_passive_startup as fixture

PREP=r'''
static void auth_setup(int pad){
 setup(pad);assert(command("AUTHMODE1")==0);assert(!strcmp(reply,"AUTHMODE1_OK\n"));
 armed=true;arm_time=fixture_now;
}
'''
def run(body,prefix=fixture.PREFIX):
 fixture.run(body.replace('int main(void){','int main(void){(void)auth_setup;',1),prefix+PREP)

class AuthWaitTests(unittest.TestCase):
 def test_private_activity_and_fresh_quiet_rearm_no_coverage_credit(self):
  run(r'''int main(void){
 auth_setup(0);assert(command("AUTHWAIT_1")==0);assert(!strcmp(reply,"AUTHWAIT_1_OK\n"));
 assert(auth_waiting&&!armed&&!calibration_seen);
 assert(event(EV_MSC,MSC_SCAN,123)==0);assert(event(EV_KEY,KEY_A,1)==0);physical_key=1;assert(auth_tick(fixture_now)==0);
 assert(event(EV_KEY,KEY_A,0)==0);physical_key=0;
 assert(event(EV_REL,REL_X,2)==0);assert(event(EV_KEY,BTN_LEFT,1)==0);assert(event(EV_KEY,BTN_LEFT,0)==0);
 assert(!observation_primary_after_arm&&!observation_relative_after_arm&&!pointer_yielded&&motion_notices==0);
 assert(event(EV_SYN,SYN_REPORT,0)==0);
 assert(command("AUTHEND_1")==0);advance(1499);assert(auth_tick(fixture_now)==0);assert(!armed);
 advance(1);assert(auth_tick(fixture_now)==0);assert(armed&&!auth_waiting);assert(!strcmp(reply,"AUTHREADY_1\n"));
 assert(arm_time==fixture_now&&!calibration_seen&&!calibration_pointer_stream&&motion_notices==0);
 assert(event(EV_KEY,KEY_A,1)==1);return 0;
}''')
 def test_held_keys_and_touchpad_contact_prevent_rearm(self):
  run(r'''int main(void){
 auth_setup(1);assert(command("AUTHWAIT_1")==0);assert(command("AUTHEND_1")==0);
 physical_key=1;advance(1500);assert(auth_tick(fixture_now)==0);assert(!armed);
 physical_key=0;physical_contact=1;advance(1500);assert(auth_tick(fixture_now)==0);assert(!armed);
 physical_contact=0;advance(1499);assert(auth_tick(fixture_now)==0);assert(!armed);
 advance(1);assert(auth_tick(fixture_now)==0);assert(armed);return 0;
}''')
 def test_protocol_strict_epochs_duplicates_and_no_implicit_selection(self):
  run(r'''int main(void){
 setup(0);armed=true;assert(command("AUTHWAIT_1")==-1);armed=false;
 assert(command("AUTHMODE1")==0);assert(command("AUTHMODE1")==-1);assert(command("AUTHWAIT_1")==-1);armed=true;
 assert(command("AUTHWAIT_0")==-1);assert(command("AUTHWAIT_01")==-1);assert(command("AUTHWAIT_2")==-1);
 assert(command("AUTHWAIT_1")==0);assert(command("AUTHWAIT_1")==-1);assert(command("RESUME_1")==-1);
 assert(command("ARM")==-1);assert(command("ARM_PASSIVE")==-1);assert(command("LEASE_600")==-1);
 assert(command("AUTHEND_2")==-1);assert(command("AUTHEND_01")==-1);
 assert(command("AUTHEND_1")==0);assert(command("AUTHEND_1")==-1);
 advance(1500);assert(auth_tick(fixture_now)==0);assert(armed);
 assert(command("AUTHWAIT_1")==-1);assert(command("AUTHWAIT_2")==0);return 0;
}''')
 def test_unknown_stale_and_dropped_input_remain_faults(self):
  for record in [('EV_SYN','SYN_DROPPED'),('EV_SW','SW_LID'),('EV_REL','REL_Z'),('EV_ABS','ABS_X'),('EV_KEY','KEY_POWER')]:
   with self.subTest(record=record):
    run('int main(void){auth_setup(0);assert(command("AUTHWAIT_1")==0);assert(event('+record[0]+','+record[1]+',1)==-1);return 0;}')
  run(r'''int main(void){auth_setup(0);assert(command("AUTHWAIT_1")==0);
 fixture_event=(struct input_event){.time={0,0},.type=EV_KEY,.code=KEY_A,.value=1};have_event=1;assert(drain(4)==-1);return 0;}''')
 def test_touchpad_activity_is_private_and_pending_frame_blocks(self):
  run(r'''int main(void){auth_setup(1);assert(command("AUTHWAIT_1")==0);
 assert(event(EV_KEY,BTN_TOUCH,1)==0);assert(event(EV_KEY,BTN_TOOL_FINGER,1)==0);
 assert(event(EV_ABS,ABS_X,100)==0);assert(event(EV_ABS,ABS_Y,100)==0);assert(event(EV_SYN,SYN_REPORT,0)==0);
 assert(event(EV_ABS,ABS_X,200)==0);assert(event(EV_SYN,SYN_REPORT,0)==0);assert(motion_notices==0&&!pointer_yielded);
 assert(event(EV_KEY,BTN_LEFT,1)==0);assert(event(EV_KEY,BTN_LEFT,0)==0);
 assert(event(EV_KEY,BTN_TOUCH,0)==0);assert(event(EV_KEY,BTN_TOOL_FINGER,0)==0);assert(event(EV_SYN,SYN_REPORT,0)==0);
 assert(command("AUTHEND_1")==0);advance(1500);assert(event(EV_ABS,ABS_PRESSURE,0)==0);
 assert(auth_tick(fixture_now)==0);assert(!armed);assert(event(EV_SYN,SYN_REPORT,0)==0);
 assert(auth_tick(fixture_now)==0);assert(armed&&motion_notices==0);return 0;}''')
 def test_pending_topology_owner_heartbeat_and_original_lease_stay_terminal(self):
  for body in [
   'advance(1000);heartbeat=fixture_now-1000;assert(auth_tick(fixture_now)==-1);assert(collector_phase==17);',
   'fixture_now=session_time+120000;heartbeat=fixture_now;assert(auth_tick(fixture_now)==-1);assert(collector_phase==18);',
   'fixture_now=auth_deadline;heartbeat=fixture_now;assert(auth_tick(fixture_now)==-1);',
   'assert(command("AUTHEND_1")==0);advance(1500);pending=2;assert(auth_tick(fixture_now)==-1);',
   'assert(command("AUTHEND_1")==0);advance(1500);pending=4;assert(auth_tick(fixture_now)==-1);',
  ]:
   with self.subTest(body=body):run('int main(void){auth_setup(0);assert(command("AUTHWAIT_1")==0);'+body+'assert(!armed);return 0;}')
 def test_close_is_available_and_heartbeat_does_not_extend_wait(self):
  run(r'''int main(void){auth_setup(0);assert(command("AUTHWAIT_1")==0);long long original=auth_deadline;
 advance(100);assert(command("HB")==0);assert(auth_deadline==original);assert(command("CLOSE")==2);return 0;}''')
 def test_late_boundary_query_cannot_rearm(self):
  prefix=fixture.PREFIX.replace('static int fixture_poll(struct pollfd *fds,nfds_t n,int timeout){','static int fixture_poll(struct pollfd *fds,nfds_t n,int timeout){fixture_now+=2;')
  run(r'''int main(void){auth_setup(0);assert(command("AUTHWAIT_1")==0);assert(command("AUTHEND_1")==0);
 fixture_now=auth_deadline-1;heartbeat=fixture_now;assert(auth_tick(fixture_now)==-1);assert(!armed);return 0;}''',prefix)
 def test_session_revocation_inside_final_held_query_never_acknowledges(self):
  import pathlib,subprocess,tempfile
  source=pathlib.Path(__file__).with_name('broker.c').read_text()
  tick=source[source.index('static int auth_tick('):source.index('static unsigned auth_parse_epoch(')]
  prefix=r'''
#include <assert.h>
#include <stdbool.h>
#include <poll.h>
#define LDC_NATIVE_WATCH 1
#define MAX_DEVICES 64
#define CALIBRATION_QUIET_MS 1500
static bool auth_waiting=true,auth_ending=true,armed,auth_frame_pending[MAX_DEVICES];
static bool pointer_yielded,pointer_quiet,healthy=true,ack;
static unsigned passive_motion_epoch;
static int collector_phase,device_count=1,held_calls;
static long long auth_started_at=1000,auth_deadline=6000,auth_last_activity=1000,heartbeat=3000,session_time=1000,arm_time;
static long long now_ms(void){return 3000;}
static int expiry_phase(long long a,long long b,long long c){(void)a;(void)b;(void)c;return 0;}
static int drain(int fd){(void)fd;return 0;}
static int held_state(void){if(++held_calls==2)healthy=false;return 0;}
static bool touchpad_contact_active(void){return false;}
static bool touchpad_busy(void){return false;}
static bool session_watch_ok(void){return healthy;}
static int fixture_poll(struct pollfd *p,nfds_t n,int timeout){(void)timeout;for(nfds_t i=0;i<n;i++)p[i].revents=0;return 0;}
#define poll fixture_poll
static int auth_reply(const char *s){(void)s;ack=true;return 0;}
'''
  with tempfile.TemporaryDirectory(prefix='ldc-auth-session-') as directory:
   p=pathlib.Path(directory);(p/'fixture.c').write_text(prefix+tick+'int main(void){assert(auth_tick(3000)==-1);assert(held_calls==2&&!healthy&&!armed&&!ack);return 0;}')
   subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',str(p/'fixture.c'),'-o',str(p/'fixture')],check=True)
   subprocess.run([str(p/'fixture')],check=True,timeout=3)
