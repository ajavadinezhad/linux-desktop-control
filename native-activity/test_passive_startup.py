"""Explicit supervised arming: fake I/O against the real collector only."""
import ast
import pathlib
import subprocess
import tempfile
import unittest
from test_pointer_yield import PREFIX

PREFIX = PREFIX.replace("static int have_event, pending, closed_mask;",
                        "static int have_event, pending, closed_mask;static int physical_key,physical_contact;")
PREFIX = PREFIX.replace("static char reply[128];", "static char reply[128];static int motion_notices;")
PREFIX = PREFIX.replace("memset(p,0,(KEY_MAX+8)/8);return 0;", r'''
memset(p,0,(KEY_MAX+8)/8);
if(physical_key)((unsigned char*)p)[KEY_LEFTSHIFT/8]|=1U<<(KEY_LEFTSHIFT%8);
if(physical_contact){((unsigned char*)p)[BTN_TOUCH/8]|=1U<<(BTN_TOUCH%8);((unsigned char*)p)[BTN_TOOL_FINGER/8]|=1U<<(BTN_TOOL_FINGER%8);}
return 0;''')
PREFIX = PREFIX.replace("assert(n<sizeof reply);memcpy", "if(n>=7&&!memcmp(p,\"MOTION_\",7))motion_notices++;assert(n<sizeof reply);memcpy")
PREFIX += r'''
static int event(unsigned type,unsigned code,int value){
 fixture_event=(struct input_event){.time={fixture_now/1000,(fixture_now%1000)*1000},.type=type,.code=code,.value=value};
 have_event=1;return drain(4);
}
static void setup(int pad){
 device_count=1;device_categories[0]=CATEGORY_KEYBOARD|CATEGORY_POINTER;
 heartbeat=session_time=fixture_now;
 if(pad){device_touchpad[0]=true;touchpad_limits[0]=(struct tp_limits){0,1000,0,1000,false,0,0,0};}
 assert(command(pad?"MODEYIELD3":"MODEYIELD2")==0);
}
static void advance(int ms){fixture_now+=ms;heartbeat=fixture_now;}
'''


def run(body, prefix=PREFIX):
    body = body.replace("int main(void){", "int main(void){(void)advance;(void)setup;(void)event;", 1)
    with tempfile.TemporaryDirectory(prefix="ldc-passive-") as temporary:
        root = pathlib.Path(temporary)
        (root / "fixture.c").write_text(prefix + body)
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                        str(root / "fixture.c"), "-o", str(root / "fixture")], check=True)
        subprocess.run([str(root / "fixture")], check=True, timeout=5)


class PassiveStartupTests(unittest.TestCase):
    def test_delayed_authentication_records_are_discarded_before_tracking_fence(self):
        run(r'''int main(void){
 setup(1);physical_contact=1;assert(command("ARM_PASSIVE")==0);assert(!passive_tracking);
 fixture_event=(struct input_event){.time={0,0},.type=EV_KEY,.code=BTN_TOUCH,.value=0};
 have_event=1;assert(drain(4)==0);
 fixture_event.code=BTN_TOOL_FINGER;have_event=1;assert(drain(4)==0);
 fixture_event.type=EV_ABS;fixture_event.code=ABS_PRESSURE;fixture_event.value=0;
 have_event=1;assert(drain(4)==0);
 fixture_event.type=EV_SYN;fixture_event.code=SYN_REPORT;
 have_event=1;assert(drain(4)==0);
 physical_contact=0;assert(passive_tick(fixture_now)==0);assert(passive_tracking);
 assert(!armed&&!calibration_seen&&!calibration_pointer_stream&&motion_notices==0);
 /* Once a clean released boundary starts tracking, old queued input cannot
  * establish a new baseline or silently change what readiness means. */
 fixture_event.time.tv_sec=0;fixture_event.time.tv_usec=0;
 have_event=1;assert(drain(4)==-1);assert(!armed);
 return 0;
}''')

    def test_partial_idle_frame_blocks_arming_without_restarting_quiet(self):
        run(r'''int main(void){
 setup(1);physical_contact=1;assert(command("ARM_PASSIVE")==0);
 assert(event(EV_ABS,ABS_PRESSURE,0)==0);physical_contact=0;
 assert(passive_tick(fixture_now)==0);assert(!passive_tracking);
 advance(100);assert(event(EV_SYN,SYN_REPORT,0)==0);
 assert(passive_tick(fixture_now)==0);assert(passive_tracking);
 long long quiet_started=passive_last_activity;
 advance(1490);assert(event(EV_ABS,ABS_PRESSURE,0)==0);
 assert(passive_tick(fixture_now)==0);assert(!armed&&passive_last_activity==quiet_started);
 advance(10);assert(passive_tick(fixture_now)==0);assert(!armed);
 assert(event(EV_SYN,SYN_REPORT,0)==0);assert(passive_tick(fixture_now)==0);
 assert(armed&&passive_armed&&motion_notices==0);
 return 0;
}''')

    def test_expiry_rechecked_after_boundary_queries(self):
        prefix = PREFIX.replace("static int motion_notices;", "static int motion_notices;static int poll_cost;")
        prefix = prefix.replace("static int fixture_poll(struct pollfd *fds,nfds_t n,int timeout){",
                                "static int fixture_poll(struct pollfd *fds,nfds_t n,int timeout){fixture_now+=poll_cost;")
        cases = [
            # Quiet is otherwise complete, but the bounded settle window ends
            # inside its query. No PASSIVE_ARMED may be published afterward.
            'setup(0);assert(command("ARM_PASSIVE")==0);fixture_now=passive_deadline-1;heartbeat=fixture_now;poll_cost=2;assert(passive_tick(fixture_now)==-1);',
            'setup(0);fixture_now=session_time+119000;heartbeat=fixture_now;assert(command("ARM_PASSIVE")==0);fixture_now=session_time+119999;heartbeat=fixture_now;poll_cost=2;assert(passive_tick(fixture_now)==-1);assert(collector_phase==18);',
            'setup(0);assert(command("ARM_PASSIVE")==0);fixture_now=heartbeat+999;poll_cost=2;assert(passive_tick(fixture_now)==-1);assert(collector_phase==17);',
        ]
        for case in cases:
            with self.subTest(case=case):
                run('int main(void){' + case + 'assert(!armed&&!passive_armed);return 0;}', prefix)

    def test_real_collector_passive_ack_and_motion_epoch_protocol(self):
        native = pathlib.Path(__file__).resolve().parent
        tree = ast.parse((native / "test_broker.py").read_text())
        method = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                      and node.name == "test_full_collector_calibration_report_closes_fake_sources_without_arm")
        source = next(ast.literal_eval(node.value) for node in method.body
                      if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                      and isinstance(node.value.value, str))
        source = source.replace("#undef main\nstatic void line", r'''#undef main
static void emit(int fd,unsigned type,unsigned code,int value){
 long long now=now_ms();struct input_event e={.time={now/1000,(now%1000)*1000},.type=type,.code=code,.value=value};
 assert(write(fd,&e,sizeof e)==sizeof e);
}
static void line''')
        source = source.replace("device_categories[0]=CATEGORY_KEYBOARD|CATEGORY_POINTER;", r'''
device_categories[0]=CATEGORY_KEYBOARD|CATEGORY_POINTER;
device_touchpad[0]=true;touchpad_limits[0]=(struct tp_limits){0,1000,0,1000,false,0,0,0};''')
        begin = source.index('    line(control[1],"READY')
        end = source.index('    signal(SIGPIPE', begin)
        sequence = r'''
    line(control[1],"READY\n");assert(write(control[1],"MODEYIELD3\n",11)==11);line(control[1],"MODEYIELD3_OK\n");
    assert(write(control[1],"ARM_PASSIVE\n",12)==12);
    for(int i=0;i<14;i++){usleep(100000);assert(write(control[1],"HB\n",3)==3);line(control[1],"ALIVE\n");}
    usleep(200000);line(control[1],"PASSIVE_ARMED\n");
    emit(stream[1],EV_KEY,BTN_TOUCH,1);emit(stream[1],EV_KEY,BTN_TOOL_FINGER,1);
    line(control[1],"YIELDED_1\n");
    emit(stream[1],EV_ABS,ABS_X,100);emit(stream[1],EV_ABS,ABS_Y,100);emit(stream[1],EV_SYN,SYN_REPORT,0);
    emit(stream[1],EV_ABS,ABS_X,140);emit(stream[1],EV_SYN,SYN_REPORT,0);line(control[1],"MOTION_1\n");
    emit(stream[1],EV_ABS,ABS_Y,150);emit(stream[1],EV_SYN,SYN_REPORT,0);
    emit(stream[1],EV_KEY,BTN_TOUCH,0);emit(stream[1],EV_KEY,BTN_TOOL_FINGER,0);emit(stream[1],EV_SYN,SYN_REPORT,0);
    assert(write(control[1],"HB\n",3)==3);line(control[1],"ALIVE\n");
    for(int i=0;i<14;i++){usleep(100000);assert(write(control[1],"HB\n",3)==3);line(control[1],"ALIVE\n");}
    usleep(200000);line(control[1],"QUIET_1\n");assert(write(control[1],"RESUME_1\n",9)==9);line(control[1],"ARMED_1\n");
    assert(write(control[1],"CLOSE\n",6)==6);line(control[1],"OBS_TPAD_0111\n");
    struct input_event event={0};
'''
        source = source[:begin] + sequence + source[end:]
        with tempfile.TemporaryDirectory(prefix="ldc-passive-loop-") as temporary:
            directory = pathlib.Path(temporary)
            (directory / "fixture.c").write_text(source)
            subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I", str(native),
                            str(directory / "fixture.c"), "-o", str(directory / "fixture")], check=True)
            subprocess.run([str(directory / "fixture")], check=True, timeout=8)

    def test_released_quiet_arms_without_challenge_and_motion_is_epoch_scoped(self):
        run(r'''int main(void){
 setup(0);physical_key=1;assert(command("ARM_PASSIVE")==0);
 assert(passive_pending&&!passive_tracking&&!armed&&!calibrating&&!calibrated);
 assert(command("ARM_PASSIVE")==-1);assert(command("CALIBRATE")==-1);
 assert(command("ARM")==-1);assert(command("LEASE_600")==-1);assert(command("MODEYIELD3")==-1);
 advance(100);physical_key=0;assert(event(EV_KEY,KEY_LEFTSHIFT,0)==0);
 assert(passive_tick(fixture_now)==0);assert(passive_tracking&&!armed);
 advance(1499);assert(passive_tick(fixture_now)==0);assert(!armed);
 advance(1);assert(passive_tick(fixture_now)==0);
 assert(armed&&passive_armed&&!passive_pending&&!calibrated&&!calibrating&&!calibration_seen&&!calibration_pointer_stream);
 assert(!strcmp(reply,"PASSIVE_ARMED\n"));assert(motion_notices==0);
 advance(1);assert(event(EV_REL,REL_X,1)==0);
 assert(pointer_yielded&&pointer_epoch==1&&passive_motion_epoch==1&&motion_notices==1);
 assert(!strcmp(reply,"MOTION_1\n"));
 advance(1);assert(event(EV_REL,REL_Y,2)==0);assert(motion_notices==1);
 advance(1500);assert(pointer_yield_tick(fixture_now)==0);assert(pointer_quiet);
 assert(command("RESUME_1")==0);assert(passive_motion_epoch==0);
 advance(1);assert(event(EV_REL,REL_X,1)==0);assert(motion_notices==2);
 assert(pointer_epoch==2&&passive_motion_epoch==2&&!strcmp(reply,"MOTION_2\n"));
 assert(event(EV_KEY,KEY_LEFTSHIFT,1)==1); /* physical key still terminal */
 return 0;
}''')

    def test_touchpad_idle_frames_do_not_fake_motion_and_contact_is_not_coverage(self):
        run(r'''int main(void){
 setup(1);physical_contact=1;assert(command("ARM_PASSIVE")==0);
 advance(500);assert(passive_tick(fixture_now)==0);assert(!passive_tracking&&!armed);
 physical_contact=0;assert(event(EV_KEY,BTN_TOUCH,0)==0);assert(event(EV_KEY,BTN_TOOL_FINGER,0)==0);
 assert(event(EV_SYN,SYN_REPORT,0)==0);assert(passive_tick(fixture_now)==0);assert(passive_tracking);
 for(int i=0;i<15;i++){
  advance(100);assert(event(EV_MSC,MSC_TIMESTAMP,100)==0);
  assert(event(EV_ABS,ABS_PRESSURE,0)==0);assert(event(EV_SYN,SYN_REPORT,0)==0);
  assert(passive_tick(fixture_now)==0);
 }
 assert(armed&&passive_armed&&!calibrated&&!calibration_touchpad_motion&&motion_notices==0);
 advance(1);assert(event(EV_KEY,BTN_TOUCH,1)==0);assert(event(EV_KEY,BTN_TOOL_FINGER,1)==0);
 assert(pointer_yielded&&pointer_epoch==1&&motion_notices==0);
 advance(2000);assert(pointer_yield_tick(fixture_now)==0);assert(!pointer_quiet);
 assert(event(EV_KEY,BTN_TOUCH,0)==0);assert(event(EV_KEY,BTN_TOOL_FINGER,0)==0);
 assert(event(EV_SYN,SYN_REPORT,0)==0);advance(1500);
 assert(pointer_yield_tick(fixture_now)==0);assert(pointer_quiet&&motion_notices==0);
 assert(command("RESUME_1")==0); /* explicit manual resume, not coverage */
 advance(1);event(EV_KEY,BTN_TOUCH,1);event(EV_KEY,BTN_TOOL_FINGER,1);
 event(EV_ABS,ABS_X,100);event(EV_ABS,ABS_Y,100);event(EV_SYN,SYN_REPORT,0);
 assert(motion_notices==0);
 event(EV_ABS,ABS_X,120);event(EV_SYN,SYN_REPORT,0);
 assert(pointer_epoch==2&&motion_notices==1&&!strcmp(reply,"MOTION_2\n"));
 event(EV_ABS,ABS_Y,150);event(EV_SYN,SYN_REPORT,0);assert(motion_notices==1);
 device_touchpad[0]=false;assert(event(EV_REL,REL_X,1)==1); /* source isolation */
 return 0;
}''')

    def test_default_challenge_quiet_survives_idle_touchpad_metadata(self):
        run(r'''int main(void){
 setup(1);assert(command("CALIBRATE")==0);calibration_seen=CATEGORY_KEYBOARD;advance(1);
 event(EV_KEY,BTN_TOUCH,1);event(EV_KEY,BTN_TOOL_FINGER,1);
 event(EV_ABS,ABS_X,100);event(EV_ABS,ABS_Y,100);event(EV_SYN,SYN_REPORT,0);
 event(EV_ABS,ABS_X,120);event(EV_SYN,SYN_REPORT,0);
 assert(calibration_touchpad_motion);advance(2000);
 assert(calibration_tick(fixture_now)==0);assert(!calibrated); /* held contact */
 event(EV_KEY,BTN_TOUCH,0);event(EV_KEY,BTN_TOOL_FINGER,0);event(EV_SYN,SYN_REPORT,0);
 for(int i=0;i<15;i++){
  advance(100);event(EV_MSC,MSC_TIMESTAMP,1);event(EV_ABS,ABS_PRESSURE,0);event(EV_SYN,SYN_REPORT,0);
  assert(calibration_tick(fixture_now)==0);
 }
 assert(calibrated&&!passive_selected&&!passive_armed&&motion_notices==0);
 return 0;
}''')

    def test_selection_expiry_faults_and_no_fallback(self):
        cases = [
            'device_count=1;heartbeat=session_time=fixture_now;assert(command("ARM_PASSIVE")==-1);',
            'device_count=1;heartbeat=session_time=fixture_now;assert(command("MODEYIELD")==0);assert(command("ARM_PASSIVE")==-1);',
            'setup(0);physical_key=1;assert(command("ARM_PASSIVE")==0);advance(5000);assert(passive_tick(fixture_now)==-1);assert(!armed);',
            'setup(1);physical_contact=1;assert(command("ARM_PASSIVE")==0);advance(5000);assert(passive_tick(fixture_now)==-1);assert(!armed);',
            'setup(0);assert(command("ARM_PASSIVE")==0);fixture_now+=1000;assert(passive_tick(fixture_now)==-1);assert(!armed);',
            'setup(0);fixture_now=session_time+120000;heartbeat=fixture_now;assert(command("ARM_PASSIVE")==-1);assert(!armed);',
            'setup(0);assert(command("ARM_PASSIVE")==0);pending=2;assert(passive_tick(fixture_now)==-1);assert(!armed);',
            'setup(0);assert(command("ARM_PASSIVE")==0);assert(event(EV_REL,REL_WHEEL,1)==-1);assert(!armed);',
            'setup(1);assert(command("ARM_PASSIVE")==0);assert(event(EV_SYN,SYN_DROPPED,0)==-1);assert(!armed);',
            'setup(1);assert(command("ARM_PASSIVE")==0);assert(event(EV_MSC,MSC_SCAN,1)==-1);assert(!armed);',
            'setup(1);assert(command("ARM_PASSIVE")==0);fixture_now-=1;assert(event(EV_SYN,SYN_REPORT,0)==-1);assert(!armed);',
        ]
        for case in cases:
            with self.subTest(case=case):
                run('int main(void){' + case + 'return 0;}')


if __name__ == "__main__":
    unittest.main()
