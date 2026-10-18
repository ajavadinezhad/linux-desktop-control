#ifndef LDC_SESSION_WATCH_H
#define LDC_SESSION_WATCH_H
/* Include in the collector AFTER dropping all UIDs to nobody and before seccomp.
 * Private system-bus connection only: never inherit a root bus connection.
 * Poll session_watch_fd(), and call session_watch_ok() before ARM and at least
 * every 20ms. All relevant lifecycle changes latch failure; no auto rearming. */
#include <systemd/sd-bus.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define SW_LOGIND "org.freedesktop.login1"
#define SW_MANAGER "/org/freedesktop/login1"
#define SW_SESSION "org.freedesktop.login1.Session"
static struct {
    sd_bus *bus;
    sd_bus_slot *properties, *removed, *owner;
    bool healthy, terminal;
    int io_fd;
    char id[129], path[1025], name[257];
} session_watch_state = {.io_fd = -1};

static inline int sw_copy(char *out, size_t size, const char *in) {
    if (!in || strlen(in) >= size) return -1;
    memcpy(out, in, strlen(in) + 1);
    return 0;
}
static inline int sw_relevant_property(const char *name) {
    return name && (!strcmp(name, "Active") || !strcmp(name, "LockedHint") ||
        !strcmp(name, "Remote") || !strcmp(name, "Type") ||
        !strcmp(name, "Seat") || !strcmp(name, "State"));
}
static inline int sw_properties(sd_bus_message *message, void *userdata, sd_bus_error *error) {
    (void)userdata; (void)error;
    const char *interface = NULL, *name = NULL;
    bool relevant = false;
    unsigned entries = 0;
    if (!message || sd_bus_message_read(message, "s", &interface) <= 0 || !interface ||
        sd_bus_message_enter_container(message, 'a', "{sv}") <= 0) goto malformed;
    bool session = !strcmp(interface, SW_SESSION);
    for (;;) {
        int result = sd_bus_message_enter_container(message, 'e', "sv");
        if (result < 0) goto malformed;
        if (!result) break;
        if (++entries > 128 || sd_bus_message_read(message, "s", &name) <= 0 || !name ||
            sd_bus_message_skip(message, "v") < 0 || sd_bus_message_exit_container(message) < 0) goto malformed;
        if (session && sw_relevant_property(name)) relevant = true;
    }
    if (sd_bus_message_exit_container(message) < 0 ||
        sd_bus_message_enter_container(message, 'a', "s") <= 0) goto malformed;
    for (;;) {
        int result = sd_bus_message_read(message, "s", &name);
        if (result < 0) goto malformed;
        if (!result) break;
        if (++entries > 128 || !name) goto malformed;
        if (session && sw_relevant_property(name)) relevant = true;
    }
    if (sd_bus_message_exit_container(message) < 0 || sd_bus_message_at_end(message, 1) <= 0) goto malformed;
    if (relevant) session_watch_state.healthy = false;
    return 0;
malformed:
    session_watch_state.healthy = false;
    return 0;
}
static inline int sw_removed(sd_bus_message *message, void *userdata, sd_bus_error *error) {
    (void)userdata; (void)error;
    const char *id = NULL, *path = NULL;
    if (sd_bus_message_read(message, "so", &id, &path) < 0 ||
        !id || !path || !strcmp(id, session_watch_state.id) || !strcmp(path, session_watch_state.path))
        session_watch_state.healthy = false;
    return 0;
}
static inline int sw_owner(sd_bus_message *message, void *userdata, sd_bus_error *error) {
    (void)userdata; (void)error;
    const char *name = NULL, *old = NULL, *current = NULL;
    if (sd_bus_message_read(message, "sss", &name, &old, &current) < 0 || !name || !old || !current)
        session_watch_state.healthy = false;
    else if (!strcmp(name, SW_LOGIND))
        session_watch_state.healthy = false;
    return 0;
}
static inline void session_watch_close(void) {
    /* Terminal confinement cleanup deliberately leaves library memory alone. */
    if (session_watch_state.terminal) return;
    session_watch_state.healthy = false;
    session_watch_state.properties = sd_bus_slot_unref(session_watch_state.properties);
    session_watch_state.removed = sd_bus_slot_unref(session_watch_state.removed);
    session_watch_state.owner = sd_bus_slot_unref(session_watch_state.owner);
    if (session_watch_state.bus) sd_bus_close(session_watch_state.bus);
    session_watch_state.bus = sd_bus_unref(session_watch_state.bus);
    session_watch_state.io_fd = -1;
    memset(session_watch_state.id, 0, sizeof session_watch_state.id);
    memset(session_watch_state.path, 0, sizeof session_watch_state.path);
    memset(session_watch_state.name, 0, sizeof session_watch_state.name);
}
/* Terminal path only: raw input FDs must already be closed. Never invoke
 * libsystemd destructors/flush under seccomp. Process exit reclaims memory.
 * Latch before closing so no later processing or reopening can use this FD. */
static inline void session_watch_stop_io(void) {
    if (session_watch_state.terminal) return;
    session_watch_state.terminal = true;
    session_watch_state.healthy = false;
    int fd = session_watch_state.io_fd;
    session_watch_state.io_fd = -1;
    if (fd >= 0) close(fd);
}
static inline int session_watch_ok(void) {
    if (session_watch_state.terminal || !session_watch_state.healthy || !session_watch_state.bus) return 0;
    if (sd_bus_is_open(session_watch_state.bus) <= 0) {
        session_watch_state.healthy = false; return 0;
    }
    /* sd_bus_process is nonblocking. Flooding cannot starve device/control work. */
    for (unsigned i = 0; i < 64; ++i) {
        int result = sd_bus_process(session_watch_state.bus, NULL);
        if (result < 0) { session_watch_state.healthy = false; return 0; }
        if (!session_watch_state.healthy) return 0;
        if (!result) return 1;
    }
    session_watch_state.healthy = false;
    return 0;
}
static inline int session_watch_fd(void) {
    if (session_watch_state.terminal || !session_watch_state.bus || !session_watch_state.healthy) return -1;
    int fd = sd_bus_get_fd(session_watch_state.bus);
    if (fd < 0) session_watch_state.healthy = false;
    else session_watch_state.io_fd = fd;
    return fd;
}
static inline int session_watch_open(const char *sessionid) {
    if (session_watch_state.terminal) return 0;
    sd_bus_message *reply = NULL;
    const char *value = NULL;
    int active = 0, locked = 1, remote = 1;
    session_watch_close();
    if (getuid() != 65534 || geteuid() != 65534 || !sessionid || !*sessionid || strlen(sessionid) > 128) return 0;
    for (const unsigned char *p = (const unsigned char *)sessionid; *p; ++p)
        if (!((*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z') || (*p >= '0' && *p <= '9') || *p == '_' || *p == '-')) return 0;
    if (sw_copy(session_watch_state.id, sizeof session_watch_state.id, sessionid) < 0 ||
        sd_bus_open_system(&session_watch_state.bus) < 0 ||
        sd_bus_set_method_call_timeout(session_watch_state.bus, UINT64_C(100000)) < 0) goto failure;
    if (sd_bus_call_method(session_watch_state.bus, "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "GetNameOwner", NULL, &reply, "s", SW_LOGIND) < 0 ||
        sd_bus_message_read(reply, "s", &value) < 0 || !value || value[0] != ':' ||
        sw_copy(session_watch_state.name, sizeof session_watch_state.name, value) < 0) goto failure;
    reply = sd_bus_message_unref(reply);
    session_watch_state.healthy = true; /* Never restore after subscriptions can dispatch. */
    if (sd_bus_match_signal(session_watch_state.bus, &session_watch_state.owner, "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "NameOwnerChanged", sw_owner, NULL) < 0) goto failure;
    if (sd_bus_call_method(session_watch_state.bus, session_watch_state.name, SW_MANAGER, SW_LOGIND ".Manager", "GetSession", NULL, &reply, "s", sessionid) < 0 ||
        sd_bus_message_read(reply, "o", &value) < 0 || !value || value[0] != '/' ||
        sw_copy(session_watch_state.path, sizeof session_watch_state.path, value) < 0) goto failure;
    reply = sd_bus_message_unref(reply);
    if (sd_bus_match_signal(session_watch_state.bus, &session_watch_state.properties, session_watch_state.name, session_watch_state.path, "org.freedesktop.DBus.Properties", "PropertiesChanged", sw_properties, NULL) < 0 ||
        sd_bus_match_signal(session_watch_state.bus, &session_watch_state.removed, session_watch_state.name, SW_MANAGER, SW_LOGIND ".Manager", "SessionRemoved", sw_removed, NULL) < 0) goto failure;
    /* Callbacks may run while sync property calls pump the connection. Arm the
     * health latch first, and never restore it after a concurrent notification. */
    if (sd_bus_get_property_trivial(session_watch_state.bus, session_watch_state.name, session_watch_state.path, SW_SESSION, "Active", NULL, 'b', &active) < 0 ||
        sd_bus_get_property_trivial(session_watch_state.bus, session_watch_state.name, session_watch_state.path, SW_SESSION, "LockedHint", NULL, 'b', &locked) < 0 ||
        sd_bus_get_property_trivial(session_watch_state.bus, session_watch_state.name, session_watch_state.path, SW_SESSION, "Remote", NULL, 'b', &remote) < 0 ||
        !active || locked || remote) goto failure;
    /* Close the GetNameOwner-to-subscribe race without trusting an old owner
     * that remains connected after giving up the well-known logind name. */
    if (sd_bus_call_method(session_watch_state.bus, "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "GetNameOwner", NULL, &reply, "s", SW_LOGIND) < 0 ||
        sd_bus_message_read(reply, "s", &value) < 0 || !value || strcmp(value, session_watch_state.name)) goto failure;
    reply = sd_bus_message_unref(reply);
    if (!session_watch_ok() || session_watch_fd() < 0) goto failure;
    return 1;
failure:
    sd_bus_message_unref(reply);
    session_watch_close();
    return 0;
}
#endif
