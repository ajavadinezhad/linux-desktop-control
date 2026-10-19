"""Terminal evidence uses production classifier and closes fake FDs first."""
import pathlib
import subprocess
import tempfile
import unittest
from test_pointer_yield import PREFIX

class ObservationDiagnosticTests(unittest.TestCase):
    def test_silence_coverage_feedback_motion_and_send_failure_distinguished(self):
        prefix=PREFIX.replace('static int have_event, pending, closed_mask;', 'static int have_event, pending, closed_mask;static int fail_yield_send;')
        prefix=prefix.replace('if(!strncmp(reply,"CAL_DIAG_",9))assert(closed_mask==15);return n;', 'if(strstr(reply,"OBS_DIAG_"))assert(closed_mask==15);if(fail_yield_send&&!strncmp(reply,"YIELDED_",8))return -1;return n;')
        body=r'''
static void event(unsigned type,unsigned code,int value){
 fixture_event=(struct input_event){.time={fixture_now/1000,(fixture_now%1000)*1000},.type=type,.code=code,.value=value};have_event=1;
}
static void clear(void){
 armed=calibrating=calibrated=false;pointer_yield_mode=pointer_yielded=pointer_quiet=false;
 pointer_epoch=0;calibration_pointer_stream=false;
 observation_primary_after_arm=observation_relative_after_arm=observation_yield_sent=false;
 closed_mask=0;fixture_now=2000;arm_time=2000;device_count=1;device_categories[0]=3;
}
int main(void){
 clear();pointer_strict_coverage=true;calibrating=true;calibration_seen=3;
 calibration_time=0;calibration_last_activity=0;
 assert(calibration_tick(fixture_now)==0);assert(!calibrated); /* missing streamed route */
 assert(command("REPORT")==3);assert(strlen(reply)==48);assert(!strcmp(reply+34,"OBS_DIAG_0000\n"));
 clear();calibrating=true;calibration_time=0;
 event(EV_REL,REL_X,1);assert(drain(4)==0);assert(calibration_pointer_stream);
 assert(report("FAULT\n")==0);assert(!strcmp(reply,"FAULT\nOBS_DIAG_1000\n"));
 clear();armed=true;event(EV_SYN,SYN_REPORT,0);assert(drain(4)==0);
 assert(report("FAULT\n")==0);assert(!strcmp(reply,"FAULT\nOBS_DIAG_0100\n"));
 clear();armed=true;pointer_yield_mode=true;event(EV_REL,REL_X,1);assert(drain(4)==0);
 assert(!strcmp(reply,"YIELDED_1\n"));assert(!closed_mask); /* never append while watching */
 assert(report("")==0);assert(!strcmp(reply,"OBS_DIAG_0111\n"));
 clear();armed=true;pointer_yield_mode=true;fail_yield_send=1;
 event(EV_REL,REL_Y,-1);assert(drain(4)==-1);fail_yield_send=0;
 assert(report("FAULT\n")==0);assert(!strcmp(reply,"FAULT\nOBS_DIAG_0110\n"));
 return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='observation-evidence-') as directory:
            root=pathlib.Path(directory);(root/'fixture.c').write_text(prefix+body)
            subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',str(root/'fixture.c'),'-o',str(root/'fixture')],check=True)
            subprocess.run([str(root/'fixture')],check=True,timeout=3)

if __name__=='__main__':unittest.main()
