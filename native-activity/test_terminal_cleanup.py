"""Compile real terminal paths against fake I/O; no bus/devices/privilege."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest


class TerminalCleanupTests(unittest.TestCase):
    def test_input_closed_before_bus_and_report_without_library_teardown(self):
        directory = Path(__file__).resolve().parent
        source = r'''
#define _GNU_SOURCE
#include <systemd/sd-bus.h>
#include <unistd.h>
#include <string.h>
#include <sys/socket.h>
static int closed_fds[16], closed_count, teardown, processed, reported;
static int fake_close(int fd){closed_fds[closed_count++]=fd;return 0;}
static sd_bus_slot *fake_slot_unref(sd_bus_slot *s){(void)s;teardown++;return 0;}
static void fake_bus_close(sd_bus *b){(void)b;teardown++;}
static sd_bus *fake_bus_unref(sd_bus *b){(void)b;teardown++;return 0;}
static int fake_get_fd(sd_bus *b){(void)b;return 9;}
static int fake_process(sd_bus *b,sd_bus_message **m){(void)b;(void)m;processed++;return 0;}
static int fake_is_open(sd_bus *b){(void)b;processed++;return 1;}
static ssize_t fake_send(int fd,const void *p,size_t n,int flags){
 (void)p;(void)flags;
 if(fd!=3||closed_count!=5||closed_fds[0]!=4||closed_fds[1]!=5||closed_fds[2]!=6||closed_fds[3]!=7||closed_fds[4]!=9)return -1;
 if(n!=23||memcmp(p,"ACTIVITY\nOBS_DIAG_0000\n",23))return -1;
 reported++;return (ssize_t)n;
}
#define close fake_close
#define send fake_send
#define sd_bus_slot_unref fake_slot_unref
#define sd_bus_close fake_bus_close
#define sd_bus_unref fake_bus_unref
#define sd_bus_get_fd fake_get_fd
#define sd_bus_process fake_process
#define sd_bus_is_open fake_is_open
#include WATCH
#define LDC_NATIVE_WATCH
#define LDC_ACTIVITY_CONFINEMENT_H
static int confine_collector(void){return 0;}
#define main unused_collector_main
#include BROKER
#undef main
int main(void){
 device_count=1;
 session_watch_state.bus=(sd_bus*)1;
 session_watch_state.healthy=true;
 if(session_watch_fd()!=9)return 1;
 if(report("ACTIVITY\n")||reported!=1||teardown||processed)return 2;
 if(!session_watch_state.terminal||session_watch_state.healthy||session_watch_state.io_fd!=-1)return 3;
 if(session_watch_ok()||session_watch_fd()!=-1||session_watch_open("1"))return 4;
 session_watch_close(); session_watch_stop_io();
 if(teardown||processed||closed_count!=5)return 5;
 return 0;
}
'''.replace("#include WATCH", '#include "' + str(directory / "session_watch.h") + '"').replace(
            "#include BROKER", '#include "' + str(directory / "broker.c") + '"')
        compiler = shlex.split(os.environ.get("CC", "cc"))
        with tempfile.TemporaryDirectory(prefix="ldc-terminal-") as temporary:
            binary = Path(temporary) / "check"
            build = subprocess.run(compiler + shlex.split(os.environ.get("CFLAGS", "")) +
                                   ["-Wall", "-Wextra", "-Werror", "-x", "c", "-o", str(binary), "-",
                                    "-x", "none", "/usr/lib/x86_64-linux-gnu/libsystemd.so.0"],
                                   input=source, text=True, capture_output=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            result = subprocess.run([str(binary)], timeout=5, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
