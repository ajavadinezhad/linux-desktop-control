"""Compile-only fixture tests; never open real input devices or run a broker."""
import pathlib
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
COMPILER = shutil.which(os.environ.get('CC', 'cc')) or shutil.which('gcc') or shutil.which('clang')


@unittest.skipUnless(COMPILER, 'C compiler unavailable; collector is NOT build-validated')
class CollectorTests(unittest.TestCase):
    def test_full_collector_calibration_report_closes_fake_sources_without_arm(self):
        source = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/input.h>
#include <poll.h>
#include <signal.h>
#include <stdarg.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
static uid_t fake_uid(void) { return 65534; }
static int fake_sockopt(int fd,int level,int option,void *out,socklen_t *size) {
    (void)level;
    if(fd==3 && option==SO_TYPE) *(int*)out=SOCK_STREAM;
    else if(fd==5 && option==SO_DOMAIN) *(int*)out=AF_NETLINK;
    else return -1;
    *size=sizeof(int); return 0;
}
static int fake_ioctl(int fd,unsigned long request,...) {
    assert(fd==4 || fd==7);
    va_list ap;va_start(ap,request);void *out=va_arg(ap,void*);va_end(ap);
    if(request==EVIOCGVERSION) { *(int*)out=0x10001;return 0; }
    if(request==EVIOCSCLOCKID) { assert(fd==4);return 0; }
    if(request==EVIOCGKEY((KEY_MAX+8)/8)) {
        assert(fd==7);memset(out,0,(KEY_MAX+8)/8);return 0;
    }
    return -1;
}
static ssize_t fake_send(int fd,const void *p,size_t n,int flags) { (void)flags;return write(fd,p,n); }
static ssize_t fake_recv(int fd,void *p,size_t n,int flags) { (void)flags;return read(fd,p,n); }
#define getuid fake_uid
#define geteuid fake_uid
#define getsockopt fake_sockopt
#define ioctl fake_ioctl
#define send fake_send
#define recv fake_recv
#define main collector_main
#include "broker.c"
#undef main
static void line(int fd,const char *expected) {
    char out[64];size_t used=0;
    while(used<sizeof(out)-1) {
        struct pollfd p={fd,POLLIN,0};assert(poll(&p,1,2000)==1);
        assert(read(fd,out+used,1)==1);
        if(out[used++]=='\n')break;
    }
    out[used]=0;assert(strcmp(out,expected)==0);
}
int main(void) {
    int control[2], stream[2], topology[2], peer[2], snapshot[2];
    assert(socketpair(AF_UNIX,SOCK_STREAM,0,control)==0);
    assert(pipe2(stream,O_NONBLOCK)==0);assert(pipe(topology)==0);
    assert(pipe(peer)==0);assert(pipe2(snapshot,O_NONBLOCK)==0);
    pid_t child=fork();assert(child>=0);
    if(!child) {
        int original[]={control[0],stream[0],topology[0],peer[0],snapshot[0]}, keep[5];
        for(int i=0;i<5;i++)assert((keep[i]=fcntl(original[i],F_DUPFD_CLOEXEC,128))>=128);
        for(int fd=3;fd<128;fd++)close(fd);
        for(int i=0;i<5;i++){assert(dup2(keep[i],3+i)==3+i);close(keep[i]);}
        device_categories[0]=CATEGORY_KEYBOARD|CATEGORY_POINTER;
        char *args[]={"fixture","1",NULL};_exit(collector_main(2,args));
    }
    close(control[0]);close(stream[0]);close(topology[0]);close(peer[0]);close(snapshot[0]);
    line(control[1],"READY\n");assert(write(control[1],"CALIBRATE\n",10)==10);
    line(control[1],"CALIBRATING\n");usleep(5000);
    long long stamp=now_ms();struct input_event event={0};
    event.time.tv_sec=stamp/1000;event.time.tv_usec=(stamp%1000)*1000;
    /* Clock-switch drop becomes visible with the next packet. Lost packet's
     * key must not supply challenge credit. */
    struct input_event lost[3] = {event,event,event};
    lost[0].type=EV_SYN;lost[0].code=SYN_DROPPED;
    lost[1].type=EV_KEY;lost[1].code=KEY_LEFTSHIFT;lost[1].value=1;
    lost[2].type=EV_SYN;lost[2].code=SYN_REPORT;
    assert(write(stream[1],lost,sizeof lost)==(ssize_t)sizeof lost);
    assert(write(control[1],"HB\n",3)==3);
    line(control[1],"CALIBRATION_RESET\n");line(control[1],"ALIVE\n");usleep(2000);
    stamp=now_ms();event.time.tv_sec=stamp/1000;event.time.tv_usec=(stamp%1000)*1000;
    event.type=EV_LED;event.code=LED_NUML;event.value=1;
    assert(write(stream[1],&event,sizeof event)==(ssize_t)sizeof event);
    assert(write(control[1],"HB\n",3)==3);line(control[1],"ALIVE\n");
    event.type=EV_KEY;event.code=KEY_LEFTSHIFT;event.value=1;
    assert(write(stream[1],&event,sizeof event)==(ssize_t)sizeof event);
    assert(write(control[1],"HB\n",3)==3);line(control[1],"ALIVE\n");
    assert(write(control[1],"REPORT\n",7)==7);
    line(control[1],"CAL_DIAG_10110000\n");
    signal(SIGPIPE,SIG_IGN);
    assert(write(stream[1],&event,sizeof event)==-1 && errno==EPIPE);
    int status;assert(waitpid(child,&status,0)==child);assert(WIFEXITED(status)&&WEXITSTATUS(status)==0);
    close(control[1]);close(stream[1]);close(topology[1]);close(peer[1]);close(snapshot[1]);
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='collector-runtime-') as directory:
            path = pathlib.Path(directory)
            (path / 'fixture.c').write_text(source)
            build = subprocess.run([COMPILER, '-std=c11', '-Wall', '-Wextra', '-Werror',
                                    '-I', str(ROOT), str(path / 'fixture.c'), '-o', str(path / 'fixture')],
                                   capture_output=True, timeout=20)
            self.assertEqual(build.returncode, 0, build.stderr.decode(errors='replace'))
            result = subprocess.run([str(path / 'fixture')], capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))

    def test_parser_and_metadata_classifier(self):
        source = r'''
#define _GNU_SOURCE
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <linux/input.h>
#include <stdarg.h>
#include <string.h>
#include <assert.h>
#include <fcntl.h>
#include <unistd.h>
#include <poll.h>
static int fixture_held_fd = -1, fixture_query_error, fixture_queries, fixture_code = KEY_MAX;
static int fixture_quiet, fixture_capture;
static int fixture_fill_budget;
static char fixture_reply[32];
static ssize_t fixture_read(int fd, void *data, size_t size) {
    if (fixture_fill_budget) {
        assert(size % sizeof(struct input_event) == 0);
        struct input_event event = {.type = EV_SYN, .code = SYN_REPORT};
        for(size_t i=0;i<size;i+=sizeof event) memcpy((char*)data+i,&event,sizeof event);
        return (ssize_t)size;
    }
    return read(fd, data, size);
}
#define read fixture_read
static int fixture_poll(struct pollfd *fds, nfds_t count, int timeout) {
    if (fixture_quiet) return 0;
    return poll(fds, count, timeout);
}
#define poll fixture_poll
static int fixture_ioctl(int fd, unsigned long request, ...) {
    assert(fd == 7); /* one-device snapshot descriptor; never primary stream4 */
    unsigned char empty[(KEY_MAX + 8) / 8] = {0};
    if (request != EVIOCGKEY(sizeof empty) || fixture_query_error) return -1;
    va_list args; va_start(args, request); unsigned char *out = va_arg(args, unsigned char *); va_end(args);
    memcpy(out, empty, sizeof empty); ++fixture_queries;
    if (fd == fixture_held_fd) out[fixture_code / 8] |= 1U << (fixture_code % 8);
    return 0;
}
#define ioctl fixture_ioctl
/* Restricted test sandbox denies sendto even on socketpair. Production keeps
 * MSG_NOSIGNAL; this parser-only harness substitutes a fixture transport write. */
static ssize_t fixture_send(int fd, const void *data, size_t size, int flags) {
    if (fixture_capture) {
        assert(size < sizeof fixture_reply);
        memcpy(fixture_reply, data, size); fixture_reply[size] = 0;
        return (ssize_t)size;
    }
    (void)flags; return write(fd, data, size);
}
#define send fixture_send
#define main collector_production_main
#include "broker.c"
#undef main
#include <assert.h>
int main(void) {
    assert(expiry_phase(1999, 1000, 0) == 0);
    assert(expiry_phase(2000, 1000, 0) == 17); /* exact heartbeat boundary */
    assert(expiry_phase(119999, 119999, 0) == 0);
    assert(expiry_phase(120000, 120000, 0) == 18); /* live heartbeat, lease over */
    assert(expiry_phase(120000, 0, 0) == 18); /* both expired: absolute wins */
    assert(expiry_phase(-1, 0, 0) == 19);
    assert(expiry_phase(999, 1000, 0) == 19);
    assert(20 + expiry_phase(2000, 1000, 0) == 37);
    assert(20 + expiry_phase(120000, 120000, 0) == 38);
    int stream_pipe[2], snapshot_pipe[2];
    assert(pipe2(stream_pipe, O_NONBLOCK) == 0);
    assert(pipe2(snapshot_pipe, O_NONBLOCK) == 0);
    int stream_copy = fcntl(stream_pipe[0], F_DUPFD_CLOEXEC, 128);
    int snapshot_copy = fcntl(snapshot_pipe[0], F_DUPFD_CLOEXEC, 128);
    assert(stream_copy >= 128 && snapshot_copy >= 128);
    close(stream_pipe[0]); close(stream_pipe[1]);
    close(snapshot_pipe[0]); close(snapshot_pipe[1]);
    assert(dup2(stream_copy, 4) == 4); assert(dup2(snapshot_copy, 7) == 7);
    close(stream_copy); close(snapshot_copy);
    device_count = 1;
    assert(held_state() == 0); assert(fixture_queries == 1);
    fixture_held_fd = 7; assert(held_state() == 1);
    fixture_held_fd = -1; assert(held_state() == 0);
    fixture_query_error = 1; assert(held_state() == -1);
    fixture_query_error = 0;
    device_categories[0] = CATEGORY_KEYBOARD | CATEGORY_POINTER;
    struct input_event category = {.type = EV_KEY, .code = KEY_A, .value = 1};
    assert(event_category(0, &category) == CATEGORY_KEYBOARD);
    category.value = 0; assert(event_category(0, &category) == 0);
    category.value = 2; assert(event_category(0, &category) == 0);
    category.value = 1;
    category.code = KEY_POWER; assert(event_category(0, &category) == 0);
    category.code = KEY_SLEEP; assert(event_category(0, &category) == 0);
    category.code = BTN_LEFT; assert(event_category(0, &category) == CATEGORY_POINTER);
    category.type = EV_REL; assert(event_category(0, &category) == CATEGORY_POINTER);
    category.value = 0; assert(event_category(0, &category) == 0);
    category.type = EV_ABS; category.value = 50; assert(event_category(0, &category) == 0);
    category.type = EV_REL; category.value = 1;
    device_categories[0] = 0; assert(event_category(0, &category) == 0);
    device_categories[0] = CATEGORY_KEYBOARD | CATEGORY_POINTER;
    calibrating = true; calibrated = false; calibration_seen = 0;
    fixture_quiet = fixture_capture = 1;
    assert(command("ARM") == -1); /* no implicit challenge bypass */
    calibration_last_activity = 1000;
    assert(calibration_tick(2000) == 0); assert(!calibrated);
    calibration_note(CATEGORY_KEYBOARD, 1000);
    assert(calibration_tick(2000) == 0); assert(!calibrated);
    fixture_held_fd = 7; fixture_code = KEY_POWER;
    assert(held_state() == 1); assert(calibration_seen == CATEGORY_KEYBOARD);
    fixture_code = BTN_LEFT; assert(held_state() == 1);
    assert(calibration_seen == (CATEGORY_KEYBOARD | CATEGORY_POINTER));
    fixture_held_fd = -1; calibration_last_activity = 1000;
    assert(calibration_tick(1149) == 0); assert(!calibrated);
    assert(calibration_tick(1150) == 0); assert(calibrated && !calibrating);
    assert(strcmp(fixture_reply, "CALIBRATED\n") == 0);
    calibrating = true; calibrated = false; fixture_query_error = 1;
    assert(calibration_tick(2000) == -1);
    fixture_query_error = 0; calibrating = false; calibration_seen = 0;
    fixture_quiet = fixture_capture = 0;
    fixture_query_error = 0; device_count = 0; close(4); close(7);
    assert(count_arg("1") == 1); assert(count_arg("64") == 64);
    assert(count_arg("0") == -1); assert(count_arg("65") == -1);
    assert(count_arg("-1") == -1); assert(count_arg("1junk") == -1);
    assert(count_arg("9999999999999999") == -1);
    struct input_event e = {0};
    e.type = EV_KEY; e.code = KEY_A; e.value = 1; assert(classify(&e) == 1);
    e.value = 0; assert(classify(&e) == 1);
    e.type = EV_REL; assert(classify(&e) == 1);
    e.type = EV_ABS; assert(classify(&e) == 1);
    e.type = EV_SYN; e.code = SYN_REPORT; assert(classify(&e) == 0);
    e.code = SYN_DROPPED; assert(classify(&e) == -1);
    e.type = EV_MAX + 1; assert(classify(&e) == -1);
    unsigned feedback[] = {EV_LED, EV_REP, EV_SND, EV_FF, EV_FF_STATUS};
    for(unsigned i=0;i<sizeof feedback/sizeof *feedback;i++) {
        e.type=feedback[i]; assert(classify(&e)==2);
    }
    int p[2]; assert(pipe2(p, O_NONBLOCK) == 0);
    e.type = EV_KEY; e.code = KEY_B; e.value = 1;
    long long stamp = now_ms(); e.time.tv_sec = stamp / 1000; e.time.tv_usec = (stamp % 1000) * 1000;
    /* This pipe's fd3 is not a production stream index: move it to fd4. */
    int read_copy = fcntl(p[0], F_DUPFD_CLOEXEC, 128);
    int write_copy = fcntl(p[1], F_DUPFD_CLOEXEC, 128);
    close(p[0]); close(p[1]); assert(dup2(read_copy, 4) == 4);
    close(read_copy); p[0] = 4; p[1] = write_copy;
    device_count=1; armed=false; calibrated=false; calibrating=true;
    calibration_seen=CATEGORY_KEYBOARD|CATEGORY_POINTER;
    calibration_reset_pending=false;calibration_reset_rounds=0;
    struct input_event lost[3] = {e,e,e};
    lost[0].type=EV_SYN;lost[0].code=SYN_DROPPED;
    lost[1].type=EV_KEY;lost[1].code=KEY_LEFTSHIFT;lost[1].value=1;
    lost[2].type=EV_SYN;lost[2].code=SYN_REPORT;
    assert(write(p[1],lost,sizeof lost)==(ssize_t)sizeof lost);
    assert(drain(p[0])==0); assert(calibration_seen==0);
    assert(calibration_reset_pending && !calibration_resync[0]);
    assert(command("ARM")==-1);
    fixture_quiet=fixture_capture=1;
    assert(calibration_tick(now_ms())==0);
    assert(strcmp(fixture_reply,"CALIBRATION_RESET\n")==0);
    assert(!calibration_reset_pending && calibration_seen==0);
    assert(command("ARM")==-1);usleep(2000);
    stamp=now_ms();e.time.tv_sec=stamp/1000;e.time.tv_usec=(stamp%1000)*1000;
    assert(write(p[1],&e,sizeof e)==(ssize_t)sizeof e);
    assert(drain(p[0])==0);assert(calibration_seen==CATEGORY_KEYBOARD);
    assert(command("ARM")==-1);
    e.type=EV_REL;
    assert(write(p[1],&e,sizeof e)==(ssize_t)sizeof e);
    assert(drain(p[0])==0);
    assert(calibration_tick(now_ms()+150)==0);assert(calibrated);
    assert(command("ARM")==0);assert(armed);
    assert(write(p[1],lost,sizeof lost)==(ssize_t)sizeof lost);
    assert(drain(p[0])==-1);assert(collector_phase==42); /* armed drop never resyncs */
    armed=false;calibrated=false;calibrating=true;calibration_reset_pending=false;
    assert(write(p[1],lost,sizeof lost)==(ssize_t)sizeof lost);
    assert(drain(p[0])==0);assert(calibration_tick(now_ms())==0); /* second reset */
    assert(write(p[1],lost,sizeof lost)==(ssize_t)sizeof lost);
    assert(drain(p[0])==-1);assert(collector_phase==42); /* third round refuses */
    calibration_reset_pending=false;calibration_reset_rounds=0;
    memset(calibration_resync,0,sizeof calibration_resync);
    fixture_quiet=fixture_capture=0; device_count=0; e.type=EV_KEY;
    armed = false; calibrating = true; calibration_seen = 0;
    calibration_time = stamp + 1000;
    assert(write(p[1], &e, sizeof e) == (ssize_t)sizeof e);
    assert(drain(p[0]) == 0); assert(calibration_seen == 0); /* stale excluded */
    calibration_time = stamp;
    assert(write(p[1], &e, sizeof e) == (ssize_t)sizeof e);
    assert(drain(p[0]) == 0); assert(calibration_seen == 0); /* equal-ms stale */
    calibration_time = stamp - 1;
    assert(write(p[1], &e, sizeof e) == (ssize_t)sizeof e);
    assert(drain(p[0]) == 0); assert(calibration_seen == CATEGORY_KEYBOARD);
    e.type = EV_REL;
    assert(write(p[1], &e, sizeof e) == (ssize_t)sizeof e);
    assert(drain(p[0]) == 0); assert(calibration_seen == (CATEGORY_KEYBOARD | CATEGORY_POINTER));
    calibrating = false; e.type = EV_KEY;
    assert(write(p[1], &e, sizeof e) == (ssize_t)sizeof e);
    armed = false; assert(drain(p[0]) == 0);
    stamp = now_ms(); e.time.tv_sec = stamp / 1000; e.time.tv_usec = (stamp % 1000) * 1000;
    e.type = EV_LED;
    assert(write(p[1], &e, sizeof e) == (ssize_t)sizeof e);
    armed = true; arm_time = stamp; assert(drain(p[0]) == 0); /* feedback isn't takeover */
    e.type = EV_KEY;
    assert(write(p[1], &e, sizeof e) == (ssize_t)sizeof e);
    armed = true; arm_time = stamp; assert(drain(p[0]) == 1);
    e.type=EV_SYN; e.code=SYN_DROPPED;
    assert(write(p[1], &e, sizeof e) == (ssize_t)sizeof e);
    assert(drain(p[0]) == -1); assert(collector_phase == 42);
    e.type=EV_MAX+1;
    assert(write(p[1], &e, sizeof e) == (ssize_t)sizeof e);
    assert(drain(p[0]) == -1); assert(collector_phase == 44);
    e.type=EV_KEY; e.code=KEY_B; e.time.tv_sec=(now_ms()+5000)/1000;
    assert(write(p[1], &e, sizeof e) == (ssize_t)sizeof e);
    assert(drain(p[0]) == -1); assert(collector_phase == 45);
    armed=false; calibrated=true;
    assert(write(p[1], &e, sizeof e) == (ssize_t)sizeof e);
    assert(drain(p[0]) == -1); assert(collector_phase == 46); calibrated=false;
    assert(write(p[1], "x", 1) == 1); assert(drain(p[0]) == -1); assert(collector_phase == 41);
    close(p[1]); assert(drain(p[0]) == -1); assert(collector_phase == 41); close(p[0]);
    assert(drain(-1)==-1); assert(collector_phase==40);
    fixture_fill_budget=1; assert(drain(-1)==-1); assert(collector_phase==47); fixture_fill_budget=0;
    control_used = 0;
    assert(feed_control("CL", 2) == 0); assert(control_used == 2);
    assert(feed_control("OSE\n", 4) == 2); assert(control_used == 0);
    assert(feed_control("UNKNOWN\n", 8) == -1);
    int sockets[2]; assert(socketpair(AF_UNIX, SOCK_STREAM, 0, sockets) == 0);
    assert(sockets[0] == CONTROL); heartbeat = now_ms();
    control_used = 0; assert(feed_control("H", 1) == 0);
    assert(feed_control("B\nHB\n", 5) == 0);
    char replies[12]; assert(read(sockets[1], replies, 12) == 12);
    assert(memcmp(replies, "ALIVE\nALIVE\n", 12) == 0);
    assert(feed_control("FAULT\n", 6) == -1);
    close(sockets[0]); close(sockets[1]);
    control_used = 0; assert(feed_control("\0", 1) == -1);
    assert(feed_control("AAAAAAAAAAAAAAAAAAAA", 20) == -1);
    /* Terminal calibration diagnostics never grant calibration/ARM. */
    fixture_capture = fixture_quiet = 1;
    armed = false; calibrating = true; calibrated = false;
    device_count = 0; calibration_seen = 0;
    memset(&calibration_diag, 0, sizeof calibration_diag);
    assert(command("REPORT") == 3);
    assert(strcmp(fixture_reply, "CAL_DIAG_00000000\n") == 0);
    assert(strlen(fixture_reply) == 18); assert(!calibrated && !calibrating);
    assert(command("REPORT") == -1); assert(command("ARM") == -1);
    assert(collector_phase == 28);
    calibrating = false; calibrated = true;
    assert(command("REPORT") == 3); /* CALIBRATED raced controller timeout */
    assert(!calibrated && !calibrating);
    assert(strcmp(fixture_reply, "CAL_DIAG_00000000\n") == 0);
    assert(command("ARM") == -1);
    calibrating = true; armed = true; assert(command("REPORT") == -1); armed = false;
    assert(collector_phase == 28);
    calibration_seen = CATEGORY_KEYBOARD | CATEGORY_POINTER;
    calibration_last_activity = 1000;
    assert(calibration_tick(1149) == 0); assert(calibration_diag.quiet_blocked);
    /* Non-credit noise postpones quiet without manufacturing category credit. */
    calibration_note(0, 1149);
    assert(calibration_tick(1250) == 0); assert(calibration_diag.quiet_blocked);
    calibration_diag.stream_record = true; calibration_diag.query_success = true;
    calibration_diag.held_seen = true; calibration_diag.held_last = false;
    calibration_diag.stale_timestamp = true;
    int terminal_pipe[2]; assert(pipe(terminal_pipe) == 0);
    assert(dup2(terminal_pipe[0], 7) == 7);
    close(terminal_pipe[0]); close(terminal_pipe[1]); device_count = 1;
    assert(command("REPORT") == 3);
    assert(strcmp(fixture_reply, "CAL_DIAG_11111011\n") == 0);
    assert(fcntl(7, F_GETFD) == -1 && errno == EBADF);
    assert(!calibrated && !calibrating); assert(command("ARM") == -1);
    calibrating = true; fixture_capture = 0;
    assert(command("REPORT") == -1); assert(collector_phase == 27);
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='collector-unit-') as directory:
            path = pathlib.Path(directory)
            (path / 'fixture.c').write_text(source)
            subprocess.run([COMPILER, '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-I', str(ROOT), str(path / 'fixture.c'), '-o', str(path / 'fixture')],
                           check=True, capture_output=True, timeout=20)
            result = subprocess.run([str(path / 'fixture')], capture_output=True, timeout=3)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
