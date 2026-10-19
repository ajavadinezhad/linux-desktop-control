"""Bounded startup release settling; fake state/pipes, no input devices or UI."""
import ast
import pathlib
import subprocess
import tempfile
import unittest
from test_pointer_yield import PREFIX
ROOT=pathlib.Path(__file__).parent

def run(source,timeout=4):
    with tempfile.TemporaryDirectory(prefix='auth-release-settling-') as directory:
        path=pathlib.Path(directory);(path/'fixture.c').write_text(source)
        subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-I',str(ROOT),str(path/'fixture.c'),'-o',str(path/'fixture')],check=True)
        subprocess.run([str(path/'fixture')],check=True,timeout=timeout)

class AuthReleaseSettlingTests(unittest.TestCase):
    def test_auth_records_have_no_credit_and_all_deadlines_fail_closed(self):
        prefix=PREFIX.replace('static int have_event, pending, closed_mask;', 'static int have_event, pending, closed_mask;static int held,error_query;')
        prefix=prefix.replace('memset(p,0,(KEY_MAX+8)/8);return 0;', 'if(error_query){return -1;}memset(p,0,(KEY_MAX+8)/8);if(held)((unsigned char*)p)[BTN_LEFT/8]|=1U<<(BTN_LEFT%8);return 0;')
        body=r'''
static void event(unsigned type,unsigned code,int value){
 fixture_event=(struct input_event){.time={fixture_now/1000,(fixture_now%1000)*1000},.type=type,.code=code,.value=value};have_event=1;
}
static void reset(void){
 armed=calibrating=calibrated=calibration_release_pending=false;pointer_yield_mode=pointer_strict_coverage=false;
 calibration_seen=0;calibration_pointer_stream=false;fixture_now=1000;heartbeat=session_time=1000;held=1;pending=error_query=0;
 memset(&calibration_diag,0,sizeof calibration_diag);strcpy(reply,"NO_CUE");
}
int main(void){
 device_count=1;device_categories[0]=3;reset();
 assert(command("MODEYIELD2")==0);strcpy(reply,"NO_CUE");
 assert(command("CALIBRATE")==0);assert(calibration_release_pending&&!calibrating);
 assert(command("CALIBRATE")==-1);assert(command("ARM")==-1);assert(command("MODEYIELD")==-1);
 fixture_now=1200;event(EV_KEY,KEY_LEFTSHIFT,1);assert(calibration_release_tick(fixture_now)==0);
 event(EV_REL,REL_X,1);assert(calibration_release_tick(fixture_now)==0);
 assert(!calibration_seen&&!calibration_pointer_stream&&!calibration_diag.stream_record&&!calibration_diag.held_seen);
 assert(!strcmp(reply,"NO_CUE"));held=0;pending=1;
 assert(calibration_release_tick(fixture_now)==0);assert(!calibrating);
 pending=0;fixture_now=1500;assert(calibration_release_tick(fixture_now)==0);
 assert(calibrating&&!calibration_release_pending);assert(!strcmp(reply,"CALIBRATING\n"));
 assert(calibration_time==1500&&!calibration_seen&&!calibration_pointer_stream);
 event(EV_REL,REL_X,1);fixture_event.time.tv_sec=1;fixture_event.time.tv_usec=499000;assert(drain(4)==0);
 assert(!calibration_pointer_stream); /* auth/stale records remain ineligible */
 reset();assert(command("CALIBRATE")==0);fixture_now=6000;heartbeat=6000;
 assert(calibration_release_tick(fixture_now)==-1);assert(collector_phase==48&&!calibrating);assert(!strcmp(reply,"NO_CUE"));
 reset();error_query=1;assert(command("CALIBRATE")==-1);assert(collector_phase==49&&!calibrating);
 reset();fixture_now=119000;heartbeat=119000;session_time=0;assert(command("CALIBRATE")==0);
 held=0;fixture_now=120000;heartbeat=120000;
 assert(calibration_release_tick(fixture_now)==-1);assert(collector_phase==18&&!calibrating);
 return 0;
}
'''
        run(prefix+body)

    def test_actual_main_loop_waits_for_auth_release_before_fresh_cue(self):
        tree=ast.parse((ROOT/'test_broker.py').read_text())
        method=next(node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef) and node.name.startswith('test_full_collector_calibration_report'))
        source=next(ast.literal_eval(node.value) for node in method.body if isinstance(node,ast.Assign) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str))
        source=source.replace('static int fake_ioctl(', 'static int auth_held(void);\nstatic int fake_ioctl(')
        source=source.replace('assert(fd==7);memset(out,0,(KEY_MAX+8)/8);return 0;', 'assert(fd==7);memset(out,0,(KEY_MAX+8)/8);if(auth_held())((unsigned char*)out)[BTN_LEFT/8]|=1U<<(BTN_LEFT%8);return 0;')
        source=source.replace('#undef main\nstatic void line', '#undef main\nstatic int auth_held(void){static long long started;if(!started)started=now_ms();return now_ms()-started<150;}\nstatic void line')
        begin=source.index('    line(control[1],"READY');end=source.index('    signal(SIGPIPE',begin)
        sequence=r'''    struct input_event event={0};line(control[1],"READY\n");
    assert(write(control[1],"MODEYIELD2\n",11)==11);line(control[1],"MODEYIELD2_OK\n");
    assert(write(control[1],"CALIBRATE\n",10)==10);
    struct pollfd waiting={control[1],POLLIN,0};assert(poll(&waiting,1,50)==0); /* no early cue */
    line(control[1],"CALIBRATING\n");
    assert(write(control[1],"REPORT\n",7)==7);
    line(control[1],"CAL_DIAG_00010000\n");line(control[1],"CAL_IDLE_NNM000\n");line(control[1],"OBS_DIAG_0000\n");
'''
        run(source[:begin]+sequence+source[end:])

if __name__=='__main__':unittest.main()
