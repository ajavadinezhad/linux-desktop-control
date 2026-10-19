"""Strict yield coverage fixtures; no physical devices or privileged helper."""
import ast
import pathlib
import subprocess
import tempfile
import unittest
from test_pointer_yield import PREFIX

ROOT=pathlib.Path(__file__).parent

def compile_run(source,timeout=5):
    with tempfile.TemporaryDirectory(prefix='strict-pointer-coverage-') as directory:
        root=pathlib.Path(directory);(root/'fixture.c').write_text(source)
        subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-I',str(ROOT),str(root/'fixture.c'),'-o',str(root/'fixture')],check=True)
        subprocess.run([str(root/'fixture')],check=True,timeout=timeout)

class StrictPointerCoverageTests(unittest.TestCase):
    def test_snapshot_abs_wheel_stale_and_reset_cannot_supply_relative_coverage(self):
        prefix=PREFIX.replace('static int have_event, pending, closed_mask;','static int have_event, pending, closed_mask;static int fixture_held;')
        prefix=prefix.replace('memset(p,0,(KEY_MAX+8)/8);return 0;','memset(p,0,(KEY_MAX+8)/8);if(fixture_held){((unsigned char*)p)[KEY_LEFTSHIFT/8]|=1U<<(KEY_LEFTSHIFT%8);((unsigned char*)p)[BTN_LEFT/8]|=1U<<(BTN_LEFT%8);}return 0;')
        body=r'''
static void event(unsigned type,unsigned code,int value,long long stamp){
 fixture_event=(struct input_event){.time={stamp/1000,(stamp%1000)*1000},.type=type,.code=code,.value=value};have_event=1;assert(drain(4)==0);
}
int main(void){
 device_count=1;device_categories[0]=3;
 assert(command("MODEYIELD2")==0);assert(!strcmp(reply,"MODEYIELD2_OK\n"));
 assert(pointer_strict_coverage);heartbeat=session_time=fixture_now;assert(command("CALIBRATE")==0);
 fixture_now=2000;fixture_held=1;assert(calibration_tick(fixture_now)==0);assert(calibration_seen==3);
 fixture_held=0;fixture_now=3500;assert(calibration_tick(fixture_now)==0);
 assert(!calibrated&&!calibration_pointer_stream&&!calibration_diag.stream_record);
 assert(command("ARM")==-1);
 event(EV_ABS,ABS_X,1,3500);event(EV_REL,REL_WHEEL,1,3500);event(EV_REL,REL_X,0,3500);
 event(EV_REL,REL_X,1,calibration_time); /* stale relative motion */
 fixture_now=5000;assert(calibration_tick(fixture_now)==0);assert(!calibrated&&!calibration_pointer_stream);
 device_categories[0]=CATEGORY_KEYBOARD;event(EV_REL,REL_X,1,5000);assert(!calibration_pointer_stream);
 device_categories[0]=3;fixture_now=5100;event(EV_REL,REL_X,1,5100);assert(calibration_pointer_stream);
 event(EV_SYN,SYN_DROPPED,0,5100);assert(!calibration_pointer_stream&&calibration_seen==0);
 event(EV_SYN,SYN_REPORT,0,5100);assert(calibration_tick(fixture_now)==0);
 assert(!calibration_pointer_stream&&!strcmp(reply,"CALIBRATION_RESET\n"));
 fixture_now=5200;fixture_held=1;assert(calibration_tick(fixture_now)==0);fixture_held=0;
 fixture_now=6800;assert(calibration_tick(fixture_now)==0);assert(!calibrated);
 event(EV_REL,REL_Y,-1,6800);assert(calibration_pointer_stream);
 fixture_now=8300;assert(calibration_tick(fixture_now)==0);assert(calibrated);
 assert(command("ARM")==0);assert(!strcmp(reply,"ARMED\n"));
 return 0;
}
'''
        compile_run(prefix+body)

    def test_full_collector_snapshot_only_rejected_then_primary_relative_accepted(self):
        tree=ast.parse((ROOT/'test_broker.py').read_text())
        method=next(node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef) and node.name=='test_full_collector_calibration_report_closes_fake_sources_without_arm')
        source=next(ast.literal_eval(node.value) for node in method.body if isinstance(node,ast.Assign) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str))
        source=source.replace('static int fake_ioctl(', 'static int snapshot_down(void);\nstatic int fake_ioctl(')
        source=source.replace('assert(fd==7);memset(out,0,(KEY_MAX+8)/8);return 0;', 'assert(fd==7);memset(out,0,(KEY_MAX+8)/8);if(snapshot_down()){((unsigned char*)out)[KEY_LEFTSHIFT/8]|=1U<<(KEY_LEFTSHIFT%8);((unsigned char*)out)[BTN_LEFT/8]|=1U<<(BTN_LEFT%8);}return 0;')
        source=source.replace('#undef main\nstatic void line', '#undef main\nstatic int snapshot_down(void){return calibrating && now_ms()-calibration_time>20 && now_ms()-calibration_time<120;}\nstatic void line')
        begin=source.index('    line(control[1],"READY')
        end=source.index('    signal(SIGPIPE',begin)
        sequence=r'''    line(control[1],"READY\n");assert(write(control[1],"MODEYIELD2\n",11)==11);line(control[1],"MODEYIELD2_OK\n");
    assert(write(control[1],"CALIBRATE\n",10)==10);line(control[1],"CALIBRATING\n");
    /* Two seconds with snapshot key/button credit, but no primary records:
     * every reply MUST remain ALIVE, never CALIBRATED. */
    for(int i=0;i<20;i++){usleep(100000);assert(write(control[1],"HB\n",3)==3);line(control[1],"ALIVE\n");}
    long long stamp=now_ms();struct input_event event={0};event.time.tv_sec=stamp/1000;event.time.tv_usec=(stamp%1000)*1000;
    event.type=EV_REL;event.code=REL_X;event.value=1;assert(write(stream[1],&event,sizeof event)==sizeof event);
    assert(write(control[1],"HB\n",3)==3);line(control[1],"ALIVE\n");
    for(int i=0;i<14;i++){usleep(100000);assert(write(control[1],"HB\n",3)==3);line(control[1],"ALIVE\n");}
    usleep(200000);line(control[1],"CALIBRATED\n");assert(write(control[1],"ARM\n",4)==4);line(control[1],"ARMED\n");
    assert(write(control[1],"CLOSE\n",6)==6);line(control[1],"OBS_DIAG_1000\n");usleep(50000);
'''
        combined=source[:begin]+sequence+source[end:]
        compile_run(combined,timeout=8)
        # An undeliverable optional CLOSE diagnostic must not turn clean close
        # into failure. Run the production main loop with an EPIPE send fixture.
        missing=combined.replace('return write(fd,p,n);', 'if(n>=9&&!memcmp(p,"OBS_DIAG_",9)){errno=EPIPE;return -1;}return write(fd,p,n);')
        missing=missing.replace('line(control[1],"OBS_DIAG_1000\\n");','')
        compile_run(missing,timeout=8)

if __name__=='__main__':unittest.main()
