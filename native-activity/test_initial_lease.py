"""Initial lease bounds using actual collector code, synthetic FDs only."""
import ast,pathlib,unittest
from test_pointer_yield import PREFIX
from test_auth_release_settling import run
ROOT=pathlib.Path(__file__).parent
class InitialLeaseTests(unittest.TestCase):
 def test_exact_bounds_once_precalibration_and_no_renewal(self):
  body=r'''
int main(void){
 fixture_now=1000;session_time=heartbeat=1000;
 assert(session_budget_ms==120000);assert(expiry_phase(121000,121000,1000)==18);
 const char *bad[]={"LEASE_119","LEASE_1201","LEASE_0120","LEASE_600x","LEASE_+600","LEASE_","LEASE_99999","LEASE_0001200","LEASE_1200x","LEASE_+1200","LEASE_-1200","LEASE_1 00","LEASE_12a0"};
 for(unsigned i=0;i<sizeof bad/sizeof bad[0];i++){assert(command(bad[i])==-1);assert(session_budget_ms==120000);assert(!lease_negotiated);}
 assert(command("LEASE_1200")==0);assert(!strcmp(reply,"LEASE_1200_OK\n"));assert(session_time==1000);
 assert(session_budget_ms==1200000);assert(expiry_phase(2000,1000,1000)==17);assert(command("LEASE_600")==-1);assert(command("LEASE_120")==-1);
 assert(expiry_phase(1200999,1200999,1000)==0);assert(expiry_phase(1201000,1201000,1000)==18);
 const unsigned good[]={120,600,999,1000,1200};
 for(unsigned i=0;i<sizeof good/sizeof good[0];i++){
  char request[20],expected[20];fixture_now=1000;heartbeat=1000;lease_negotiated=false;session_budget_ms=120000;
  snprintf(request,sizeof request,"LEASE_%u",good[i]);snprintf(expected,sizeof expected,"LEASE_%u_OK\n",good[i]);
  assert(command(request)==0);assert(!strcmp(reply,expected));assert(session_budget_ms==(long long)good[i]*1000);assert(session_time==1000);
  assert(command(request)==-1);assert(command("HB")==0);assert(session_time==1000);
 }
 fixture_now=1000;lease_negotiated=false;session_budget_ms=120000;
 armed=true;assert(command("LEASE_600")==-1);armed=false;
 calibrating=true;assert(command("LEASE_600")==-1);calibrating=false;
 calibrated=true;assert(command("LEASE_600")==-1);calibrated=false;
 calibration_release_pending=true;assert(command("LEASE_600")==-1);calibration_release_pending=false;
 pointer_yield_mode=true;assert(command("LEASE_600")==-1);pointer_yield_mode=false;
 fixture_now=121000;heartbeat=121000;assert(command("LEASE_600")==-1);assert(session_budget_ms==120000);
 fixture_now=1000;heartbeat=1000;assert(command("LEASE_120")==0);assert(!strcmp(reply,"LEASE_120_OK\n"));
 return 0;
}
'''
  run(PREFIX+body)
 def test_actual_collector_negotiates_before_calibration_and_closes(self):
  tree=ast.parse((ROOT/'test_broker.py').read_text())
  method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name.startswith('test_full_collector_calibration_report'))
  source=next(ast.literal_eval(n.value) for n in method.body if isinstance(n,ast.Assign) and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str))
  begin=source.index('    line(control[1],"READY');end=source.index('    signal(SIGPIPE',begin)
  sequence=r'''    struct input_event event={0};line(control[1],"READY\n");
    assert(write(control[1],"LEASE_1200\n",11)==11);line(control[1],"LEASE_1200_OK\n");
    assert(write(control[1],"MODEYIELD2\n",11)==11);line(control[1],"MODEYIELD2_OK\n");
    assert(write(control[1],"CALIBRATE\n",10)==10);line(control[1],"CALIBRATING\n");
    assert(write(control[1],"REPORT\n",7)==7);line(control[1],"CAL_DIAG_00010000\n");line(control[1],"CAL_IDLE_NNM000\n");line(control[1],"OBS_DIAG_0000\n");
'''
  run(source[:begin]+sequence+source[end:])
