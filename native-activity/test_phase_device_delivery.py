"""Real poll/pipe + actual opener remap across calibration/ARM at 20 devices.
No input devices, compositor, administrator helper, or GUI are accessed.
"""
import ast
import pathlib
import subprocess
import tempfile
import unittest
ROOT=pathlib.Path(__file__).parent

class PhaseDeliveryTests(unittest.TestCase):
    def test_twenty_device_actual_remap_keeps_last_primary_live_after_arm(self):
        tree=ast.parse((ROOT/'test_broker.py').read_text())
        method=next(node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef) and node.name=='test_full_collector_calibration_report_closes_fake_sources_without_arm')
        template=next(ast.literal_eval(node.value) for node in method.body if isinstance(node,ast.Assign) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str))
        prefix=template.split('int main(void) {',1)[0].replace('#include <unistd.h>','#include <unistd.h>\n#include <sys/syscall.h>')
        prefix=prefix.replace('fd==5 && option==SO_DOMAIN','fd==24 && option==SO_DOMAIN')
        prefix=prefix.replace('assert(fd==4 || fd==7);','assert((fd>=4&&fd<=23)||(fd>=26&&fd<=45));')
        prefix=prefix.replace('assert(fd==4);','assert(fd>=4&&fd<=23);').replace('assert(fd==7);','assert(fd>=26&&fd<=45);')
        opener=(ROOT/'opener.c').read_text()
        remap=opener[opener.index('    int source[2*MAX_DEVICES+3]'):opener.index('    phase=9;')]
        remap=remap.replace('goto fault','abort()')
        body=r'''
int main(void) {
 int channels[2],streams[20][2],snap[20][2],topology_pipe[2],owner_pipe[2];
 assert(socketpair(AF_UNIX,SOCK_STREAM,0,channels)==0);
 assert(pipe(topology_pipe)==0);assert(pipe(owner_pipe)==0);
 for(int i=0;i<20;i++){assert(pipe2(streams[i],O_NONBLOCK)==0);assert(pipe2(snap[i],O_NONBLOCK)==0);}
 pid_t child=fork();assert(child>=0);
 if(!child){
  int count=20,control=channels[0],topology=topology_pipe[0],parent=owner_pipe[0];
  int devices[MAX_DEVICES],snapshots[MAX_DEVICES];
  for(int i=0;i<count;i++){devices[i]=streams[i][0];snapshots[i]=snap[i][0];device_categories[i]=3;}
REMAP
  char *args[]={"fixture","20",NULL};_exit(collector_main(2,args));
 }
 close(channels[0]);close(topology_pipe[0]);close(owner_pipe[0]);
 for(int i=0;i<20;i++){close(streams[i][0]);close(snap[i][0]);}
 int fd=channels[1];line(fd,"READY\n");assert(write(fd,"MODEYIELD2\n",11)==11);line(fd,"MODEYIELD2_OK\n");
 assert(write(fd,"CALIBRATE\n",10)==10);line(fd,"CALIBRATING\n");usleep(5000);
 long long stamp=now_ms();struct input_event events[3]={0};
 for(int i=0;i<3;i++){events[i].time.tv_sec=stamp/1000;events[i].time.tv_usec=(stamp%1000)*1000;}
 events[0].type=EV_KEY;events[0].code=KEY_LEFTSHIFT;events[0].value=1;
 events[1].type=EV_KEY;events[1].code=KEY_LEFTSHIFT;events[1].value=0;
 events[2].type=EV_REL;events[2].code=REL_X;events[2].value=1;
 assert(write(streams[0][1],events,sizeof events)==sizeof events);
 assert(write(fd,"HB\n",3)==3);line(fd,"ALIVE\n");
 for(int i=0;i<14;i++){usleep(100000);assert(write(fd,"HB\n",3)==3);line(fd,"ALIVE\n");}
 usleep(200000);line(fd,"CALIBRATED\n");assert(write(fd,"ARM\n",4)==4);line(fd,"ARMED\n");
 usleep(5000);stamp=now_ms();events[2].time.tv_sec=stamp/1000;events[2].time.tv_usec=(stamp%1000)*1000;
 assert(write(streams[19][1],events+2,sizeof events[2])==sizeof events[2]);
 assert(write(fd,"HB\n",3)==3);line(fd,"YIELDED_1\n");line(fd,"ALIVE\n");
 assert(write(fd,"CLOSE\n",6)==6);line(fd,"OBS_DIAG_1111\n");
 int status;assert(waitpid(child,&status,0)==child);assert(WIFEXITED(status)&&WEXITSTATUS(status)==0);
 return 0;
}
'''.replace('REMAP',remap)
        with tempfile.TemporaryDirectory(prefix='phase-device-delivery-') as directory:
            root=pathlib.Path(directory);(root/'fixture.c').write_text(prefix+body)
            subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-I',str(ROOT),str(root/'fixture.c'),'-o',str(root/'fixture')],check=True)
            subprocess.run([str(root/'fixture')],check=True,timeout=7)

if __name__=='__main__':unittest.main()
