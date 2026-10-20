#define _GNU_SOURCE
/* Fixed root-owned pkexec mechanism. No commands, raw-event export or device
 * paths are accepted from the requester. Installation is a separate step. */
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <libudev.h>
#include <linux/capability.h>
#include <limits.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/sysmacros.h>
#include <sys/un.h>
#include <systemd/sd-login.h>
#include <unistd.h>
#define LDC_NATIVE_WATCH 1
#include "session_watch.h"
#define main collector_main
#include "broker.c"
#undef main

static bool property(struct udev_device *d, const char *key) {
    const char *v=udev_device_get_property_value(d,key);return v&&!strcmp(v,"1");
}
static bool input_bit(const unsigned char *bits,unsigned code) {
    return (bits[code/8]&(1U<<(code%8)))!=0;
}
/* Admission is performed only by the privileged fixed opener, before its
 * descriptors are handed to the unprivileged parser. Udev alone is not proof
 * of an indirect single-finger coordinate protocol. */
static bool verified_touchpad(int fd,struct udev_device *d,struct tp_limits *limits) {
    if(!property(d,"ID_INPUT_TOUCHPAD")||property(d,"ID_INPUT_TOUCHSCREEN")||
       property(d,"ID_INPUT_TABLET")||property(d,"ID_INPUT_JOYSTICK")||
       property(d,"ID_INPUT_KEYBOARD")||property(d,"ID_INPUT_MOUSE"))return false;
    unsigned char props[(INPUT_PROP_MAX+8)/8]={0};
    unsigned char keys[(KEY_MAX+8)/8]={0},abs[(ABS_MAX+8)/8]={0};
    if(ioctl(fd,EVIOCGPROP(sizeof props),props)<0||!input_bit(props,INPUT_PROP_POINTER)||
       input_bit(props,INPUT_PROP_DIRECT)||
       ioctl(fd,EVIOCGBIT(EV_KEY,sizeof keys),keys)<0||
       ioctl(fd,EVIOCGBIT(EV_ABS,sizeof abs),abs)<0||
       !input_bit(keys,BTN_TOUCH)||!input_bit(keys,BTN_TOOL_FINGER)||
       !input_bit(abs,ABS_X)||!input_bit(abs,ABS_Y))return false;
    struct input_absinfo x,y;
    if(ioctl(fd,EVIOCGABS(ABS_X),&x)<0||ioctl(fd,EVIOCGABS(ABS_Y),&y)<0||
       x.minimum>=x.maximum||y.minimum>=y.maximum)return false;
    *limits=(struct tp_limits){.x_min=x.minimum,.x_max=x.maximum,.y_min=y.minimum,.y_max=y.maximum};
    bool mt=false;
    for(unsigned code=ABS_MT_SLOT;code<=ABS_MT_TOOL_Y;code++)mt|=input_bit(abs,code);
    if(mt) {
        if(!input_bit(abs,ABS_MT_SLOT)||!input_bit(abs,ABS_MT_TRACKING_ID)||
           !input_bit(abs,ABS_MT_POSITION_X)||!input_bit(abs,ABS_MT_POSITION_Y))return false;
        struct input_absinfo slot,tracking,mx,my;
        if(ioctl(fd,EVIOCGABS(ABS_MT_SLOT),&slot)<0||
           ioctl(fd,EVIOCGABS(ABS_MT_TRACKING_ID),&tracking)<0||
           ioctl(fd,EVIOCGABS(ABS_MT_POSITION_X),&mx)<0||
           ioctl(fd,EVIOCGABS(ABS_MT_POSITION_Y),&my)<0||
           slot.minimum!=0||slot.maximum<0||slot.maximum>=TP_MAX_SLOTS||
           tracking.minimum!=0||tracking.maximum<0||
           mx.minimum!=x.minimum||mx.maximum!=x.maximum||
           my.minimum!=y.minimum||my.maximum!=y.maximum)return false;
        limits->mt=true;limits->slot_min=slot.minimum;limits->slot_max=slot.maximum;
        limits->tracking_max=tracking.maximum;
    }
    return tp_valid_limits(limits);
}
static char *verified_session;
static int active_local(uid_t uid,pid_t peer_pid) {
    char *session=NULL,*seat=NULL,*type=NULL;uid_t session_uid;int ok=0;
    if(sd_pid_get_session(peer_pid,&session)<0 && sd_uid_get_display(uid,&session)<0)goto done;
    if(sd_session_get_uid(session,&session_uid)<0||session_uid!=uid||
       sd_session_is_active(session)<=0||sd_session_is_remote(session)!=0||
       sd_session_get_seat(session,&seat)<0||strcmp(seat,"seat0")||
       sd_session_get_type(session,&type)<0||strcmp(type,"wayland"))goto done;
    free(verified_session);verified_session=strdup(session);ok=verified_session!=NULL;
done:free(session);free(seat);free(type);return ok;
}
static int connect_request(const char *path,uid_t uid,struct ucred *peer) {
    char base[64];snprintf(base,sizeof base,"/run/user/%u/",uid);
    if(strncmp(path,base,strlen(base)))return -1;
    const char *tail=path+strlen(base);const char *slash=strchr(tail,'/');
    if(!slash||strncmp(tail,"codex-activity-",15)||strcmp(slash,"/observer.sock"))return -1;
    for(const char *p=tail;p<slash;p++)if(!((*p>='a'&&*p<='z')||(*p>='0'&&*p<='9')||*p=='-'||*p=='_'))return -1;
    if(slash-tail<20||slash-tail>64)return -1;
    char directory[PATH_MAX];size_t len=(size_t)(slash-path);if(len>=sizeof directory)return -1;
    memcpy(directory,path,len);directory[len]=0;
    int dir=open(directory,O_PATH|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);struct stat st;
    if(dir<0)return -1;
    if(fstat(dir,&st)||st.st_uid!=uid||(st.st_mode&0777)!=0700){close(dir);return -1;}
    int fd=socket(AF_UNIX,SOCK_STREAM|SOCK_CLOEXEC,0);struct sockaddr_un addr={.sun_family=AF_UNIX};
    snprintf(addr.sun_path,sizeof addr.sun_path,"/proc/self/fd/%d/observer.sock",dir);
    if(fd<0||connect(fd,(struct sockaddr*)&addr,sizeof addr)){if(fd>=0)close(fd);close(dir);return -1;}
    close(dir);socklen_t size=sizeof *peer;
    if(getsockopt(fd,SOL_SOCKET,SO_PEERCRED,peer,&size)||size!=sizeof *peer||peer->uid!=uid||peer->pid<=1){close(fd);return -1;}
    return fd;
}
int main(int argc,char **argv) {
    if(getuid()!=0||geteuid()!=0||argc!=3||strcmp(argv[1],"--socket"))return 1;
    const char *who=getenv("PKEXEC_UID");if(!who||!*who)return 1;
    char *end;errno=0;unsigned long user=strtoul(who,&end,10);
    if(errno||*end||user==0||user>UINT_MAX)return 1;
    uid_t uid=(uid_t)user;struct ucred peer;
    int phase=2;
    int control=connect_request(argv[2],uid,&peer);if(control<0)return 1;
    if(!active_local(uid,peer.pid)){send(control,"FAULT\n",6,MSG_NOSIGNAL);return 42;}
    phase=3;
    int parent=-1;socklen_t parent_size=sizeof parent;
    if(getsockopt(control,SOL_SOCKET,SO_PEERPIDFD,&parent,&parent_size)||parent<0||parent_size!=sizeof parent)goto fault;
    phase=4;
    struct udev *u=udev_new();if(!u)goto fault;
    struct udev_monitor *monitor=udev_monitor_new_from_netlink(u,"udev");
    if(!monitor||udev_monitor_filter_add_match_subsystem_devtype(monitor,"input",NULL)<0||udev_monitor_enable_receiving(monitor)<0)goto fault;
    int topology=udev_monitor_get_fd(monitor);if(topology<0)goto fault;
    phase=5;
    struct udev_enumerate *enumeration=udev_enumerate_new(u);if(!enumeration)goto fault;
    if(udev_enumerate_add_match_subsystem(enumeration,"input")<0||udev_enumerate_add_match_sysname(enumeration,"event*")<0||udev_enumerate_scan_devices(enumeration)<0)goto fault;
    phase=6;
    int devices[MAX_DEVICES],snapshots[MAX_DEVICES],count=0;bool keyboard=false,pointer=false;
    struct udev_list_entry *entry;
    udev_list_entry_foreach(entry,udev_enumerate_get_list_entry(enumeration)) {
        const char *syspath=udev_list_entry_get_name(entry);
        struct udev_device *d=udev_device_new_from_syspath(u,syspath);if(!d)goto fault;
        bool key=property(d,"ID_INPUT_KEYBOARD"),ptr=property(d,"ID_INPUT_MOUSE")||property(d,"ID_INPUT_TOUCHPAD")||property(d,"ID_INPUT_TOUCHSCREEN");
        bool human=key||ptr||property(d,"ID_INPUT_KEY")||property(d,"ID_INPUT_TABLET")||property(d,"ID_INPUT_JOYSTICK")||property(d,"ID_INPUT_SWITCH");
        if(!human){bool sensor=property(d,"ID_INPUT_ACCELEROMETER");udev_device_unref(d);if(sensor)continue;goto fault;}
        const char *seat=udev_device_get_property_value(d,"ID_SEAT");
        if(seat&&strcmp(seat,"seat0")){udev_device_unref(d);continue;}
        /* Include UHID/uinput kernel devices conservatively. Portal virtual
         * input lives inside Mutter and creates no evdev stream. A kernel
         * event is not human provenance attestation. */
        if(!syspath||strncmp(syspath,"/sys/devices/",13)){udev_device_unref(d);goto fault;}
        
        const char *node=udev_device_get_devnode(d);dev_t expected=udev_device_get_devnum(d);
        if(!node||strncmp(node,"/dev/input/event",16)||count==MAX_DEVICES){udev_device_unref(d);goto fault;}
        int fd=open(node,O_RDONLY|O_NONBLOCK|O_CLOEXEC|O_NOFOLLOW);struct stat info;
        if(fd<0||fstat(fd,&info)||!S_ISCHR(info.st_mode)||info.st_rdev!=expected||major(info.st_rdev)!=13){if(fd>=0)close(fd);udev_device_unref(d);goto fault;}
        /* Set the stream clock before capability queries, snapshot opens and
         * the rest of enumeration. A clock change can queue SYN_DROPPED for
         * pending events; keep that startup window as small as possible.
         * Collector verify may repeat the same clock without changing it.
         * This does not replace explicit unarmed resynchronization. */
        int stream_clock=CLOCK_MONOTONIC;
        if(ioctl(fd,EVIOCSCLOCKID,&stream_clock)<0){close(fd);udev_device_unref(d);goto fault;}
        unsigned long capabilities[(EV_MAX+8*sizeof(long))/(8*sizeof(long))]={0};
        if(ioctl(fd,EVIOCGBIT(0,sizeof capabilities),capabilities)<0){close(fd);udev_device_unref(d);goto fault;}
        bool has_key=(capabilities[EV_KEY/(8*sizeof(long))]>>(EV_KEY%(8*sizeof(long))))&1;
        bool has_switch=(capabilities[EV_SW/(8*sizeof(long))]>>(EV_SW%(8*sizeof(long))))&1;
        bool has_motion=((capabilities[EV_REL/(8*sizeof(long))]>>(EV_REL%(8*sizeof(long))))&1)||((capabilities[EV_ABS/(8*sizeof(long))]>>(EV_ABS%(8*sizeof(long))))&1);
        if((key&&!has_key)||(ptr&&!has_motion)||(!has_key&&!has_motion&&!has_switch)){close(fd);udev_device_unref(d);goto fault;}
        /* Unadmitted pads remain covered by the unchanged terminal activity
         * path. They do not gain contact exemptions or MODEYIELD3 credit. */
        device_touchpad[count]=property(d,"ID_INPUT_TOUCHPAD")&&verified_touchpad(fd,d,&touchpad_limits[count]);
        tp_reset(&touchpad_states[count]);
        /* EVIOCGKEY flushes its evdev client's key queue. A second OPEN,
         * never dup(), keeps held-state sampling off the event-stream client. */
        int snapshot=open(node,O_RDONLY|O_NONBLOCK|O_CLOEXEC|O_NOFOLLOW);struct stat snapshot_info;
        if(snapshot<0||fstat(snapshot,&snapshot_info)||!S_ISCHR(snapshot_info.st_mode)||snapshot_info.st_rdev!=expected){if(snapshot>=0)close(snapshot);close(fd);udev_device_unref(d);goto fault;}
        device_categories[count]=(key?CATEGORY_KEYBOARD:0)|(ptr?CATEGORY_POINTER:0);
        devices[count]=fd;snapshots[count]=snapshot;count++;keyboard|=key;pointer|=ptr;udev_device_unref(d);
    }
    phase=7;
    if(!count||!keyboard||!pointer||!active_local(uid,peer.pid))goto fault;
    /* Duplicate before moving, so arbitrary source fd numbers cannot collide. */
    phase=8;
    int source[2*MAX_DEVICES+3];source[0]=control;
    for(int i=0;i<count;i++){source[i+1]=devices[i];}
    source[count+1]=topology;source[count+2]=parent;
    for(int i=0;i<count;i++){source[count+3+i]=snapshots[i];}
    for(int i=0;i<2*count+3;i++){source[i]=fcntl(source[i],F_DUPFD_CLOEXEC,256);if(source[i]<0)goto fault;}
    for(int i=0;i<2*count+3;i++)if(dup2(source[i],3+i)<0)goto fault;
    control=3;
    if(syscall(SYS_close_range,(unsigned)(2*count+6),UINT_MAX,0))goto fault;
    int null=open("/dev/null",O_RDWR|O_CLOEXEC);if(null<0)goto fault;
    for(int i=0;i<3;i++){if(dup2(null,i)<0)goto fault;}
    if(null>2)close(null);
    phase=9;
    for(int cap=0;cap<=CAP_LAST_CAP;cap++)if(prctl(PR_CAPBSET_DROP,cap,0,0,0)&&errno!=EINVAL)goto fault;
    if(setgroups(0,NULL)||setresgid(65534,65534,65534)||setresuid(65534,65534,65534)||prctl(PR_SET_DUMPABLE,0)||prctl(PR_SET_NO_NEW_PRIVS,1,0,0,0))goto fault;
    phase=10;
    if(!session_watch_open(verified_session))goto fault;
    char number[16];snprintf(number,sizeof number,"%d",count);char *args[]={"collector",number,NULL};
    int result=collector_main(2,args);return result?100+result:0;
fault:
    send(control,"FAULT\n",6,MSG_NOSIGNAL|MSG_DONTWAIT);
    return 40+phase; /* Process exit closes every remaining descriptor. */
}
