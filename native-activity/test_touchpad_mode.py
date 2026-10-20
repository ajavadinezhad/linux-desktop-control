"""MODEYIELD3 production collector fixtures, synthetic records only."""
import ast
import pathlib
import subprocess
import tempfile
import unittest
from test_pointer_yield import PREFIX

ROOT = pathlib.Path(__file__).resolve().parent


def compile_run(source):
    with tempfile.TemporaryDirectory(prefix="ldc-pad-mode-") as temporary:
        root = pathlib.Path(temporary)
        (root / "fixture.c").write_text(source)
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                        str(root / "fixture.c"), "-o", str(root / "fixture")], check=True)
        subprocess.run([str(root / "fixture")], check=True, timeout=5)


class TouchpadModeTests(unittest.TestCase):
    def test_real_collector_loop_calibrates_pad_then_snapshot_contact_yields(self):
        tree = ast.parse((ROOT / "test_broker.py").read_text())
        method = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                      and node.name == "test_full_collector_calibration_report_closes_fake_sources_without_arm")
        source = next(ast.literal_eval(node.value) for node in method.body
                      if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                      and isinstance(node.value.value, str))
        source = source.replace("static int fake_ioctl(", "static int snapshot_bits(void);\nstatic int fake_ioctl(")
        source = source.replace("assert(fd==7);memset(out,0,(KEY_MAX+8)/8);return 0;", r'''
assert(fd==7);memset(out,0,(KEY_MAX+8)/8);
int bits=snapshot_bits();
if(bits&1)((unsigned char*)out)[KEY_LEFTSHIFT/8]|=1U<<(KEY_LEFTSHIFT%8);
if(bits&2){((unsigned char*)out)[BTN_TOUCH/8]|=1U<<(BTN_TOUCH%8);((unsigned char*)out)[BTN_TOOL_FINGER/8]|=1U<<(BTN_TOOL_FINGER%8);}
return 0;''')
        source = source.replace("#undef main\nstatic void line", r'''#undef main
static int snapshot_bits(void){
 long long now=now_ms();
 if(calibrating&&now-calibration_time>20&&now-calibration_time<120)return 1;
 if(armed&&now-arm_time>100&&now-arm_time<350)return 2;
 return 0;
}
static void emit(int fd,unsigned type,unsigned code,int value){
 long long now=now_ms();struct input_event event={.time={now/1000,(now%1000)*1000},.type=type,.code=code,.value=value};
 assert(write(fd,&event,sizeof event)==sizeof event);
}
static void line''')
        source = source.replace('device_categories[0]=CATEGORY_KEYBOARD|CATEGORY_POINTER;', r'''
device_categories[0]=CATEGORY_KEYBOARD|CATEGORY_POINTER;
device_touchpad[0]=true;touchpad_limits[0]=(struct tp_limits){0,1000,0,1000,false,0,0,0};''')
        begin = source.index('    line(control[1],"READY')
        end = source.index('    signal(SIGPIPE', begin)
        sequence = r'''
    line(control[1],"READY\n");assert(write(control[1],"MODEYIELD3\n",11)==11);line(control[1],"MODEYIELD3_OK\n");
    assert(write(control[1],"CALIBRATE\n",10)==10);line(control[1],"CALIBRATING\n");usleep(5000);
    emit(stream[1],EV_KEY,BTN_TOUCH,1);emit(stream[1],EV_KEY,BTN_TOOL_FINGER,1);
    emit(stream[1],EV_ABS,ABS_X,100);emit(stream[1],EV_ABS,ABS_Y,100);emit(stream[1],EV_SYN,SYN_REPORT,0);
    emit(stream[1],EV_ABS,ABS_X,140);emit(stream[1],EV_SYN,SYN_REPORT,0);
    emit(stream[1],EV_KEY,BTN_TOUCH,0);emit(stream[1],EV_KEY,BTN_TOOL_FINGER,0);emit(stream[1],EV_SYN,SYN_REPORT,0);
    assert(write(control[1],"HB\n",3)==3);line(control[1],"ALIVE\n");
    for(int i=0;i<14;i++){usleep(100000);assert(write(control[1],"HB\n",3)==3);line(control[1],"ALIVE\n");}
    usleep(300000);line(control[1],"CALIBRATED\n");assert(write(control[1],"ARM\n",4)==4);line(control[1],"ARMED\n");
    usleep(200000);line(control[1],"YIELDED_1\n");
    assert(write(control[1],"HB\n",3)==3);line(control[1],"ALIVE\n");
    for(int i=0;i<15;i++){usleep(100000);assert(write(control[1],"HB\n",3)==3);line(control[1],"ALIVE\n");}
    usleep(300000);line(control[1],"QUIET_1\n");assert(write(control[1],"RESUME_1\n",9)==9);line(control[1],"ARMED_1\n");
    assert(write(control[1],"CLOSE\n",6)==6);line(control[1],"OBS_TPAD_1001\n");
    struct input_event event={0};
'''
        source = source[:begin] + sequence + source[end:]
        with tempfile.TemporaryDirectory(prefix="ldc-pad-loop-") as temporary:
            root = pathlib.Path(temporary)
            (root / "fixture.c").write_text(source)
            subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT),
                            str(root / "fixture.c"), "-o", str(root / "fixture")], check=True)
            subprocess.run([str(root / "fixture")], check=True, timeout=8)

    def test_selected_pad_credit_contact_yield_and_snapshot_boundaries(self):
        prefix = PREFIX.replace(
            "static int have_event, pending, closed_mask;",
            "static int have_event, pending, closed_mask;static int snapshot_contact,snapshot_button;")
        prefix = prefix.replace("memset(p,0,(KEY_MAX+8)/8);return 0;", r'''
memset(p,0,(KEY_MAX+8)/8);
if(snapshot_contact){((unsigned char*)p)[BTN_TOUCH/8]|=1U<<(BTN_TOUCH%8);((unsigned char*)p)[BTN_TOOL_FINGER/8]|=1U<<(BTN_TOOL_FINGER%8);}
if(snapshot_button)((unsigned char*)p)[BTN_LEFT/8]|=1U<<(BTN_LEFT%8);
return 0;''')
        body = r'''
static int event(unsigned type,unsigned code,int value){
 fixture_event=(struct input_event){.time={fixture_now/1000,(fixture_now%1000)*1000},.type=type,.code=code,.value=value};
 have_event=1;return drain(4);
}
static void contact(void){
 assert(event(EV_KEY,BTN_TOUCH,1)==0);assert(event(EV_KEY,BTN_TOOL_FINGER,1)==0);
}
static void release(void){
 assert(event(EV_KEY,BTN_TOUCH,0)==0);assert(event(EV_KEY,BTN_TOOL_FINGER,0)==0);
 assert(event(EV_SYN,SYN_REPORT,0)==0);
}
int main(void){
 device_count=1;device_categories[0]=CATEGORY_POINTER;
 heartbeat=session_time=fixture_now;assert(command("MODEYIELD3")==-1); /* no admission */
 device_touchpad[0]=true;touchpad_limits[0]=(struct tp_limits){0,1000,0,1000,false,0,0,0};
 assert(command("MODEYIELD3")==0);assert(!strcmp(reply,"MODEYIELD3_OK\n"));
 assert(command("MODEYIELD2")==-1);assert(command("MODEYIELD3")==-1);
 assert(command("CALIBRATE")==0);assert(calibrating);
 calibration_seen=CATEGORY_KEYBOARD;fixture_now+=10;
 device_touchpad[0]=false; /* simulated separate relative pointer route */
 assert(event(EV_REL,REL_X,2)==0);assert(!calibration_pointer_stream); /* other route not credit */
 device_touchpad[0]=true;
 contact();assert(event(EV_ABS,ABS_X,100)==0);assert(event(EV_ABS,ABS_Y,100)==0);
 assert(event(EV_SYN,SYN_REPORT,0)==0);assert(!calibration_pointer_stream);
 fixture_now+=10;assert(event(EV_ABS,ABS_X,120)==0);
 assert(event(EV_SYN,SYN_REPORT,0)==0);assert(calibration_pointer_stream&&calibration_touchpad_motion);
 fixture_now+=2000;assert(calibration_tick(fixture_now)==0);assert(!calibrated); /* stationary finger blocks */
 release();fixture_now+=1500;assert(calibration_tick(fixture_now)==0);assert(calibrated);
 heartbeat=fixture_now;assert(command("ARM")==0);assert(armed);
 /* Snapshot contact alone immediately yields, without stream delivery or credit. */
 snapshot_contact=1;fixture_now+=10;assert(held_state()==0);
 assert(pointer_yielded&&!pointer_quiet&&pointer_epoch==1);assert(!strcmp(reply,"YIELDED_1\n"));
 assert(!observation_touchpad_motion_after_arm);
 fixture_now+=2000;assert(pointer_yield_tick(fixture_now)==0);assert(!pointer_quiet);
 snapshot_contact=0;fixture_now+=1500;assert(pointer_yield_tick(fixture_now)==0);assert(pointer_quiet);
 heartbeat=fixture_now;
 /* New snapshot contact after QUIET invalidates its epoch before RESUME. */
 snapshot_contact=1;assert(command("RESUME_1")==-1);assert(pointer_epoch==2&&!pointer_quiet);
 snapshot_contact=0;fixture_now+=1500;assert(pointer_yield_tick(fixture_now)==0);assert(pointer_quiet);
 heartbeat=fixture_now;assert(command("RESUME_2")==0);
 fixture_now+=1;contact();assert(pointer_yielded&&!pointer_quiet&&pointer_epoch==3);
 event(EV_ABS,ABS_X,200);event(EV_ABS,ABS_Y,200);event(EV_SYN,SYN_REPORT,0);
 assert(!observation_touchpad_motion_after_arm);
 event(EV_ABS,ABS_Y,240);event(EV_SYN,SYN_REPORT,0);assert(observation_touchpad_motion_after_arm);
 release();fixture_now+=1500;assert(pointer_yield_tick(fixture_now)==0);assert(pointer_quiet);
 /* A partial frame prevents resume despite no held keys/contact. */
 assert(event(EV_ABS,ABS_PRESSURE,0)==0);assert(tp_incomplete(&touchpad_states[0]));
 heartbeat=fixture_now;assert(command("RESUME_3")==-1);
 assert(event(EV_SYN,SYN_REPORT,0)==0);
 heartbeat=fixture_now;assert(command("RESUME_3")==0);
 /* Relative movement from an unselected separate mouse remains terminal. */
 device_touchpad[0]=false;
 assert(event(EV_REL,REL_X,1)==1);assert(!pointer_yielded);
 device_touchpad[0]=true;
 /* Physical buttons never receive the contact exemption. */
 snapshot_button=1;assert(held_state()==1);snapshot_button=0;
 assert(event(EV_KEY,BTN_LEFT,1)==-1);
 assert(report("ACTIVITY\n")==0);assert(!strcmp(reply,"ACTIVITY\nOBS_TPAD_1111\n"));
 assert(closed_mask==15);
 return 0;
}
'''
        compile_run(prefix + body)

    def test_touchpad_is_not_enabled_by_legacy_relative_mode(self):
        body = r'''
int main(void){
 device_count=1;device_categories[0]=CATEGORY_POINTER;device_touchpad[0]=true;
 touchpad_limits[0]=(struct tp_limits){0,1000,0,1000,false,0,0,0};
 assert(command("MODEYIELD2")==0);armed=true;arm_time=fixture_now;
 fixture_event=(struct input_event){.time={fixture_now/1000,(fixture_now%1000)*1000},.type=EV_KEY,.code=BTN_TOUCH,.value=1};
 have_event=1;assert(drain(4)==1);assert(!pointer_yielded&&!touchpad_yield_mode);
 return 0;
}
'''
        compile_run(PREFIX + body)


if __name__ == "__main__":
    unittest.main()
