#ifndef LDC_ACTIVITY_CONFINEMENT_H
#define LDC_ACTIVITY_CONFINEMENT_H
/* Include after device_count, CONTROL and session_watch_fd() declarations.
 * Call only after descriptor setup, session-watch setup and verify().
 * This filter cannot inspect sendmsg ancillary buffers: the fixed collector
 * must never construct SCM_RIGHTS. Do not describe it as an SCM_RIGHTS filter.
 */
#include <linux/audit.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <stddef.h>
#include <sys/mman.h>
#include <sys/syscall.h>

static int confine_collector(void) {
#if !defined(__x86_64__) || defined(__ILP32__)
    errno = ENOTSUP;
    return -1;
#else
    struct rlimit core = {0, 0};
    if (setrlimit(RLIMIT_CORE, &core) ||
        prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)) return -1;
    int bus = session_watch_fd();
    if (device_count < 1 || device_count > MAX_DEVICES || bus < 0 ||
        bus <= 5 + 2*device_count) { errno = EINVAL; return -1; }
    struct sock_filter f[256]; unsigned n = 0;
#define ST(code, k) do { f[n++] = (struct sock_filter)BPF_STMT(code, k); } while (0)
#define JP(code, k, t, e) do { f[n++] = (struct sock_filter)BPF_JUMP(code, k, t, e); } while (0)
#define OK() ST(BPF_RET | BPF_K, SECCOMP_RET_ALLOW)
#define NO() ST(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM)
#define ARG(i) ST(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, args[i]))
#define NR() ST(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr))
#define ALLOW(name) do { JP(BPF_JMP | BPF_JEQ | BPF_K, SYS_##name, 0, 1); OK(); } while (0)
    ST(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, arch));
    JP(BPF_JMP | BPF_JEQ | BPF_K, AUDIT_ARCH_X86_64, 1, 0);
    ST(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS);
    NR();
    /* Reject the x32 ABI even though its audit architecture is x86_64. */
    JP(BPF_JMP | BPF_JSET | BPF_K, 0x40000000U, 0, 1);
    ST(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS);
    ALLOW(read); ALLOW(readv); ALLOW(close);
    ALLOW(poll); ALLOW(ppoll); ALLOW(clock_gettime); ALLOW(clock_nanosleep);
    ALLOW(futex); ALLOW(brk); ALLOW(munmap); ALLOW(mremap); ALLOW(madvise);
    ALLOW(rt_sigreturn); ALLOW(rt_sigaction); ALLOW(rt_sigprocmask);
    ALLOW(sigaltstack); ALLOW(restart_syscall);
    ALLOW(exit); ALLOW(exit_group);
    ALLOW(getuid); ALLOW(geteuid); ALLOW(getgid); ALLOW(getegid);
    ALLOW(getpid); ALLOW(gettid); ALLOW(fstat); ALLOW(newfstatat);
    ALLOW(getrlimit); ALLOW(prlimit64);
    /* All writable channels are established before confinement. No sockets,
     * connect, open, exec, fork/clone, dup, splice or process-memory syscalls. */
    unsigned writes[] = {SYS_write, SYS_writev, SYS_sendto};
    for (unsigned i=0; i<sizeof writes/sizeof *writes; ++i) {
        JP(BPF_JMP | BPF_JEQ | BPF_K, writes[i], 0, 5);
        ARG(0);
        JP(BPF_JMP | BPF_JEQ | BPF_K, CONTROL, 2, 0);
        JP(BPF_JMP | BPF_JEQ | BPF_K, (unsigned)bus, 1, 0);
        NO(); OK();
    }
    JP(BPF_JMP | BPF_JEQ | BPF_K, SYS_sendmsg, 0, 4);
    ARG(0); JP(BPF_JMP | BPF_JEQ | BPF_K, (unsigned)bus, 1, 0); NO(); OK();
    /* Only the authenticated system-bus connection may receive ancillary data.
     * recvfrom is used by some bus libraries for ordinary stream reads. */
    unsigned receives[] = {SYS_recvmsg};
    for (unsigned i=0; i<sizeof receives/sizeof *receives; ++i) {
        JP(BPF_JMP | BPF_JEQ | BPF_K, receives[i], 0, 4);
        ARG(0);
        JP(BPF_JMP | BPF_JEQ | BPF_K, (unsigned)bus, 1, 0);
        NO(); OK();
    }
    /* Broker control uses recv(), implemented as recvfrom on Linux x86_64. */
    JP(BPF_JMP | BPF_JEQ | BPF_K, SYS_recvfrom, 0, 5);
    ARG(0);
    JP(BPF_JMP | BPF_JEQ | BPF_K, CONTROL, 2, 0);
    JP(BPF_JMP | BPF_JEQ | BPF_K, (unsigned)bus, 1, 0);
    NO(); OK();
    /* getsockopt is read-only but restrict it to the established bus channel. */
    JP(BPF_JMP | BPF_JEQ | BPF_K, SYS_getsockopt, 0, 4);
    ARG(0); JP(BPF_JMP | BPF_JEQ | BPF_K, (unsigned)bus, 1, 0); NO(); OK();
    /* EVIOCGKEY is allowed only on independently opened snapshot clients:
     * n+6 .. 2n+5. Querying primary stream clients can flush queued key events.
     * Mask only
     * _IOC_SIZE; direction/type/number must match the read-only key query. */
    JP(BPF_JMP | BPF_JEQ | BPF_K, SYS_ioctl, 0, 10);
    ARG(0);
    JP(BPF_JMP | BPF_JGE | BPF_K, (unsigned)(6+device_count), 1, 0); NO();
    JP(BPF_JMP | BPF_JGE | BPF_K, (unsigned)(6+2*device_count), 0, 1); NO();
    ARG(1); ST(BPF_ALU | BPF_AND | BPF_K, 0xc000ffffU);
    JP(BPF_JMP | BPF_JEQ | BPF_K, (unsigned)EVIOCGKEY(0), 1, 0); NO(); OK();
    /* Allocator mappings and protection changes must never create executable
     * memory. mmap requires MAP_ANONYMOUS; no new FD-backed mappings. */
    JP(BPF_JMP | BPF_JEQ | BPF_K, SYS_mmap, 0, 7);
    ARG(2); JP(BPF_JMP | BPF_JSET | BPF_K, PROT_EXEC, 0, 1); NO();
    ARG(3); JP(BPF_JMP | BPF_JSET | BPF_K, MAP_ANONYMOUS, 1, 0); NO(); OK();
    JP(BPF_JMP | BPF_JEQ | BPF_K, SYS_mprotect, 0, 4);
    ARG(2); JP(BPF_JMP | BPF_JSET | BPF_K, PROT_EXEC, 0, 1); NO(); OK();
    NO();
    struct sock_fprog program = {.len=(unsigned short)n, .filter=f};
#undef ST
#undef JP
#undef OK
#undef NO
#undef ARG
#undef NR
#undef ALLOW
    return prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program);
#endif
}
#endif
