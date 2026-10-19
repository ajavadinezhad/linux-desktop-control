#define _GNU_SOURCE
/* Unprivileged collector only. The privileged opener owns device selection,
 * active-session checks and topology monitoring. No paths or input contents
 * cross this protocol. fd3: private control socket; fd4+: preopened evdev;
 * fd(4+count): topology netlink; fd(5+count): authenticated peer pidfd;
 * fd(6+count)..fd(5+2*count): separately opened snapshot evdev clients. */
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <linux/input.h>
#include <poll.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#define CONTROL 3
#define MAX_DEVICES 64
#define HEARTBEAT_MS 1000
#define SESSION_BUDGET_MS 120000
#define CALIBRATION_QUIET_MS 1500
static int device_count;
/* Exit status only: fixed stage identifiers, never device/input metadata. */
static int collector_phase;
#ifdef LDC_NATIVE_WATCH
#include "confinement.h"
#endif
static bool armed;
static bool pointer_yield_mode, pointer_yielded, pointer_quiet;
static bool pointer_strict_coverage, calibration_pointer_stream;
static unsigned pointer_epoch;
static long long pointer_last_motion;
#define POINTER_YIELD_MAX_EPOCH 64
#define POINTER_QUIET_MS 1500
static const char *stream_activity_message;
enum { CATEGORY_KEYBOARD = 1, CATEGORY_POINTER = 2 };
/* Filled only by the verified opener, not accepted from the requester. */
static unsigned device_categories[MAX_DEVICES];
static bool calibrating, calibrated;
static unsigned calibration_seen;
static long long calibration_time, calibration_last_activity;
static bool calibration_resync[MAX_DEVICES], calibration_reset_pending;
static unsigned calibration_reset_rounds;
static struct {
    bool stream_record, query_success, held_seen, held_last, quiet_blocked, stale_timestamp;
} calibration_diag;
/* Terminal-only coarse diagnostics; never exported while observing input. */
static char calibration_last_kind = 'N', calibration_quiet_reason = 'M';
static bool calibration_pending_input, calibration_pending_topology, calibration_pending_owner;
static long long heartbeat, arm_time, session_time;
static char control_line[16];
static size_t control_used;

static long long now_ms(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) return -1;
    return (long long)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}
/* Fixed exit-stage metadata only. Absolute expiry takes precedence if both
 * deadlines expired, so controller heartbeats cannot hide the lease cap. */
static int expiry_phase(long long current, long long last_heartbeat, long long started) {
    if (current < 0 || current < last_heartbeat || current < started) return 19;
    if (current - started >= SESSION_BUDGET_MS) return 18;
    if (current - last_heartbeat >= HEARTBEAT_MS) return 17;
    return 0;
}
static void close_devices(void) {
    for (int i = 0; i < 2 * device_count + 2; ++i) close(4 + i);
#ifdef LDC_NATIVE_WATCH
    session_watch_stop_io();
#endif
}
static int report(const char *message) {
    /* Close every input descriptor before reporting a terminal condition. */
    close_devices();
    ssize_t n = send(CONTROL, message, strlen(message), MSG_NOSIGNAL | MSG_DONTWAIT);
    return n == (ssize_t)strlen(message) ? 0 : -1;
}
static int fail(void) { report("FAULT\n"); return 20 + collector_phase; }
static int count_arg(const char *text) {
    if (!text || !*text) return -1;
    unsigned value = 0;
    for (const unsigned char *p = (const unsigned char *)text; *p; ++p) {
        if (*p < '0' || *p > '9' || value > MAX_DEVICES) return -1;
        value = value * 10 + *p - '0';
    }
    return value >= 1 && value <= MAX_DEVICES ? (int)value : -1;
}
/* Activity uses type/SYN_DROPPED only. Calibration additionally tests coarse
 * key/button groups, down-state and nonzero relative-motion flags internally;
 * no identities, values or coordinates are recorded or exported. */
static int classify(const struct input_event *event) {
    if (event->type == EV_SYN) return event->code == SYN_DROPPED ? -1 : 0;
    /* Kernel output/feedback can appear on an evdev reader, including LED and
     * repeat configuration sent by another client. It is neither physical
     * takeover nor a broken stream. Never inspect its payload. */
    if (event->type == EV_LED || event->type == EV_REP || event->type == EV_SND ||
        event->type == EV_FF || event->type == EV_FF_STATUS) return 2;
    if (event->type == EV_KEY || event->type == EV_REL || event->type == EV_ABS ||
        event->type == EV_SW || event->type == EV_MSC) return 1;
    return -1;
}
static const char *activity_message(const struct input_event *event) {
    if (event->type == EV_KEY) return "ACTIVITY_KEY\n";
    if (event->type == EV_REL || event->type == EV_ABS) return "ACTIVITY_POINTER\n";
    if (event->type == EV_SW) return "ACTIVITY_SWITCH\n";
    return "ACTIVITY_METADATA\n"; /* EV_MSC: retained fail-closed observation. */
}
static bool ordinary_key(unsigned code) {
    return code > KEY_RESERVED && code < BTN_MISC && code != KEY_POWER &&
           code != KEY_SLEEP && code != KEY_WAKEUP;
}
static unsigned event_category(int device, const struct input_event *event) {
    unsigned categories = device_categories[device];
    if (event->type == EV_KEY && event->value == 1 && ordinary_key(event->code))
        return categories & CATEGORY_KEYBOARD;
    if ((event->type == EV_KEY && event->value == 1 && event->code >= BTN_MISC) ||
        (event->type == EV_REL && event->value != 0) || event->type == EV_ABS)
        return categories & CATEGORY_POINTER;
    /* A fresh ABS record establishes only this verified pointer source path.
     * It does not attest motion, a button or human provenance. No ABS value
     * or coordinate history is inspected for this classification. */
    return 0;
}
static void calibration_note(unsigned categories, long long current) {
    if (!calibrating || calibration_reset_pending) return;
    calibration_seen |= categories;
    calibration_last_activity = current;
}
static char calibration_event_kind(const struct input_event *event) {
    if (event->type == EV_KEY) return 'K';
    if (event->type == EV_REL) return event->value ? 'R' : 'Z';
    if (event->type == EV_ABS) return 'A';
    if (event->type == EV_SW) return 'S';
    if (event->type == EV_MSC && event->code == MSC_TIMESTAMP) return 'C';
    return 'M';
}
static void calibration_note_kind(unsigned categories, long long current, char kind) {
    if (calibrating && !calibration_reset_pending) calibration_last_kind = kind;
    calibration_note(categories, current);
}
static int pointer_token(const char *prefix) {
    char message[32];
    int length = snprintf(message, sizeof message, "%s_%u\n", prefix, pointer_epoch);
    if (length <= 0 || (size_t)length >= sizeof message) return -1;
    return send(CONTROL, message, (size_t)length, MSG_NOSIGNAL | MSG_DONTWAIT) == length ? 0 : -1;
}
static bool positional_mouse_motion(int device, const struct input_event *event) {
    return device >= 0 && device < device_count &&
        (device_categories[device] & CATEGORY_POINTER) && event->type == EV_REL &&
        (event->code == REL_X || event->code == REL_Y) && event->value != 0;
}
static int pointer_motion(long long current) {
    if (!pointer_yielded || pointer_quiet) {
        if (++pointer_epoch > POINTER_YIELD_MAX_EPOCH) return -1;
        pointer_yielded = true; pointer_quiet = false;
        if (pointer_token("YIELDED")) return -1;
    }
    pointer_last_motion = current;
    return 0;
}
/* Drain with a strict bound: an unbounded producer must not starve control. */
static int drain(int fd) {
    unsigned consumed = 0, attempts = 0;
    while (consumed < 4096 && attempts++ < 4096) {
        struct input_event batch[64];
        size_t capacity = 4096 - consumed < 64 ? 4096 - consumed : 64;
        ssize_t n = read(fd, batch, capacity * sizeof *batch);
        if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) return 0;
        if (n < 0 && errno == EINTR) continue;
        if (n < 0) { collector_phase = 40; return -1; }
        if (!n || n % sizeof *batch) { collector_phase = 41; return -1; }
        unsigned records = (unsigned)((size_t)n / sizeof *batch);
        consumed += records;
        for (unsigned record = 0; record < records; ++record) {
            struct input_event event = batch[record];
            if (calibrating) {
                calibration_diag.stream_record = true;
                long long stamp = (long long)event.time.tv_sec * 1000 + event.time.tv_usec / 1000;
                if (stamp <= calibration_time) calibration_diag.stale_timestamp = true;
            }
            int kind = classify(&event);
            if (calibrating && !armed && event.type == EV_SYN && event.code == SYN_DROPPED) {
                int device = fd - 4;
                if (device < 0 || device >= device_count) { collector_phase = 42; return -1; }
                if (!calibration_reset_pending && ++calibration_reset_rounds > 2) {
                    collector_phase = 42; return -1;
                }
                calibration_reset_pending = true;
                calibration_resync[device] = true;
                calibration_seen = 0;
                calibration_pointer_stream = false;
                continue;
            }
            if (calibrating && !armed && fd >= 4 && fd < 4 + device_count && calibration_resync[fd - 4]) {
                if (event.type == EV_SYN && event.code == SYN_REPORT) calibration_resync[fd - 4] = false;
                continue;
            }
            if (kind < 0) {
                collector_phase = event.type == EV_SYN && event.code == SYN_DROPPED ? 42 : 44;
                return -1;
            }
            if (kind == 2) continue; /* Known output feedback: no calibration credit. */
            if (kind) {
                if (armed) {
                    long long stamp = (long long)event.time.tv_sec * 1000 + event.time.tv_usec / 1000;
                    if (stamp < arm_time || stamp > now_ms() + 1000) { collector_phase = 45; return -1; }
                    if (pointer_yield_mode && positional_mouse_motion(fd - 4, &event)) {
                        if (pointer_motion(now_ms())) return -1;
                        continue;
                    }
                    stream_activity_message = activity_message(&event);
                    return 1;
                }
                if (calibrated) { collector_phase = 46; return -1; }
                if (calibrating) {
                    long long stamp = (long long)event.time.tv_sec * 1000 + event.time.tv_usec / 1000;
                    long long current = now_ms();
                    if (current < 0 || stamp > current + 1000) { collector_phase = 45; return -1; }
                    if (stamp > calibration_time) {
                        if (!calibration_reset_pending && positional_mouse_motion(fd - 4, &event))
                            calibration_pointer_stream = true;
                        calibration_note_kind(event_category(fd - 4, &event), current, calibration_event_kind(&event));
                    }
                }
                /* Consent/authentication activity before ARM grants no input and
                 * is discarded. ARM separately requires every key released. */
            }
        }
    }
    collector_phase = 47;
    return -1;
}
/* Read only aggregate held state, including buttons; never identify/export a
 * bit. This supplements evdev delivery when another reader owns a grab.
 * It can miss a complete press/release between polls and keyless motion. */
static int held_state(void) {
    bool held = false;
    for (int i = 0; i < device_count; ++i) {
        unsigned char keys[(KEY_MAX + 8) / 8] = {0};
        /* EVIOCGKEY flushes this client's queued EV_KEY. Never query the
         * primary stream descriptor; dup() would share the same client. */
        if (ioctl(6 + device_count + i, EVIOCGKEY(sizeof keys), keys) < 0) return -1;
        if (calibrating) calibration_diag.query_success = true;
        bool any = false; unsigned categories = 0;
        for (unsigned code = 0; code <= KEY_MAX; ++code) {
            if (!(keys[code / 8] & (1U << (code % 8)))) continue;
            any = true;
            if (ordinary_key(code)) categories |= device_categories[i] & CATEGORY_KEYBOARD;
            if (code >= BTN_MISC) categories |= device_categories[i] & CATEGORY_POINTER;
        }
        if (any) {
            calibration_note_kind(categories, now_ms(), 'H');
            held = true;
        }
    }
    if (calibrating) {
        calibration_diag.held_last = held;
        calibration_diag.held_seen |= held;
    }
    return held ? 1 : 0;
}
static int calibration_tick(long long current) {
    if (!calibrating) return 0;
    calibration_pending_input = calibration_pending_topology = calibration_pending_owner = false;
    calibration_quiet_reason = 'M';
    int held = held_state();
    if (held < 0 || current < 0) return -1;
    if (calibration_reset_pending) {
        for (int i = 0; i < device_count; ++i) if (calibration_resync[i]) return 0;
        if (held) return 0;
        struct pollfd boundary[MAX_DEVICES + 2];
        for (int i = 0; i < device_count + 2; ++i)
            boundary[i] = (struct pollfd){4 + i, POLLIN, 0};
        int pending = poll(boundary, device_count + 2, 0);
        if (pending < 0) return -1;
        if (pending) return 0;
#ifdef LDC_NATIVE_WATCH
        if (!session_watch_ok()) return -1;
#endif
        calibration_seen = 0;
        calibration_pointer_stream = false;
        calibration_time = calibration_last_activity = now_ms();
        if (calibration_time < 0) return -1;
        calibration_reset_pending = false;
        calibration_last_kind = 'N';
        calibration_diag.quiet_blocked = false;
        return send(CONTROL, "CALIBRATION_RESET\n", 18, MSG_NOSIGNAL | MSG_DONTWAIT) == 18 ? 0 : -1;
    }
    bool missing = calibration_seen != (CATEGORY_KEYBOARD | CATEGORY_POINTER) || (pointer_strict_coverage && !calibration_pointer_stream);
    calibration_quiet_reason = held ? 'H' : missing ? 'M' : current - calibration_last_activity < CALIBRATION_QUIET_MS ? 'R' : 'Y';
    calibration_diag.quiet_blocked = !held &&
        calibration_seen == (CATEGORY_KEYBOARD | CATEGORY_POINTER) &&
        current - calibration_last_activity < CALIBRATION_QUIET_MS;
    if (held || missing || current - calibration_last_activity < CALIBRATION_QUIET_MS) return 0;
    struct pollfd boundary[MAX_DEVICES + 2];
    for (int i = 0; i < device_count + 2; ++i)
        boundary[i] = (struct pollfd){4 + i, POLLIN, 0};
    int pending = poll(boundary, device_count + 2, 0);
    if (pending < 0) return -1;
    if (pending) {
        calibration_quiet_reason = 'Q';
        for (int i = 0; i < device_count; ++i) calibration_pending_input |= boundary[i].revents != 0;
        calibration_pending_topology = boundary[device_count].revents != 0;
        calibration_pending_owner = boundary[device_count + 1].revents != 0;
        calibration_diag.quiet_blocked = true; return 0;
    }
#ifdef LDC_NATIVE_WATCH
    if (!session_watch_ok()) return -1;
#endif
    calibrating = false; calibrated = true;
    return send(CONTROL, "CALIBRATED\n", 11, MSG_NOSIGNAL | MSG_DONTWAIT) == 11 ? 0 : -1;
}
static int pointer_boundary(void) {
    if (held_state() != 0) return -1;
    struct pollfd boundary[MAX_DEVICES + 2];
    for (int i = 0; i < device_count + 2; ++i)
        boundary[i] = (struct pollfd){4 + i, POLLIN, 0};
    if (poll(boundary, device_count + 2, 0) != 0) return -1;
#ifdef LDC_NATIVE_WATCH
    if (!session_watch_ok()) return -1;
#endif
    return 0;
}
static int pointer_yield_tick(long long current) {
    if (!pointer_yielded || pointer_quiet) return 0;
    if (current < pointer_last_motion) return -1;
    if (current - pointer_last_motion < POINTER_QUIET_MS) return 0;
    /* A busy source is not proof of quiet. Main loop drains it first. */
    if (held_state() != 0) return -1;
    struct pollfd boundary[MAX_DEVICES + 2];
    for (int i = 0; i < device_count + 2; ++i)
        boundary[i] = (struct pollfd){4 + i, POLLIN, 0};
    int pending = poll(boundary, device_count + 2, 0);
    if (pending < 0) return -1;
    if (pending) return 0;
#ifdef LDC_NATIVE_WATCH
    if (!session_watch_ok()) return -1;
#endif
    pointer_quiet = true;
    return pointer_token("QUIET");
}
static int command(const char *line) {
    long long current = now_ms();
    if (current < 0) return -1;
    if (!strcmp(line, "CLOSE")) return 2;
    if (!strcmp(line, "MODEYIELD") || !strcmp(line, "MODEYIELD2")) {
        if (pointer_yield_mode || armed || calibrating || calibrated) return -1;
        pointer_yield_mode = true;
        pointer_strict_coverage = !strcmp(line, "MODEYIELD2");
        const char *reply = pointer_strict_coverage ? "MODEYIELD2_OK\n" : "MODEYIELD_OK\n";
        size_t length = strlen(reply);
        return send(CONTROL,reply,length,MSG_NOSIGNAL | MSG_DONTWAIT) == (ssize_t)length ? 0 : -1;
    }
    if (!strncmp(line, "RESUME_", 7)) {
        const char *epoch = line + 7; unsigned value = 0;
        if (!*epoch || *epoch == '0') return -1;
        for (const char *p = epoch; *p; ++p) {
            if (*p < '0' || *p > '9' || value > POINTER_YIELD_MAX_EPOCH) return -1;
            value = value * 10 + (unsigned)(*p - '0');
        }
        if (!pointer_yield_mode || !armed || !pointer_yielded || !pointer_quiet || value != pointer_epoch) return -1;
        if (expiry_phase(current, heartbeat, session_time)) return -1;
        /* No queued input is discarded to manufacture a successful resume. */
        if (pointer_boundary()) return -1;
        /* Snapshot/session queries may cross either existing deadline. */
        long long resumed_at = now_ms();
        if (expiry_phase(resumed_at, heartbeat, session_time)) return -1;
        pointer_yielded = pointer_quiet = false;
        arm_time = resumed_at;
        return pointer_token("ARMED");
    }
    if (!strcmp(line, "FAULT")) return -1; /* opener topology/session loss */
    if (!strcmp(line, "REPORT")) {
        collector_phase = 28;
        if (armed || (!calibrating && !calibrated)) return -1;
        char response[] = "CAL_DIAG_00000000\nCAL_IDLE_NNM000\n";
        bool bits[8] = {
            (calibration_seen & CATEGORY_KEYBOARD) != 0,
            (calibration_seen & CATEGORY_POINTER) != 0,
            calibration_diag.stream_record, calibration_diag.query_success,
            calibration_diag.held_seen, calibration_diag.held_last,
            calibration_diag.quiet_blocked, calibration_diag.stale_timestamp
        };
        for (unsigned i = 0; i < 8; ++i) response[9 + i] = bits[i] ? '1' : '0';
        response[27] = calibration_last_kind;
        response[28] = calibration_last_kind == 'N' ? 'N' : current - calibration_last_activity < CALIBRATION_QUIET_MS ? 'R' : 'S';
        response[29] = calibration_quiet_reason;
        response[30] = calibration_pending_input ? '1' : '0';
        response[31] = calibration_pending_topology ? '1' : '0';
        response[32] = calibration_pending_owner ? '1' : '0';
        collector_phase = 27;
        if (report(response)) return -1;
        calibrating = calibrated = false;
        return 3; /* terminal report already closed every source descriptor */
    }
    if (!strcmp(line, "CALIBRATE")) {
        if (armed || calibrating || calibrated) return -1;
#ifdef LDC_NATIVE_WATCH
        if (!session_watch_ok()) return -1;
#endif
        for (int i = 0; i < device_count; ++i) if (drain(4 + i)) return -1;
        if (held_state() != 0) return -1;
        calibration_seen = 0;
        calibration_pointer_stream = false;
        calibration_reset_pending = false;
        calibration_reset_rounds = 0;
        memset(calibration_resync, 0, sizeof calibration_resync);
        memset(&calibration_diag, 0, sizeof calibration_diag);
        calibration_last_kind = 'N'; calibration_quiet_reason = 'M';
        calibration_pending_input = calibration_pending_topology = calibration_pending_owner = false;
        calibration_time = calibration_last_activity = now_ms();
        if (calibration_time < 0) return -1;
        calibrating = true;
        return send(CONTROL, "CALIBRATING\n", 12, MSG_NOSIGNAL | MSG_DONTWAIT) == 12 ? 0 : -1;
    }
    if (!strcmp(line, "ARM")) {
        if (armed || calibrating || calibration_reset_pending || !calibrated ||
            (pointer_strict_coverage && !calibration_pointer_stream)) return -1;
        for (int i = 0; i < device_count; ++i) if (calibration_resync[i]) return -1;
#ifdef LDC_NATIVE_WATCH
        if (!session_watch_ok()) return -1;
#endif
        /* The queue is checked again at the activation boundary. */
        for (int i = 0; i < device_count; ++i) if (drain(4 + i)) return -1;
        if (held_state() != 0) return -1;
        /* Catch activity/topology queued during the state checks; no grace. */
        struct pollfd boundary[MAX_DEVICES + 2];
        for (int i = 0; i < device_count + 2; ++i)
            boundary[i] = (struct pollfd){4 + i, POLLIN, 0};
        if (poll(boundary, device_count + 2, 0) != 0) return -1;
#ifdef LDC_NATIVE_WATCH
        if (!session_watch_ok()) return -1;
#endif
        arm_time = now_ms();
        if (arm_time < 0) return -1;
        heartbeat = arm_time;
        armed = true;
        return send(CONTROL, "ARMED\n", 6, MSG_NOSIGNAL | MSG_DONTWAIT) == 6 ? 0 : -1;
    }
    if (!strcmp(line, "HB")) {
        if (current - heartbeat >= HEARTBEAT_MS) { collector_phase = 17; return -1; }
        heartbeat = current;
        return send(CONTROL, "ALIVE\n", 6, MSG_NOSIGNAL | MSG_DONTWAIT) == 6 ? 0 : -1;
    }
    return -1;
}
/* Unix streams may split/coalesce records. Bound each command and each read;
 * incomplete records never renew the heartbeat. */
static int feed_control(const char *data, size_t length) {
    for (size_t i = 0; i < length; ++i) {
        unsigned char c = (unsigned char)data[i];
        if (c == '\n') {
            if (!control_used) return -1;
            control_line[control_used] = 0;
            control_used = 0;
            int result = command(control_line);
            if (result) return result;
        } else {
            if (!((c >= 'A' && c <= 'Z') || c == '_' || (c >= '0' && c <= '9')) || control_used >= sizeof control_line - 1) return -1;
            control_line[control_used++] = (char)c;
        }
    }
    return 0;
}
static int verify(void) {
    collector_phase = 11;
    int type; socklen_t length = sizeof type;
    if (geteuid() == 0 || getuid() == 0 ||
        getsockopt(CONTROL, SOL_SOCKET, SO_TYPE, &type, &length) || type != SOCK_STREAM)
        return -1;
    collector_phase = 12;
    if (prctl(PR_SET_DUMPABLE, 0) || prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)) return -1;
    collector_phase = 13;
    int domain; length = sizeof domain;
    if (getsockopt(4 + device_count, SOL_SOCKET, SO_DOMAIN, &domain, &length) ||
        domain != AF_NETLINK || fcntl(5 + device_count, F_GETFD) == -1) return -1;
    struct rlimit limit;
    collector_phase = 14;
    if (getrlimit(RLIMIT_NOFILE, &limit) || limit.rlim_cur > 1048576) return -1;
    collector_phase = 15;
#ifdef LDC_NATIVE_WATCH
    int watch_fd = session_watch_fd();
    if (watch_fd < 6 + 2 * device_count) return -1;
#endif
    /* sd-bus may create auxiliary descriptors during setup. Retain only its
     * authenticated connection; no unexpected descriptor survives readiness.
     * Revalidate watch health after pruning, never assume auxiliaries optional. */
    for (unsigned long fd = 6 + 2 * device_count; fd < limit.rlim_cur; ++fd) {
#ifdef LDC_NATIVE_WATCH
        if ((int)fd == watch_fd) continue;
#endif
        if (close((int)fd) && errno != EBADF) return -1;
    }
#ifdef LDC_NATIVE_WATCH
    if (!session_watch_ok()) return -1;
#endif
    collector_phase = 16;
    for (int i = 0; i < device_count; ++i) {
        int descriptors[2] = {4 + i, 6 + device_count + i};
        for (int j = 0; j < 2; ++j) {
            int fd = descriptors[j], version = 0, flags = fcntl(fd, F_GETFL);
            if (flags < 0 || (flags & O_ACCMODE) != O_RDONLY || !(flags & O_NONBLOCK) ||
                ioctl(fd, EVIOCGVERSION, &version) || version <= 0) return -1;
        }
        int clock = CLOCK_MONOTONIC;
        if (ioctl(descriptors[0], EVIOCSCLOCKID, &clock)) return -1;
    }
    return 0;
}
int main(int argc, char **argv) {
    if (argc != 2 || (device_count = count_arg(argv[1])) < 0) return 1;
    if (verify()) return fail();
    collector_phase = 2;
    struct pollfd fds[MAX_DEVICES + 4];
    int poll_count = device_count + 3;
    fds[0] = (struct pollfd){ CONTROL, POLLIN, 0 };
    for (int i = 0; i < device_count; ++i) {
        fds[i + 1] = (struct pollfd){ 4 + i, POLLIN, 0 };
        if (drain(4 + i)) return fail();
    }
    fds[device_count + 1] = (struct pollfd){4 + device_count, POLLIN, 0};
    fds[device_count + 2] = (struct pollfd){5 + device_count, POLLIN, 0};
#ifdef LDC_NATIVE_WATCH
    collector_phase = 3;
    if (!session_watch_ok()) return fail();
    int watch_fd = session_watch_fd();
    if (watch_fd < 6 + 2 * device_count) return fail();
    fds[device_count + 3] = (struct pollfd){watch_fd, POLLIN, 0};
    ++poll_count;
    collector_phase = 4;
    if (confine_collector()) return fail();
#endif
    collector_phase = 5;
    heartbeat = now_ms();
    session_time = heartbeat;
    if (heartbeat < 0 || send(CONTROL, "READY\n", 6, MSG_NOSIGNAL | MSG_DONTWAIT) != 6)
        return fail();
    for (;;) {
        collector_phase = 6;
#ifdef LDC_NATIVE_WATCH
        collector_phase = 20;
        if (!session_watch_ok()) return fail();
#endif
        long long current = now_ms();
        int expired = expiry_phase(current, heartbeat, session_time);
        if (expired) { collector_phase = expired; return fail(); }
        collector_phase = 30;
        if (calibration_tick(current)) return fail();
        if (armed) {
            collector_phase = 31;
            int held = held_state();
            if (held < 0) return fail();
            if (held > 0) return report("ACTIVITY_HELD\n") ? 1 : 0;
        }
        collector_phase = 22;
        int ready = poll(fds, poll_count, 20);
        if (ready < 0) { if (errno == EINTR) continue; return fail(); }
#ifdef LDC_NATIVE_WATCH
        collector_phase = 33;
        if (fds[device_count + 3].revents & (POLLERR | POLLHUP | POLLNVAL)) return fail();
        collector_phase = 20;
        if (!session_watch_ok()) return fail();
#endif
        collector_phase = 23;
        if (fds[device_count + 1].revents || fds[device_count + 2].revents) return fail();
        if (armed) {
            collector_phase = 31;
            int held = held_state();
            if (held < 0) return fail();
            if (held > 0) return report("ACTIVITY_HELD\n") ? 1 : 0;
        }
        /* Source activity takes priority over new control commands. */
        for (int i = 1; i <= device_count; ++i) {
            collector_phase = 24;
            if (fds[i].revents & (POLLERR | POLLHUP | POLLNVAL)) return fail();
            if (fds[i].revents & POLLIN) {
                int result = drain(fds[i].fd);
                if (result < 0) return fail();
                if (result > 0) return report(stream_activity_message) ? 1 : 0;
            }
        }
        collector_phase = 30;
        if (calibration_tick(now_ms())) return fail();
        if (pointer_yield_tick(now_ms())) return fail();
        collector_phase = 29;
        if (fds[0].revents & (POLLERR | POLLHUP | POLLNVAL)) return fail();
        if (fds[0].revents & POLLIN) {
            collector_phase = 25;
            char data[256];
            ssize_t n = recv(CONTROL, data, sizeof data, MSG_DONTWAIT);
            if (n <= 0) return fail();
            collector_phase = 26;
            int result = feed_control(data, (size_t)n);
            if (result < 0) return fail();
            if (result == 3) return 0;
            if (result == 2) { close_devices(); return 0; }
        }
    }
}
