#ifndef LDC_TOUCHPAD_H
#define LDC_TOUCHPAD_H
/* Private, bounded evdev frame parser. No I/O and no coordinate export. */
#include <stdbool.h>
#include <string.h>
#include <linux/input.h>
#define TP_MAX_SLOTS 16
enum tp_reject_reason { TP_REJECT_NONE, TP_REJECT_CONFIGURATION, TP_REJECT_FRAME,
    TP_REJECT_TOOLS, TP_REJECT_STATE, TP_REJECT_LIMIT, TP_REJECT_COUNT,
    TP_REJECT_COORDINATE_CONTACT, TP_REJECT_KEY, TP_REJECT_EVENT_TYPE, TP_REJECT_AXIS_TYPE, TP_REJECT_VALUE,
    TP_REJECT_DUPLICATE_STATE, TP_REJECT_AXIS, TP_REJECT_SLOT, TP_REJECT_TRACKING,
    TP_REJECT_CONTACT_SLOT, TP_REJECT_DUPLICATE_CONTACT, TP_REJECT_RELEASE };
static inline const char *tp_reject_name(enum tp_reject_reason reason) {
    static const char *const names[]={"none","invalid-configuration","frame-invalid",
        "tool-cardinality","contact-state","contact-limit","contact-count",
        "coordinate-without-contact","unsupported-key","unsupported-event-type","unsupported-axis","invalid-value",
        "duplicate-state","axis-range","slot-range","tracking-range",
        "contact-without-slot","duplicate-contact","contact-release"};
    return (unsigned)reason<sizeof names/sizeof names[0]?names[reason]:"invalid-configuration";
}
enum tp_result { TP_UNSUPPORTED=-1, TP_NONE=0, TP_CONTACT=1, TP_MOTION=2, TP_INTERVENTION=3 };
struct tp_limits { int x_min,x_max,y_min,y_max; bool mt; int slot_min,slot_max,tracking_max; };
struct tp_state {
    enum tp_reject_reason reject_reason;
    bool double_finger,triple_finger,quad_finger,gesture_sticky;
    bool touch,finger,pending,baseline,x_seen,y_seen,frame_had_contact,coordinate_frame;
    int x,y,old_x,old_y,slot;
    bool slot_selected;
    int tracking[TP_MAX_SLOTS];
};
static enum tp_result tp_reject(struct tp_state *s,enum tp_reject_reason reason) {
    if(s&&s->reject_reason==TP_REJECT_NONE)s->reject_reason=reason;
    return TP_UNSUPPORTED;
}
static void tp_reset(struct tp_state *s) {
    memset(s,0,sizeof *s);
    for(int i=0;i<TP_MAX_SLOTS;i++)s->tracking[i]=-1;
}
static bool tp_active(const struct tp_state *s) {
    if(s->touch||s->finger||s->double_finger||s->triple_finger||s->quad_finger)return true;
    for(int i=0;i<TP_MAX_SLOTS;i++)if(s->tracking[i]>=0)return true;
    return false;
}
static bool tp_incomplete(const struct tp_state *s) { return s->pending; }
static void tp_new_contact(struct tp_state *s) {
    s->baseline=false;s->x_seen=s->y_seen=false;
}
static bool tp_valid_limits(const struct tp_limits *l) {
    return l&&l->x_min<l->x_max&&l->y_min<l->y_max&&
        (!l->mt||(l->slot_min==0&&l->slot_max>=0&&l->slot_max<TP_MAX_SLOTS&&l->tracking_max>=0));
}
static enum tp_result tp_event_contacts(struct tp_state *s,const struct input_event *e,const struct tp_limits *l,int max_contacts) {
    if(!s||!e||!tp_valid_limits(l)||(max_contacts!=1&&max_contacts!=2&&max_contacts!=4))return tp_reject(s,TP_REJECT_CONFIGURATION);
    if(e->type==EV_SYN) {
        if(e->code!=SYN_REPORT||e->value!=0)return tp_reject(s,TP_REJECT_FRAME);
        int contacts=0;
        for(int i=0;i<TP_MAX_SLOTS;i++)contacts+=s->tracking[i]>=0;
        int tools=(s->finger?1:0)+(s->double_finger?1:0)+(s->triple_finger?1:0)+(s->quad_finger?1:0);
        int expected=s->quad_finger?4:(s->triple_finger?3:(s->double_finger?2:(s->finger?1:0)));
        if(tools>1)return tp_reject(s,TP_REJECT_TOOLS);
        if(s->touch!=(tools==1))return tp_reject(s,TP_REJECT_STATE);
        if(expected>max_contacts)return tp_reject(s,TP_REJECT_LIMIT);
        if(l->mt&&contacts!=expected)return tp_reject(s,TP_REJECT_COUNT);
        if(!s->touch&&s->coordinate_frame&&!s->frame_had_contact)return tp_reject(s,TP_REJECT_COORDINATE_CONTACT);
        s->pending=false;
        s->frame_had_contact=s->coordinate_frame=false;
        if(!s->touch){tp_new_contact(s);s->gesture_sticky=false;return TP_NONE;}
        /* Multiple contacts are an intervention, never pointer-motion proof.
         * Keep that classification until ALL contacts lift, even after 4->3->2->1. */
        if(expected>1||s->gesture_sticky){tp_new_contact(s);return TP_INTERVENTION;}
        if(!s->x_seen||!s->y_seen)return TP_NONE;
        bool moved=s->baseline&&(s->x!=s->old_x||s->y!=s->old_y);
        s->old_x=s->x;s->old_y=s->y;s->baseline=true;
        return moved?TP_MOTION:TP_NONE;
    }
    if(e->type==EV_MSC&&e->code==MSC_TIMESTAMP)return TP_NONE;
    s->frame_had_contact|=tp_active(s);
    s->pending=true;
    if(e->type==EV_KEY) {
        if(e->code!=BTN_TOUCH&&e->code!=BTN_TOOL_FINGER&&!(max_contacts>=2&&e->code==BTN_TOOL_DOUBLETAP)&&!(max_contacts==4&&(e->code==BTN_TOOL_TRIPLETAP||e->code==BTN_TOOL_QUADTAP)))return tp_reject(s,TP_REJECT_KEY);
        if(e->value!=0&&e->value!=1)return tp_reject(s,TP_REJECT_VALUE);
        bool before=tp_active(s);
        bool *bit=e->code==BTN_TOUCH?&s->touch:(e->code==BTN_TOOL_FINGER?&s->finger:(e->code==BTN_TOOL_DOUBLETAP?&s->double_finger:(e->code==BTN_TOOL_TRIPLETAP?&s->triple_finger:&s->quad_finger)));
        if(*bit==(bool)e->value)return tp_reject(s,TP_REJECT_DUPLICATE_STATE);
        *bit=e->value!=0;
        if(!e->value)tp_new_contact(s);
        else if(!before)tp_new_contact(s);
        s->frame_had_contact|=e->value!=0;
        if(e->code!=BTN_TOUCH&&e->code!=BTN_TOOL_FINGER&&e->value)s->gesture_sticky=true;
        return s->gesture_sticky?TP_INTERVENTION:(e->value?TP_CONTACT:TP_NONE);
    }
    if(e->type!=EV_ABS)return tp_reject(s,TP_REJECT_EVENT_TYPE);
    switch(e->code) {
    case ABS_X: case ABS_Y: {
        bool x=e->code==ABS_X;
        if(e->value<(x?l->x_min:l->y_min)||e->value>(x?l->x_max:l->y_max))return tp_reject(s,TP_REJECT_AXIS);
        if(x){s->x=e->value;s->x_seen=true;}else{s->y=e->value;s->y_seen=true;}
        s->coordinate_frame=true;
        return TP_NONE;
    }
    case ABS_MT_SLOT:
        if(!l->mt||e->value<l->slot_min||e->value>l->slot_max)return tp_reject(s,TP_REJECT_SLOT);
        s->slot=e->value;s->slot_selected=true;return TP_NONE;
    case ABS_MT_TRACKING_ID: {
        if(!l->mt||e->value< -1||e->value>l->tracking_max)return tp_reject(s,TP_REJECT_TRACKING);
        /* Type-B slot zero is implicit before its first explicit selection. */
        int slot=s->slot_selected?s->slot:0;
        if(slot<l->slot_min||slot>l->slot_max)return tp_reject(s,TP_REJECT_SLOT);
        if(e->value==-1) {
            if(s->tracking[slot]<0)return tp_reject(s,TP_REJECT_RELEASE);
            s->tracking[slot]=-1;tp_new_contact(s);return TP_NONE;
        }
        if(s->tracking[slot]>=0)return tp_reject(s,TP_REJECT_DUPLICATE_CONTACT);
        int count=0;
        for(int i=0;i<TP_MAX_SLOTS;i++)if(s->tracking[i]>=0){
            if(s->tracking[i]==e->value)return tp_reject(s,TP_REJECT_DUPLICATE_CONTACT);
            count++;
        }
        if(count>=max_contacts)return tp_reject(s,TP_REJECT_LIMIT);
        if(count)s->gesture_sticky=true;
        s->tracking[slot]=e->value;tp_new_contact(s);s->frame_had_contact=true;return s->gesture_sticky?TP_INTERVENTION:TP_CONTACT;
    }
    case ABS_MT_POSITION_X: case ABS_MT_POSITION_Y:
        if(!l->mt||s->tracking[s->slot_selected?s->slot:0]<0)return tp_reject(s,TP_REJECT_CONTACT_SLOT);
        if(e->value<(e->code==ABS_MT_POSITION_X?l->x_min:l->y_min)||
           e->value>(e->code==ABS_MT_POSITION_X?l->x_max:l->y_max))return tp_reject(s,TP_REJECT_AXIS);
        return TP_NONE;
    /* Metadata never earns motion credit. Opener verifies this device class. */
    case ABS_PRESSURE: case ABS_TOOL_WIDTH:
        return e->value>=0?TP_NONE:tp_reject(s,TP_REJECT_VALUE);
    case ABS_MT_PRESSURE: case ABS_MT_TOUCH_MAJOR: case ABS_MT_TOUCH_MINOR:
    case ABS_MT_WIDTH_MAJOR: case ABS_MT_WIDTH_MINOR:
        if(!l->mt||s->tracking[s->slot_selected?s->slot:0]<0)return tp_reject(s,TP_REJECT_CONTACT_SLOT);
        return e->value>=0?TP_NONE:tp_reject(s,TP_REJECT_VALUE);
    default:return tp_reject(s,TP_REJECT_AXIS_TYPE);
    }
}
static enum tp_result tp_event_mode(struct tp_state *s,const struct input_event *e,const struct tp_limits *l,bool allow_two) {
    return tp_event_contacts(s,e,l,allow_two?2:1);
}
static enum tp_result tp_event(struct tp_state *s,const struct input_event *e,const struct tp_limits *l) {
    return tp_event_mode(s,e,l,false);
}
#endif
