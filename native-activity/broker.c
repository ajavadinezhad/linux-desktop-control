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
#include "touchpad.h"

#define CONTROL 3
#define MAX_DEVICES 64
#define HEARTBEAT_MS 1000
#define SESSION_BUDGET_MS 120000
#define SESSION_MAX_MS 600000
static long long session_budget_ms = SESSION_BUDGET_MS;
static bool lease_negotiated;
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
static bool click_pause_mode, click_pause_sticky;
static bool held_admitted_click, held_other_input;
static unsigned click_notice_epoch;
static bool touchpad_yield_mode, calibration_touchpad_motion;
static bool observation_touchpad_motion_after_arm;
/* Opener-only admission; neither requester nor event payload sets these. */
static bool device_touchpad[MAX_DEVICES], touchpad_snapshot_contact[MAX_DEVICES];
static struct tp_limits touchpad_limits[MAX_DEVICES];
static struct tp_state touchpad_states[MAX_DEVICES];
static bool observation_primary_after_arm, observation_relative_after_arm, observation_yield_sent;
static unsigned pointer_epoch;
static long long pointer_last_motion;
#define POINTER_YIELD_MAX_EPOCH 64
#define POINTER_QUIET_MS 1500
static const char *stream_activity_message;
enum { CATEGORY_KEYBOARD = 1, CATEGORY_POINTER = 2 };
/* Filled only by the verified opener, not accepted from the requester. */
static unsigned device_categories[MAX_DEVICES];
static bool calibrating, calibrated, calibration_release_pending;
/* Explicit supervised startup has no challenge credit. Selection is latched
 * through the session and cannot be converted into challenge ARM authority. */
static bool passive_selected, passive_pending, passive_tracking, passive_armed;
static bool passive_release_frame_pending[MAX_DEVICES];
static long long passive_started_at, passive_tracking_at, passive_deadline, passive_last_activity;
static unsigned passive_motion_epoch;
/* Explicit expected-authentication suspension; never input provenance or a
 * permission-dialog identity. The controller must fence capture beforehand. */
static bool auth_mode, auth_waiting, auth_ending;
static unsigned auth_epoch;
static bool auth_frame_pending[MAX_DEVICES];
static long long auth_started_at,auth_deadline,auth_last_activity;
#define AUTH_WAIT_MS 120000
#define AUTH_END_MS 5000
#define PASSIVE_SETTLE_MS 5000
static long long calibration_release_deadline;
#define CALIBRATION_RELEASE_MS 5000
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
    if (current - started >= session_budget_ms) return 18;
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
    /* Fixed terminal evidence only; raw descriptors are already gone. Neither
     * these bits nor successful export establishes input authority. */
    char payload[128];
    int length = snprintf(payload, sizeof payload, "%s%s%u%u%u%u\n", message,
        touchpad_yield_mode ? "OBS_TPAD_" : "OBS_DIAG_",
        (touchpad_yield_mode ? calibration_touchpad_motion : calibration_pointer_stream) ? 1U : 0U,
        observation_primary_after_arm ? 1U : 0U,
        (touchpad_yield_mode ? observation_touchpad_motion_after_arm : observation_relative_after_arm) ? 1U : 0U,
        observation_yield_sent ? 1U : 0U);
    if (length <= 0 || (size_t)length >= sizeof payload) return -1;
    ssize_t n = send(CONTROL, payload, (size_t)length, MSG_NOSIGNAL | MSG_DONTWAIT);
    return n == length ? 0 : -1;
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
    if (send(CONTROL, message, (size_t)length, MSG_NOSIGNAL | MSG_DONTWAIT) != length) return -1;
    if (!strcmp(prefix, "YIELDED")) observation_yield_sent = true;
    return 0;
}
static bool positional_mouse_motion(int device, const struct input_event *event) {
    return device >= 0 && device < device_count &&
        (device_categories[device] & CATEGORY_POINTER) && event->type == EV_REL &&
        (event->code == REL_X || event->code == REL_Y) && event->value != 0;
}
static int pointer_motion(long long current) {
    if(current<0)return -1;
    if (!pointer_yielded || pointer_quiet) {
        if (++pointer_epoch > POINTER_YIELD_MAX_EPOCH) return -1;
        pointer_yielded = true; pointer_quiet = false;
        passive_motion_epoch=0;
        if (pointer_token("YIELDED")) return -1;
    }
    pointer_last_motion = current;
    if(click_pause_sticky&&click_notice_epoch!=pointer_epoch) {
        if(pointer_token("CLICKED"))return -1;
        click_notice_epoch=pointer_epoch;
    }
    return 0;
}
static bool admitted_click(int device,const struct input_event *event) {
    return device>=0&&device<device_count&&(device_categories[device]&CATEGORY_POINTER)&&
        event->type==EV_KEY&&(event->code==BTN_LEFT||event->code==BTN_RIGHT||event->code==BTN_MIDDLE)&&
        (event->value==0||event->value==1);
}
static int pointer_click(long long current) {
    click_pause_sticky=true;
    return pointer_motion(current);
}
static int passive_motion_notice(void) {
    if(!passive_armed||!pointer_yielded||pointer_quiet||!pointer_epoch)return 0;
    if(passive_motion_epoch==pointer_epoch)return 0;
    if(pointer_token("MOTION"))return -1;
    passive_motion_epoch=pointer_epoch;
    return 0;
}
static void touchpad_reset_all(void) {
    for(int i=0;i<device_count;i++) {
        tp_reset(&touchpad_states[i]);
        touchpad_snapshot_contact[i]=false;
    }
}
static bool touchpad_busy(void) {
    if(!touchpad_yield_mode)return false;
    for(int i=0;i<device_count;i++)if(device_touchpad[i]&&
        (touchpad_snapshot_contact[i]||tp_active(&touchpad_states[i])||tp_incomplete(&touchpad_states[i])))return true;
    return false;
}
static bool touchpad_contact_active(void) {
    if(!touchpad_yield_mode)return false;
    for(int i=0;i<device_count;i++)if(device_touchpad[i]&&
        (touchpad_snapshot_contact[i]||tp_active(&touchpad_states[i])))return true;
    return false;
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
            if (armed) observation_primary_after_arm = true;
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
                calibration_touchpad_motion = false;
                if(touchpad_yield_mode)touchpad_reset_all();
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
            if(armed&&click_pause_mode&&admitted_click(fd-4,&event)) {
                long long stamp=(long long)event.time.tv_sec*1000+event.time.tv_usec/1000;
                long long current=now_ms();
                if(current<0||stamp<arm_time||stamp>current+1000)return -1;
                if(pointer_click(current))return -1;
                continue;
            }
            if(auth_waiting) {
                long long current=now_ms();
                long long stamp=(long long)event.time.tv_sec*1000+event.time.tv_usec/1000;
                if(current<0||stamp<auth_started_at||stamp>current+1000)return -1;
                bool pad=touchpad_yield_mode&&fd>=4&&fd<4+device_count&&device_touchpad[fd-4];
                if(fd<4||fd>=4+device_count)return -1;
                if(event.type==EV_SYN) {
                    if(event.code!=SYN_REPORT||event.value!=0)return -1;
                    auth_frame_pending[fd-4]=false;
                } else auth_frame_pending[fd-4]=true;
                if(event.type==EV_KEY&&event.value>=0&&event.value<=2&&
                   (ordinary_key(event.code)||(event.code>=BTN_MOUSE&&event.code<=BTN_TASK))) {
                    auth_last_activity=current;continue;
                }
                if(pad) {
                    enum tp_result result=tp_event(&touchpad_states[fd-4],&event,&touchpad_limits[fd-4]);
                    if(result==TP_UNSUPPORTED)return -1;
                    if(result==TP_CONTACT||result==TP_MOTION||event.type==EV_KEY)auth_last_activity=current;
                    continue;
                }
                if(event.type==EV_SYN&&event.code==SYN_REPORT&&event.value==0)continue;
                /* Ordinary keyboard scan metadata is private framing only;
                 * never export, interpret, or use its value as activity credit. */
                if(event.type==EV_MSC&&event.code==MSC_SCAN&&fd>=4&&fd<4+device_count&&
                   (device_categories[fd-4]&CATEGORY_KEYBOARD))continue;
                if(event.type==EV_KEY&&event.value>=0&&event.value<=2&&
                   (ordinary_key(event.code)||(event.code>=BTN_MOUSE&&event.code<=BTN_TASK))) {
                    auth_last_activity=current;continue;
                }
                if(event.type==EV_REL&&(event.code==REL_X||event.code==REL_Y||
                   event.code==REL_WHEEL||event.code==REL_HWHEEL)) {auth_last_activity=current;continue;}
                return -1;
            }
            if(passive_pending) {
                long long stamp=(long long)event.time.tv_sec*1000+event.time.tv_usec/1000;
                long long current=now_ms();
                if(current<0||stamp<0||(passive_tracking&&stamp<passive_tracking_at)||stamp>current+1000){collector_phase=45;return -1;}
                if(event.type==EV_SYN&&(event.code!=SYN_REPORT||event.value!=0)){collector_phase=51;return -1;}
                if(!passive_tracking) {
                    /* Initial authentication release is drained without
                     * manufacturing a parser contact or motion baseline. */
                    bool pad=touchpad_yield_mode&&fd>=4&&fd<4+device_count&&device_touchpad[fd-4];
                    if(event.type==EV_SYN){if(pad)passive_release_frame_pending[fd-4]=false;continue;}
                    if(pad&&event.type==EV_MSC&&event.code==MSC_TIMESTAMP)continue;
                    if(pad)passive_release_frame_pending[fd-4]=true;
                    if(event.type==EV_KEY&&(event.value==0||event.value==1||event.value==2)) {
                        passive_last_activity=current;continue;
                    }
                    if(positional_mouse_motion(fd-4,&event)) {passive_last_activity=current;continue;}
                    if(pad&&event.type==EV_ABS) {
                        const struct tp_limits *l=&touchpad_limits[fd-4];
                        bool axis=(event.code==ABS_X&&event.value>=l->x_min&&event.value<=l->x_max)||
                            (event.code==ABS_Y&&event.value>=l->y_min&&event.value<=l->y_max)||
                            (l->mt&&event.code==ABS_MT_POSITION_X&&event.value>=l->x_min&&event.value<=l->x_max)||
                            (l->mt&&event.code==ABS_MT_POSITION_Y&&event.value>=l->y_min&&event.value<=l->y_max)||
                            (l->mt&&event.code==ABS_MT_SLOT&&event.value>=l->slot_min&&event.value<=l->slot_max)||
                            (l->mt&&event.code==ABS_MT_TRACKING_ID&&event.value>=-1&&event.value<=l->tracking_max);
                        bool metadata=(event.code==ABS_PRESSURE||event.code==ABS_TOOL_WIDTH||
                            (l->mt&&(event.code==ABS_MT_PRESSURE||event.code==ABS_MT_TOUCH_MAJOR||event.code==ABS_MT_TOUCH_MINOR||
                                     event.code==ABS_MT_WIDTH_MAJOR||event.code==ABS_MT_WIDTH_MINOR)))&&event.value>=0;
                        if(axis||metadata){if(axis)passive_last_activity=current;continue;}
                    }
                    collector_phase=51;return -1;
                }
            }
            if(touchpad_yield_mode&&fd>=4&&fd<4+device_count&&device_touchpad[fd-4]&&(armed||calibrating||calibrated||passive_pending)) {
                long long current=now_ms();
                long long stamp=(long long)event.time.tv_sec*1000+event.time.tv_usec/1000;
                if(current<0||stamp>current+1000||(armed&&stamp<arm_time)) {collector_phase=45;return -1;}
                if(calibrated&&!armed){collector_phase=46;return -1;}
                /* Pre-challenge records may not establish a new baseline. */
                if(calibrating&&(calibration_reset_pending||stamp<=calibration_time))continue;
                bool was_active=tp_active(&touchpad_states[fd-4]);
                enum tp_result result=tp_event_mode(&touchpad_states[fd-4],&event,&touchpad_limits[fd-4],armed&&click_pause_mode);
                if(result==TP_UNSUPPORTED){collector_phase=50;return -1;}
                if(armed) {
                    if(result==TP_INTERVENTION) {
                        if(!click_pause_mode||pointer_click(current))return -1;
                        continue;
                    }
                    if(result==TP_MOTION)observation_touchpad_motion_after_arm=true;
                    if((result==TP_CONTACT||result==TP_MOTION)&&pointer_motion(current))return -1;
                    if(result==TP_MOTION&&passive_motion_notice())return -1;
                } else if(calibrating) {
                    if(result==TP_MOTION)calibration_touchpad_motion=calibration_pointer_stream=true;
                    /* Any actual contact/frame activity refreshes quiet, but
                     * metadata-only clock records supply neither credit nor busy. */
                    if(result==TP_CONTACT||result==TP_MOTION||(was_active&&!tp_active(&touchpad_states[fd-4])))calibration_note_kind(
                        result==TP_MOTION?CATEGORY_POINTER:0,current,calibration_event_kind(&event));
                } else if(passive_pending&&(result==TP_CONTACT||result==TP_MOTION||
                           (was_active&&!tp_active(&touchpad_states[fd-4])))) {
                    passive_last_activity=current;
                }
                continue;
            }
            if (kind) {
                if (armed) {
                    long long stamp = (long long)event.time.tv_sec * 1000 + event.time.tv_usec / 1000;
                    if (stamp < arm_time || stamp > now_ms() + 1000) { collector_phase = 45; return -1; }
                    if (positional_mouse_motion(fd - 4, &event)) observation_relative_after_arm = true;
                    if (pointer_yield_mode && !touchpad_yield_mode && positional_mouse_motion(fd - 4, &event)) {
                        if (pointer_motion(now_ms())) return -1;
                        if(passive_motion_notice())return -1;
                        continue;
                    }
                    stream_activity_message = activity_message(&event);
                    return 1;
                }
                if (calibrated) { collector_phase = 46; return -1; }
                if(passive_pending) {
                    if((event.type==EV_KEY&&(event.value==0||event.value==1||event.value==2))||
                       positional_mouse_motion(fd-4,&event)) {passive_last_activity=now_ms();continue;}
                    collector_phase=51;return -1;
                }
                if (calibrating) {
                    long long stamp = (long long)event.time.tv_sec * 1000 + event.time.tv_usec / 1000;
                    long long current = now_ms();
                    if (current < 0 || stamp > current + 1000) { collector_phase = 45; return -1; }
                    if (stamp > calibration_time) {
                        if (!touchpad_yield_mode&&!calibration_reset_pending && positional_mouse_motion(fd - 4, &event))
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
    held_admitted_click=held_other_input=false;
    for (int i = 0; i < device_count; ++i) {
        unsigned char keys[(KEY_MAX + 8) / 8] = {0};
        /* EVIOCGKEY flushes this client's queued EV_KEY. Never query the
         * primary stream descriptor; dup() would share the same client. */
        for (int attempt=0;;++attempt) {
            if (ioctl(6 + device_count + i, EVIOCGKEY(sizeof keys), keys) < 0) return -1;
            if(!(armed&&click_pause_mode&&touchpad_yield_mode&&device_touchpad[i]))break;
            bool touch=(keys[BTN_TOUCH/8]&(1U<<(BTN_TOUCH%8)))!=0;
            bool finger=(keys[BTN_TOOL_FINGER/8]&(1U<<(BTN_TOOL_FINGER%8)))!=0;
            bool two=(keys[BTN_TOOL_DOUBLETAP/8]&(1U<<(BTN_TOOL_DOUBLETAP%8)))!=0;
            if(!(finger&&two)&&touch==(finger||two))break;
            bool other=false;
            for(unsigned code=0;code<=KEY_MAX;++code)
                if(code!=BTN_TOUCH&&code!=BTN_TOOL_FINGER&&code!=BTN_TOOL_DOUBLETAP&&
                   (keys[code/8]&(1U<<(code%8)))){other=true;break;}
            if(other)break; /* Never discard a key, button, or unsupported tool. */
            /* EVIOCGKEY is atomic per input_event, not per SYN_REPORT.
             * A tool-count transition can therefore expose intermediate bits.
             * Re-read only this ambiguity, bounded without sleeps; never grant
             * quiet/motion credit, and keep a persistent contradiction fatal. */
            if(pointer_click(now_ms())||attempt==2||expiry_phase(now_ms(),heartbeat,session_time))return -1;
            memset(keys,0,sizeof keys);
        }
        if (calibrating) calibration_diag.query_success = true;
        bool any = false, contact=false, finger=false, touch=false, two=false; unsigned categories = 0;
        for (unsigned code = 0; code <= KEY_MAX; ++code) {
            if (!(keys[code / 8] & (1U << (code % 8)))) continue;
            if(touchpad_yield_mode&&device_touchpad[i]&&(code==BTN_TOUCH||code==BTN_TOOL_FINGER||(armed&&click_pause_mode&&code==BTN_TOOL_DOUBLETAP))) {
                contact=true;touch|=code==BTN_TOUCH;finger|=code==BTN_TOOL_FINGER;two|=code==BTN_TOOL_DOUBLETAP;continue;
            }
            any = true;
            if((device_categories[i]&CATEGORY_POINTER)&&(code==BTN_LEFT||code==BTN_RIGHT||code==BTN_MIDDLE))held_admitted_click=true;
            else held_other_input=true;
            if (ordinary_key(code)) categories |= device_categories[i] & CATEGORY_KEYBOARD;
            if (code >= BTN_MISC) categories |= device_categories[i] & CATEGORY_POINTER;
        }
        if(touchpad_yield_mode&&device_touchpad[i]) {
            /* An inconsistent snapshot is not a single-finger permission. */
            if((finger&&two)||touch!=(finger||two))return -1;
            touchpad_snapshot_contact[i]=contact;
            if(contact&&armed&&(two?pointer_click(now_ms()):pointer_motion(now_ms())))return -1;
            if(contact&&calibrating)calibration_note_kind(0,now_ms(),'H');
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
static int held_intervention(void) {
    if(click_pause_mode&&held_admitted_click&&!held_other_input)
        return pointer_click(now_ms());
    return 1; /* Keyboard, unadmitted/other buttons remain terminal. */
}
static int passive_tick(long long current) {
    if(!passive_pending)return 0;
    int expired=expiry_phase(current,heartbeat,session_time);
    if(expired){collector_phase=expired;return -1;}
    if(current<passive_started_at||current>=passive_deadline){collector_phase=52;return -1;}
    for(int i=0;i<device_count;i++)if(drain(4+i))return -1;
    int held=held_state();
    if(held<0)return -1;
    long long checked=now_ms();expired=expiry_phase(checked,heartbeat,session_time);
    if(expired){collector_phase=expired;return -1;}
    if(checked<current||checked>=passive_deadline){collector_phase=52;return -1;}
    current=checked;
    if(held||touchpad_contact_active()){passive_last_activity=current;return 0;}
    if(touchpad_busy())return 0;
    for(int i=0;i<device_count;i++)if(passive_release_frame_pending[i])return 0;
    struct pollfd boundary[MAX_DEVICES+2];
    for(int i=0;i<device_count+2;i++)boundary[i]=(struct pollfd){4+i,POLLIN,0};
    int pending=poll(boundary,device_count+2,0);
    if(pending<0)return -1;
    if(boundary[device_count].revents||boundary[device_count+1].revents)return -1;
    if(pending)return 0;
#ifdef LDC_NATIVE_WATCH
    if(!session_watch_ok())return -1;
#endif
    checked=now_ms();expired=expiry_phase(checked,heartbeat,session_time);
    if(expired){collector_phase=expired;return -1;}
    if(checked<current||checked>=passive_deadline){collector_phase=52;return -1;}
    current=checked;
    if(!passive_tracking) {
        /* A clean released boundary, never a saved calibration result. */
        touchpad_reset_all();passive_tracking=true;passive_tracking_at=passive_last_activity=current;
        return 0;
    }
    if(current<passive_last_activity)return -1;
    if(current-passive_last_activity<CALIBRATION_QUIET_MS)return 0;
    /* Recheck physical/session state after potentially blocking queries. */
    held=held_state();
    if(held<0)return -1;
    checked=now_ms();expired=expiry_phase(checked,heartbeat,session_time);
    if(expired){collector_phase=expired;return -1;}
    if(checked<current||checked>=passive_deadline){collector_phase=52;return -1;}
    current=checked;
    if(held||touchpad_contact_active()){passive_last_activity=current;return 0;}
    if(touchpad_busy())return 0;
    pending=poll(boundary,device_count+2,0);
    if(pending<0||boundary[device_count].revents||boundary[device_count+1].revents)return -1;
    if(pending)return 0;
#ifdef LDC_NATIVE_WATCH
    if(!session_watch_ok())return -1;
#endif
    pending=poll(boundary,device_count+2,0);
    if(pending<0||boundary[device_count].revents||boundary[device_count+1].revents)return -1;
    if(pending)return 0;
    long long ready=now_ms();expired=expiry_phase(ready,heartbeat,session_time);
    if(expired){collector_phase=expired;return -1;}
    if(ready<current||ready>=passive_deadline){collector_phase=52;return -1;}
    passive_pending=false;passive_armed=true;armed=true;arm_time=ready;
    return send(CONTROL,"PASSIVE_ARMED\n",14,MSG_NOSIGNAL|MSG_DONTWAIT)==14?0:-1;
}
static int auth_reply(const char *prefix) {
    char response[32];int n=snprintf(response,sizeof response,"%s_%u%s\n",prefix,auth_epoch,!strcmp(prefix,"AUTHWAIT")?"_OK":"");
    return n>0&&(size_t)n<sizeof response&&send(CONTROL,response,(size_t)n,MSG_NOSIGNAL|MSG_DONTWAIT)==n?0:-1;
}
static int auth_tick(long long current) {
    if(!auth_waiting)return 0;
    int expired=expiry_phase(current,heartbeat,session_time);
    if(expired){collector_phase=expired;return -1;}
    if(current<auth_started_at||current>=auth_deadline)return -1;
    for(int i=0;i<device_count;i++)if(drain(4+i))return -1;
    int held=held_state();if(held<0)return -1;
    long long checked=now_ms();expired=expiry_phase(checked,heartbeat,session_time);
    if(expired){collector_phase=expired;return -1;}
    if(checked<current||checked>=auth_deadline)return -1;
    if(held||touchpad_contact_active()){auth_last_activity=checked;return 0;}
    if(touchpad_busy())return 0;
    for(int i=0;i<device_count;i++)if(auth_frame_pending[i])return 0;
    if(!auth_ending||checked-auth_last_activity<CALIBRATION_QUIET_MS)return 0;
    struct pollfd boundary[MAX_DEVICES+2];
    for(int i=0;i<device_count+2;i++)boundary[i]=(struct pollfd){4+i,POLLIN,0};
    int pending=poll(boundary,device_count+2,0);
    if(pending<0||boundary[device_count].revents||boundary[device_count+1].revents)return -1;
    if(pending)return 0;
#ifdef LDC_NATIVE_WATCH
    if(!session_watch_ok())return -1;
#endif
    held=held_state();if(held<0)return -1;
    if(held||touchpad_contact_active()){auth_last_activity=now_ms();return 0;}
    if(touchpad_busy())return 0;
    pending=poll(boundary,device_count+2,0);
    if(pending<0||boundary[device_count].revents||boundary[device_count+1].revents)return -1;
    if(pending)return 0;
#ifdef LDC_NATIVE_WATCH
    if(!session_watch_ok())return -1;
#endif
    pending=poll(boundary,device_count+2,0);
    if(pending<0||boundary[device_count].revents||boundary[device_count+1].revents)return -1;
    if(pending)return 0;
    long long ready=now_ms();expired=expiry_phase(ready,heartbeat,session_time);
    if(expired){collector_phase=expired;return -1;}
    if(ready<checked||ready>=auth_deadline)return -1;
    auth_waiting=auth_ending=false;armed=true;arm_time=ready;
    pointer_yielded=pointer_quiet=false;passive_motion_epoch=0;
    return auth_reply("AUTHREADY");
}
static unsigned auth_parse_epoch(const char *digits) {
    unsigned value=0;if(!*digits||*digits=='0')return 0;
    for(const char *p=digits;*p;p++) {
        if(*p<'0'||*p>'9'||value>64)return 0;
        value=value*10+(unsigned)(*p-'0');
    }
    return value>=1&&value<=64?value:0;
}
static int calibration_tick(long long current) {
    if (!calibrating) return 0;
    calibration_pending_input = calibration_pending_topology = calibration_pending_owner = false;
    calibration_quiet_reason = 'M';
    int held = held_state();
    if (held < 0 || current < 0) return -1;
    if (calibration_reset_pending) {
        for (int i = 0; i < device_count; ++i) if (calibration_resync[i]) return 0;
        if (held||touchpad_busy()) return 0;
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
        calibration_touchpad_motion = false;
        if(touchpad_yield_mode)touchpad_reset_all();
        calibration_time = calibration_last_activity = now_ms();
        if (calibration_time < 0) return -1;
        calibration_reset_pending = false;
        calibration_last_kind = 'N';
        calibration_diag.quiet_blocked = false;
        return send(CONTROL, "CALIBRATION_RESET\n", 18, MSG_NOSIGNAL | MSG_DONTWAIT) == 18 ? 0 : -1;
    }
    bool missing = calibration_seen != (CATEGORY_KEYBOARD | CATEGORY_POINTER) || (pointer_strict_coverage && !calibration_pointer_stream);
    bool pad_busy=touchpad_busy();
    calibration_quiet_reason = held||pad_busy ? 'H' : missing ? 'M' : current - calibration_last_activity < CALIBRATION_QUIET_MS ? 'R' : 'Y';
    calibration_diag.quiet_blocked = !held &&
        calibration_seen == (CATEGORY_KEYBOARD | CATEGORY_POINTER) &&
        current - calibration_last_activity < CALIBRATION_QUIET_MS;
    if (held || pad_busy || missing || current - calibration_last_activity < CALIBRATION_QUIET_MS) return 0;
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
static int calibration_begin(void) {
    calibration_release_pending = false;
    calibration_seen = 0;
    calibration_pointer_stream = false;
    calibration_touchpad_motion = false;
    if(touchpad_yield_mode)touchpad_reset_all();
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
static int calibration_release_tick(long long current) {
    if (!calibration_release_pending) return 0;
    if (current < 0 || current >= calibration_release_deadline) { collector_phase = 48; return -1; }
    /* Authentication gestures are drained while calibration is still false;
     * neither their streamed records nor held snapshots earn challenge credit. */
    for (int i = 0; i < device_count; ++i) if (drain(4 + i)) return -1;
    int held = held_state();
    if (held < 0) { collector_phase = 49; return -1; }
    if (held||touchpad_busy()) return 0;
    struct pollfd boundary[MAX_DEVICES + 2];
    for (int i = 0; i < device_count + 2; ++i)
        boundary[i] = (struct pollfd){4 + i, POLLIN, 0};
    int pending = poll(boundary, device_count + 2, 0);
    if (pending < 0) return -1;
    if (pending) return 0;
#ifdef LDC_NATIVE_WATCH
    if (!session_watch_ok()) { collector_phase = 20; return -1; }
#endif
    current = now_ms();
    if (current < 0 || current >= calibration_release_deadline) { collector_phase = 48; return -1; }
    int expired = expiry_phase(current, heartbeat, session_time);
    if (expired) { collector_phase = expired; return -1; }
    return calibration_begin();
}
static int pointer_boundary(void) {
    if (held_state() != 0) return -1;
    if(touchpad_busy())return -1;
    struct pollfd boundary[MAX_DEVICES + 2];
    for (int i = 0; i < device_count + 2; ++i)
        boundary[i] = (struct pollfd){4 + i, POLLIN, 0};
    if (poll(boundary, device_count + 2, 0) != 0) return -1;
#ifdef LDC_NATIVE_WATCH
    if (!session_watch_ok()) return -1;
#endif
    /* The session query can block while new input/topology/owner events
     * arrive. Click-aware resume requires a final clean queue boundary. */
    if(click_pause_mode&&poll(boundary,device_count+2,0)!=0)return -1;
    return 0;
}
static int pointer_yield_tick(long long current) {
    if (!pointer_yielded || pointer_quiet) return 0;
    if (current < pointer_last_motion) return -1;
    if (current - pointer_last_motion < POINTER_QUIET_MS) return 0;
    /* Held admitted clicks keep the opted-in pause busy. Other held input
     * remains terminal, including a simultaneous keyboard key. */
    int held=held_state();
    if(held<0)return -1;
    if(held>0) {
        if(click_pause_mode&&held_admitted_click&&!held_other_input)return pointer_click(now_ms());
        return -1;
    }
    if(touchpad_busy())return 0;
    struct pollfd boundary[MAX_DEVICES + 2];
    for (int i = 0; i < device_count + 2; ++i)
        boundary[i] = (struct pollfd){4 + i, POLLIN, 0};
    int pending = poll(boundary, device_count + 2, 0);
    if (pending < 0) return -1;
    if (pending) return 0;
#ifdef LDC_NATIVE_WATCH
    if (!session_watch_ok()) return -1;
#endif
    if(click_pause_mode) {
        long long checked=now_ms();
        int expired=expiry_phase(checked,heartbeat,session_time);
        if(expired){collector_phase=expired;return -1;}
        if(checked<current)return -1;
    }
    pointer_quiet = true;
    return pointer_token("QUIET");
}
static int command(const char *line) {
    long long current = now_ms();
    if (current < 0) return -1;
    if (!strcmp(line, "CLOSE")) return 2;
    if(!strcmp(line,"CLICKPAUSE1")) {
        if(click_pause_mode||!pointer_yield_mode||!pointer_strict_coverage||armed||calibrating||calibrated||
           calibration_release_pending||passive_selected||auth_waiting||expiry_phase(current,heartbeat,session_time))return -1;
        click_pause_mode=true;
        return send(CONTROL,"CLICKPAUSE1_OK\n",15,MSG_NOSIGNAL|MSG_DONTWAIT)==15?0:-1;
    }
    if(!strcmp(line,"AUTHMODE1")) {
        if(auth_mode||armed||calibrating||calibrated||calibration_release_pending||passive_selected||expiry_phase(current,heartbeat,session_time))return -1;
        auth_mode=true;
        return send(CONTROL,"AUTHMODE1_OK\n",13,MSG_NOSIGNAL|MSG_DONTWAIT)==13?0:-1;
    }
    if(!strncmp(line,"AUTHWAIT_",9)) {
        unsigned epoch=auth_parse_epoch(line+9);
        if(!auth_mode||!armed||auth_waiting||pointer_yielded||epoch!=auth_epoch+1||!epoch||expiry_phase(current,heartbeat,session_time))return -1;
        auth_epoch=epoch;auth_waiting=true;auth_ending=false;armed=false;
        auth_started_at=auth_last_activity=current;auth_deadline=current+AUTH_WAIT_MS;
        touchpad_reset_all();memset(auth_frame_pending,0,sizeof auth_frame_pending);passive_motion_epoch=0;
        return auth_reply("AUTHWAIT");
    }
    if(!strncmp(line,"AUTHEND_",8)) {
        unsigned epoch=auth_parse_epoch(line+8);
        if(!auth_mode||!auth_waiting||auth_ending||!epoch||epoch!=auth_epoch||expiry_phase(current,heartbeat,session_time)||current>=auth_deadline)return -1;
        auth_ending=true;
        if(current+AUTH_END_MS<auth_deadline)auth_deadline=current+AUTH_END_MS;
        auth_last_activity=current;
        return 0;
    }
    if(auth_waiting&&strcmp(line,"HB"))return -1;
    if (!strncmp(line, "LEASE_", 6)) {
        if (lease_negotiated || pointer_yield_mode || armed || calibrating || calibrated || calibration_release_pending || passive_selected ||
            expiry_phase(current, heartbeat, session_time)) return -1;
        const char *digits = line + 6;
        if (strlen(digits) != 3 || digits[0] < '1' || digits[0] > '6' ||
            digits[1] < '0' || digits[1] > '9' || digits[2] < '0' || digits[2] > '9') return -1;
        unsigned seconds = (unsigned)(digits[0]-'0')*100 + (unsigned)(digits[1]-'0')*10 + (unsigned)(digits[2]-'0');
        if (seconds < 120 || seconds > SESSION_MAX_MS/1000) return -1;
        char reply[16];
        int length = snprintf(reply,sizeof reply,"LEASE_%u_OK\n",seconds);
        if (length <= 0 || (size_t)length >= sizeof reply) return -1;
        lease_negotiated = true;
        session_budget_ms = (long long)seconds * 1000;
        /* The original READY anchor is never replaced or renewed. */
        return send(CONTROL,reply,(size_t)length,MSG_NOSIGNAL | MSG_DONTWAIT)==length ? 0 : -1;
    }
    if (!strcmp(line, "MODEYIELD") || !strcmp(line, "MODEYIELD2") || !strcmp(line,"MODEYIELD3")) {
        if (pointer_yield_mode || armed || calibrating || calibrated || calibration_release_pending || passive_selected) return -1;
        bool want_touchpad=!strcmp(line,"MODEYIELD3");
        if(want_touchpad) {
            if(expiry_phase(current,heartbeat,session_time))return -1;
            bool admitted=false;
            for(int i=0;i<device_count;i++)admitted|=device_touchpad[i]&&tp_valid_limits(&touchpad_limits[i]);
            if(!admitted)return -1;
        }
        pointer_yield_mode = true;
        touchpad_yield_mode=want_touchpad;
        pointer_strict_coverage = want_touchpad||!strcmp(line, "MODEYIELD2");
        if(want_touchpad)touchpad_reset_all();
        const char *reply = want_touchpad ? "MODEYIELD3_OK\n" : pointer_strict_coverage ? "MODEYIELD2_OK\n" : "MODEYIELD_OK\n";
        size_t length = strlen(reply);
        return send(CONTROL,reply,length,MSG_NOSIGNAL | MSG_DONTWAIT) == (ssize_t)length ? 0 : -1;
    }
    bool click_resume=!strncmp(line,"RESUMECLICK_",12);
    if (!strncmp(line, "RESUME_", 7)||click_resume) {
        const char *epoch = line + (click_resume?12:7); unsigned value = 0;
        if(click_resume?(!click_pause_mode||!click_pause_sticky):click_pause_sticky)return -1;
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
        click_pause_sticky=false;click_notice_epoch=0;
        passive_motion_epoch=0;
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
        if (armed || calibrating || calibrated || calibration_release_pending || passive_selected) return -1;
        calibration_release_pending = true;
        calibration_release_deadline = current + CALIBRATION_RELEASE_MS;
        return calibration_release_tick(current);

    }
    if(!strcmp(line,"ARM_PASSIVE")) {
        if(passive_selected||armed||calibrating||calibrated||calibration_release_pending||calibration_reset_pending||
           !pointer_yield_mode||!pointer_strict_coverage||expiry_phase(current,heartbeat,session_time))return -1;
        passive_selected=passive_pending=true;passive_tracking=false;passive_armed=false;
        passive_tracking_at=0;
        passive_started_at=passive_last_activity=current;passive_deadline=current+PASSIVE_SETTLE_MS;
        memset(passive_release_frame_pending,0,sizeof passive_release_frame_pending);
        passive_motion_epoch=0;
        return passive_tick(current);
    }
    if (!strcmp(line, "ARM")) {
        if (passive_selected || armed || calibrating || calibration_release_pending || calibration_reset_pending || !calibrated ||
            (pointer_strict_coverage && !calibration_pointer_stream)) return -1;
        for (int i = 0; i < device_count; ++i) if (calibration_resync[i]) return -1;
#ifdef LDC_NATIVE_WATCH
        if (!session_watch_ok()) return -1;
#endif
        /* The queue is checked again at the activation boundary. */
        for (int i = 0; i < device_count; ++i) if (drain(4 + i)) return -1;
        if (held_state() != 0) return -1;
        if(touchpad_busy())return -1;
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
        if (calibration_release_tick(current)) return fail();
        if (calibration_tick(current)) return fail();
        if(passive_tick(current))return fail();
        if(auth_tick(current))return fail();
        if (armed) {
            collector_phase = 31;
            int held = held_state();
            if (held < 0) return fail();
            if (held > 0) {
                int intervention=held_intervention();
                if(intervention<0)return fail();
                if(intervention>0)return report("ACTIVITY_HELD\n") ? 1 : 0;
            }
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
            if (held > 0) {
                int intervention=held_intervention();
                if(intervention<0)return fail();
                if(intervention>0)return report("ACTIVITY_HELD\n") ? 1 : 0;
            }
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
        if (calibration_release_tick(now_ms())) return fail();
        if (calibration_tick(now_ms())) return fail();
        if(passive_tick(now_ms()))return fail();
        if(auth_tick(now_ms()))return fail();
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
            if (result == 2) { (void)report(""); return 0; } /* Optional CLOSE detail is best effort. */
        }
    }
}
