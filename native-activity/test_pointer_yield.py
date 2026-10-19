"""Persistent-yield collector fixtures: no device access or helper launch."""
import ast
import pathlib
import subprocess
import tempfile
import unittest
from test_quiet_diagnostics import source as diagnostic_source

# Reuse bounded fake read/clock/ioctl/poll/send adapters, not a fake state machine.
PREFIX=diagnostic_source.split('int main(void){',1)[0]
BODY=r'''
static void event(unsigned type,unsigned code,int value){
 fixture_event=(struct input_event){.time={fixture_now/1000,(fixture_now%1000)*1000},.type=type,.code=code,.value=value};have_event=1;
}
int main(void){
 device_count=1;device_categories[0]=CATEGORY_POINTER;
 fixture_now=1000;arm_time=1000;armed=true;
 event(EV_REL,REL_X,1);assert(drain(4)==1);assert(!pointer_yielded); /* old default */
 armed=false;assert(command("MODEYIELD")==0);assert(!strcmp(reply,"MODEYIELD_OK\n"));
 assert(command("MODEYIELD")==-1);
 armed=true;event(EV_REL,REL_X,1);assert(drain(4)==0);
 assert(pointer_yielded&&!pointer_quiet&&pointer_epoch==1);assert(!strcmp(reply,"YIELDED_1\n"));assert(!closed_mask);
 assert(command("RESUME_1")==-1); /* quiet not yet observed */
 fixture_now=2000;event(EV_REL,REL_Y,-1);assert(drain(4)==0);assert(pointer_epoch==1);
 assert(pointer_yield_tick(3499)==0);assert(!pointer_quiet);
 fixture_now=3500;assert(pointer_yield_tick(fixture_now)==0);assert(pointer_quiet);
 assert(!strcmp(reply,"QUIET_1\n"));assert(!closed_mask);
 fixture_now=3600;event(EV_REL,REL_X,1);assert(drain(4)==0);
 assert(!pointer_quiet&&pointer_epoch==2);assert(!strcmp(reply,"YIELDED_2\n"));
 assert(command("RESUME_1")==-1); /* old epoch is never authority */
 fixture_now=5100;pending=1;assert(pointer_yield_tick(fixture_now)==0);assert(!pointer_quiet);
 pending=0;assert(pointer_yield_tick(fixture_now)==0);assert(pointer_quiet);assert(!strcmp(reply,"QUIET_2\n"));
 assert(command("RESUME_02")==-1);assert(command("RESUME_65")==-1);
 heartbeat=fixture_now;pending=2;assert(command("RESUME_2")==-1);assert(pointer_yielded);
 pending=0;assert(feed_control("RES",3)==0);assert(feed_control("UME_2\n",6)==0);
 assert(!strcmp(reply,"ARMED_2\n"));assert(!pointer_yielded&&!pointer_quiet);assert(armed);assert(!closed_mask);
 assert(command("RESUME_2")==-1); /* replay refused */
 pointer_yielded=pointer_quiet=true;fixture_now=120000;heartbeat=120000;
 assert(command("RESUME_2")==-1); /* absolute cap at resume boundary */
 pointer_yielded=pointer_quiet=false;fixture_now=5100;arm_time=5100;
 /* All nonpositional classes remain terminal even in opted-in mode. */
 unsigned types[]={EV_KEY,EV_REL,EV_REL,EV_REL,EV_REL,EV_ABS,EV_MSC,EV_SW};
 unsigned codes[]={BTN_LEFT,REL_WHEEL,REL_HWHEEL,REL_WHEEL_HI_RES,REL_Z,ABS_X,MSC_TIMESTAMP,SW_LID};
 for(unsigned i=0;i<sizeof types/sizeof types[0];i++){
  event(types[i],codes[i],1);assert(drain(4)==1);assert(!pointer_yielded);
 }
 event(EV_REL,REL_X,0);assert(drain(4)==1);
 event(EV_SYN,SYN_DROPPED,0);assert(drain(4)==-1);
 pointer_yielded=false;pointer_epoch=POINTER_YIELD_MAX_EPOCH;
 event(EV_REL,REL_X,1);assert(drain(4)==-1); /* bounded epochs */
 assert(expiry_phase(120000,120000,0)==18); /* no lease renewal */
 assert(expiry_phase(2000,1000,0)==17); /* heartbeat remains mandatory */
 return 0;
}
'''

class PointerYieldTests(unittest.TestCase):
    def test_persistent_yield_quiet_epoch_resume_and_terminal_classes(self):
        with tempfile.TemporaryDirectory(prefix='pointer-yield-fixture-') as directory:
            root=pathlib.Path(directory);(root/'fixture.c').write_text(PREFIX+BODY)
            subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',str(root/'fixture.c'),'-o',str(root/'fixture')],check=True)
            subprocess.run([str(root/'fixture')],check=True,timeout=3)

    def test_resume_rechecks_expiry_after_boundary_queries(self):
        prefix=PREFIX.replace('static int fixture_poll(struct pollfd *fds,nfds_t n,int timeout){',
                              'static int fixture_poll(struct pollfd *fds,nfds_t n,int timeout){fixture_now+=2;')
        body=r'''int main(void){
 device_count=1;pointer_epoch=1;pointer_yield_mode=pointer_yielded=pointer_quiet=armed=true;
 fixture_now=119999;heartbeat=119999;session_time=0;strcpy(reply,"UNCHANGED");
 assert(command("RESUME_1")==-1);assert(fixture_now==120001);
 assert(pointer_yielded&&pointer_quiet);assert(!strcmp(reply,"UNCHANGED"));
 fixture_now=1999;heartbeat=1000;session_time=1000;
 assert(command("RESUME_1")==-1);assert(fixture_now==2001);
 assert(pointer_yielded&&pointer_quiet);assert(!strcmp(reply,"UNCHANGED"));
 return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='pointer-resume-expiry-') as directory:
            root=pathlib.Path(directory);(root/'fixture.c').write_text(prefix+body)
            subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',str(root/'fixture.c'),'-o',str(root/'fixture')],check=True)
            subprocess.run([str(root/'fixture')],check=True,timeout=3)

    def test_full_collector_keeps_sources_until_terminal_wheel(self):
        # Reuse the real collector main-loop harness with pipe-backed fake evdev.
        tree=ast.parse((pathlib.Path(__file__).parent/'test_broker.py').read_text())
        method=next(node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef) and node.name=='test_full_collector_calibration_report_closes_fake_sources_without_arm')
        source=next(ast.literal_eval(node.value) for node in method.body if isinstance(node,ast.Assign) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str))
        begin=source.index('    line(control[1],"READY')
        end=source.index('    signal(SIGPIPE',begin)
        sequence=r'''    line(control[1],"READY\n");assert(write(control[1],"MODEYIELD\n",10)==10);line(control[1],"MODEYIELD_OK\n");
    assert(write(control[1],"CALIBRATE\n",10)==10);line(control[1],"CALIBRATING\n");usleep(5000);
    long long stamp=now_ms();struct input_event event={0};
    event.time.tv_sec=stamp/1000;event.time.tv_usec=(stamp%1000)*1000;
    event.type=EV_KEY;event.code=KEY_LEFTSHIFT;event.value=1;assert(write(stream[1],&event,sizeof event)==sizeof event);
    event.type=EV_REL;event.code=REL_X;assert(write(stream[1],&event,sizeof event)==sizeof event);
    assert(write(control[1],"HB\n",3)==3);line(control[1],"ALIVE\n");
    for(int i=0;i<14;i++){usleep(100000);assert(write(control[1],"HB\n",3)==3);line(control[1],"ALIVE\n");}
    usleep(200000);line(control[1],"CALIBRATED\n");assert(write(control[1],"ARM\n",4)==4);line(control[1],"ARMED\n");
    usleep(5000);stamp=now_ms();event.time.tv_sec=stamp/1000;event.time.tv_usec=(stamp%1000)*1000;
    assert(write(stream[1],&event,sizeof event)==sizeof event);
    assert(write(control[1],"HB\n",3)==3);line(control[1],"YIELDED_1\n");line(control[1],"ALIVE\n");
    for(int i=0;i<14;i++){usleep(100000);assert(write(control[1],"HB\n",3)==3);line(control[1],"ALIVE\n");}
    usleep(200000);line(control[1],"QUIET_1\n");assert(write(control[1],"RESUME_1\n",9)==9);line(control[1],"ARMED_1\n");
    usleep(5000);stamp=now_ms();event.time.tv_sec=stamp/1000;event.time.tv_usec=(stamp%1000)*1000;
    event.type=EV_REL;event.code=REL_WHEEL;assert(write(stream[1],&event,sizeof event)==sizeof event);
    line(control[1],"ACTIVITY_POINTER\n");line(control[1],"OBS_DIAG_1111\n");
'''
        source=source[:begin]+sequence+source[end:]
        with tempfile.TemporaryDirectory(prefix='pointer-yield-loop-') as directory:
            root=pathlib.Path(directory);(root/'fixture.c').write_text(source)
            subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-I',str(pathlib.Path(__file__).parent),str(root/'fixture.c'),'-o',str(root/'fixture')],check=True)
            subprocess.run([str(root/'fixture')],check=True,timeout=8)

if __name__=='__main__':unittest.main()
