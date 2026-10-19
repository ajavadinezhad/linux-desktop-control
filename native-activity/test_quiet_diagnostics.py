"""Isolated quiet-gate reproducer; synthetic C records only, no devices/socket/UI."""
import pathlib,subprocess,tempfile,unittest
root=pathlib.Path(__file__).resolve().parent
source=r'''
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <linux/input.h>
#include <poll.h>
#include <stdarg.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>
static long long fixture_now=1000;
static struct input_event fixture_event;
static int have_event, pending, closed_mask;
static char reply[128];
static ssize_t fixture_read(int fd,void *buf,size_t n) {
 (void)fd;(void)n;if(!have_event){errno=EAGAIN;return -1;}
 have_event=0;memcpy(buf,&fixture_event,sizeof fixture_event);return sizeof fixture_event;
}
static int fixture_ioctl(int fd,unsigned long request,...) {
 (void)fd;(void)request;va_list ap;va_start(ap,request);void *p=va_arg(ap,void*);va_end(ap);
 memset(p,0,(KEY_MAX+8)/8);return 0;
}
static int fixture_poll(struct pollfd *fds,nfds_t n,int timeout){(void)timeout;assert(n==3);for(int i=0;i<3;i++)fds[i].revents=(pending&(1<<i))?POLLIN:0;return pending?1:0;}
static int fixture_clock(clockid_t c,struct timespec *t){(void)c;t->tv_sec=fixture_now/1000;t->tv_nsec=(fixture_now%1000)*1000000;return 0;}
static int fixture_close(int fd){if(fd>=4&&fd<=7)closed_mask|=1<<(fd-4);return 0;}
static ssize_t fixture_send(int fd,const void*p,size_t n,int flags){(void)fd;(void)flags;assert(n<sizeof reply);memcpy(reply,p,n);reply[n]=0;if(!strncmp(reply,"CAL_DIAG_",9))assert(closed_mask==15);return n;}
#define close fixture_close
#define read fixture_read
#define ioctl fixture_ioctl
#define poll fixture_poll
#define clock_gettime fixture_clock
#define send fixture_send
#define main unused_collector_main
#include "BROKER"
#undef main
int main(void){
 device_count=1;device_categories[0]=CATEGORY_KEYBOARD|CATEGORY_POINTER;
 for(int scenario=0;scenario<2;scenario++){
  calibrating=true;calibrated=armed=false;calibration_time=0;calibration_seen=3;calibration_last_activity=1000;
  memset(&calibration_diag,0,sizeof calibration_diag);calibration_diag.held_seen=true;
  for(fixture_now=1500;fixture_now<=31000;fixture_now+=500){
   fixture_event=(struct input_event){.time={fixture_now/1000,(fixture_now%1000)*1000},.type=scenario?EV_REL:EV_MSC,.code=scenario?REL_X:MSC_TIMESTAMP,.value=0};
   have_event=1;assert(drain(4)==0);assert(calibration_tick(fixture_now)==0);
   assert(calibration_seen==3);assert(!calibrated);assert(calibration_diag.quiet_blocked);assert(!calibration_diag.held_last);
  }
  closed_mask=0;assert(command("REPORT")==3);assert(strlen(reply)==34);
  assert(!strncmp(reply,"CAL_DIAG_11111010\n",18));
  assert(!strcmp(reply+18,scenario?"CAL_IDLE_ZRR000\n":"CAL_IDLE_CRR000\n"));
 }
 /* Pure SYN/queued-boundary traffic can produce the same quiet bit, without
  * any recent recognized activity or timer reset. */
 for(int mask=1;mask<=4;mask*=2){
  calibrating=true;calibrated=false;calibration_seen=3;calibration_last_activity=1000;fixture_now=31000;pending=mask;
  assert(calibration_tick(fixture_now)==0);assert(!calibrated);assert(calibration_diag.quiet_blocked);
  closed_mask=0;assert(command("REPORT")==3);
  assert(!strcmp(reply+18,mask==1?"CAL_IDLE_ZSQ100\n":mask==2?"CAL_IDLE_ZSQ010\n":"CAL_IDLE_ZSQ001\n"));
 }
 pending=0;calibrating=true;assert(calibration_tick(fixture_now)==0);assert(calibrated);
 /* Diagnostic classification never changes armed cancellation. */
 unsigned types[]={EV_KEY,EV_REL,EV_ABS,EV_SW,EV_MSC};
 for(unsigned i=0;i<sizeof(types)/sizeof(types[0]);i++){
  calibrating=calibrated=false;armed=true;arm_time=fixture_now;
  fixture_event=(struct input_event){.time={fixture_now/1000,0},.type=types[i],.value=0};
  have_event=1;assert(drain(4)==1);
 }
 return 0;
}
'''.replace('BROKER',str(root/'broker.c'))
class QuietDiagnosticTests(unittest.TestCase):
    def test_metadata_zero_motion_pending_queues_and_armed_guard(self):
        with tempfile.TemporaryDirectory(prefix='quiet-gate-audit-') as directory:
            path=pathlib.Path(directory);(path/'fixture.c').write_text(source)
            subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',str(path/'fixture.c'),'-o',str(path/'fixture')],check=True)
            subprocess.run([str(path/'fixture')],check=True)

if __name__=='__main__':unittest.main()
