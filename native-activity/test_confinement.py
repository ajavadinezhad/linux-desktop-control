"""Unprivileged fake-FD seccomp checks; opens no input devices or real bus.

Run with CC=/path/to/compiler python3 test_confinement.py.
"""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest


class ConfinementTests(unittest.TestCase):
    def test_full_collector_report_under_real_filter_fake_evdev(self):
        broker = Path(__file__).with_name("broker.c").resolve()
        source = r'''
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/input.h>
#include <poll.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <unistd.h>
static int session_watch_fd(void){return 8;}
static int session_watch_ok(void){return 1;}
static void session_watch_stop_io(void){close(8);}
static int fake_getsockopt(int fd,int level,int opt,void *p,socklen_t *len){
 (void)level;(void)len;
 if(fd==3&&opt==SO_TYPE){*(int*)p=SOCK_STREAM;return 0;}
 if(fd==5&&opt==SO_DOMAIN){*(int*)p=AF_NETLINK;return 0;}
 errno=EINVAL;return -1;
}
static int fake_ioctl(int fd,unsigned long request,...){
 va_list ap;va_start(ap,request);void *p=va_arg(ap,void*);va_end(ap);
 if(fd!=4&&fd!=7){errno=EBADF;return -1;}
 if(request==EVIOCGVERSION){*(int*)p=0x10001;return 0;}
 if(request==EVIOCSCLOCKID)return 0;
 if(fd==7&&(request&0xc000ffffU)==EVIOCGKEY(0)){memset(p,0,_IOC_SIZE(request));return 0;}
 errno=EINVAL;return -1;
}
/* This environment independently denies sendto even on socketpair. Substitute
 * write on the same control socket only; confinement itself is not stubbed. */
static ssize_t fake_send(int fd,const void *p,size_t n,int flags){(void)flags;return write(fd,p,n);}
#define getsockopt fake_getsockopt
#define ioctl fake_ioctl
#define send fake_send
#define LDC_NATIVE_WATCH
#define main collector_entry
#include BROKER
#undef main
static int line(int fd,const char *expected){
 char result[64];size_t n=0;
 while(n<sizeof result-1){struct pollfd f={fd,POLLIN,0};if(poll(&f,1,2000)<=0)return 0;
  if(read(fd,result+n,1)!=1)return 0;if(result[n++]=='\n')break;}
 result[n]=0;return !strcmp(result,expected);
}
int main(void){
 int control[2],events[2],topology[2],parent[2];
 if(socketpair(AF_UNIX,SOCK_STREAM,0,control)||pipe2(events,O_NONBLOCK)||pipe2(topology,O_NONBLOCK)||pipe2(parent,O_NONBLOCK))return 1;
 pid_t child=fork();if(child<0)return 2;
 if(child==0){
  int original[]={control[0],events[0],topology[0],parent[0],events[0],parent[0]};
  int copy[6];for(int i=0;i<6;i++){copy[i]=fcntl(original[i],F_DUPFD_CLOEXEC,64);if(copy[i]<0)_exit(3);}
  for(int i=0;i<6;i++)if(dup2(copy[i],3+i)<0)_exit(4);
  char *args[]={"collector","1",NULL};_exit(collector_entry(2,args));
 }
 close(control[0]);
 if(!line(control[1],"READY\n"))return 10;
 if(write(control[1],"CALIBRATE\n",10)!=10||!line(control[1],"CALIBRATING\n"))return 11;
 if(write(control[1],"HB\n",3)!=3||!line(control[1],"ALIVE\n"))return 12;
 if(write(control[1],"REPORT\n",7)!=7||!line(control[1],"CAL_DIAG_00010000\n"))return 13;
 int status;if(waitpid(child,&status,0)!=child||!WIFEXITED(status)||WEXITSTATUS(status))return 14;
 return 0;
}
'''.replace("#include BROKER", '#include "' + str(broker) + '"')
        compiler = shlex.split(os.environ.get("CC", "cc"))
        with tempfile.TemporaryDirectory(prefix="ldc-full-confinement-") as directory:
            binary = Path(directory) / "check"
            build = subprocess.run(compiler + ["-Wall", "-Wextra", "-Werror", "-x", "c",
                                               "-o", str(binary), "-"],
                                   input=source, text=True, capture_output=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            child = subprocess.run([str(binary)], capture_output=True, timeout=10)
            self.assertEqual(child.returncode, 0,
                             f"full fake collector returned {child.returncode}: {child.stderr!r}")

    def test_permissions_with_fake_pipe_descriptors(self):
        header = Path(__file__).with_name("confinement.h").resolve()
        source = r'''
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/input.h>
#include <sys/ioctl.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <unistd.h>
#define CONTROL 3
#define MAX_DEVICES 64
static int device_count=1;
static int session_watch_fd(void) { return 9; }
#include HEADER
#define DENIED(expression, code) do { errno=0; if((expression)!=-1 || errno!=EPERM)return code; }while(0)
int main(void) {
    int p[2]; if(pipe(p))return 1;
    int reader=fcntl(p[0],F_DUPFD_CLOEXEC,21);
    int writer=fcntl(p[1],F_DUPFD_CLOEXEC,20);
    if(reader<0||writer<0||dup2(writer,3)<0||dup2(writer,7)<0||dup2(writer,9)<0)return 2;
    if(confine_collector())return 3;
    if(getpid()<=0||write(3,"x",1)!=1)return 4;
    char c; if(read(reader,&c,1)!=1||c!='x')return 5;
    DENIED(open("/dev/null",O_RDONLY),10);
    DENIED(socket(AF_INET,SOCK_STREAM,0),11);
    DENIED(dup(3),12);
    DENIED(write(writer,"x",1),13);
    DENIED(ioctl(4,EVIOCGRAB,1),14);
    DENIED(ioctl(3,EVIOCGKEY(8),&c),15);
    DENIED(ioctl(4,EVIOCGKEY(8),&c),25);
    DENIED(ioctl(5,EVIOCGKEY(8),&c),26);
    DENIED(ioctl(6,EVIOCGKEY(8),&c),27);
    DENIED(ioctl(8,EVIOCGKEY(8),&c),28);
    DENIED(ioctl(9,EVIOCGKEY(8),&c),29);
    DENIED(ioctl(7,EVIOCGRAB,1),30);
    DENIED(syscall(SYS_execve,"/nonexistent",(char*[]){0},(char*[]){0}),16);
    DENIED(syscall(SYS_clone,0,0,0,0,0),17);
    struct msghdr msg={0}; DENIED(sendmsg(3,&msg,0),18);
    unsigned char keys[8]; errno=0;
    if(ioctl(7,EVIOCGKEY(sizeof keys),keys)!=-1||errno!=ENOTTY)return 19;
    void *memory=mmap(0,4096,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    if(memory==MAP_FAILED)return 20;
    DENIED(mprotect(memory,4096,PROT_READ|PROT_EXEC),21);
    errno=0;
    if(mmap(0,4096,PROT_READ,MAP_PRIVATE,3,0)!=MAP_FAILED||errno!=EPERM)return 22;
    if(munmap(memory,4096))return 23;
    struct rlimit core; if(getrlimit(RLIMIT_CORE,&core)||core.rlim_cur||core.rlim_max)return 24;
    return 0;
}
'''.replace("HEADER", '"' + str(header) + '"')
        compiler = shlex.split(os.environ.get("CC", "cc"))
        with tempfile.TemporaryDirectory(prefix="ldc-confinement-") as directory:
            binary = Path(directory) / "check"
            build = subprocess.run(compiler + ["-Wall", "-Wextra", "-Werror", "-x", "c",
                                               "-o", str(binary), "-"],
                                   input=source, text=True, capture_output=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            child = subprocess.run([str(binary)], capture_output=True, timeout=5)
            self.assertEqual(child.returncode, 0,
                             f"fake collector check returned {child.returncode}: {child.stderr!r}")


if __name__ == "__main__":
    unittest.main()
