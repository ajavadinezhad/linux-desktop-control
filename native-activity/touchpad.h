#ifndef LDC_TOUCHPAD_H
#define LDC_TOUCHPAD_H
/* Private, bounded evdev frame parser. No I/O and no coordinate export. */
#include <stdbool.h>
#include <string.h>
#include <linux/input.h>
#define TP_MAX_SLOTS 16
enum tp_result { TP_UNSUPPORTED=-1, TP_NONE=0, TP_CONTACT=1, TP_MOTION=2 };
struct tp_limits { int x_min,x_max,y_min,y_max; bool mt; int slot_min,slot_max,tracking_max; };
struct tp_state {
    bool touch,finger,pending,baseline,x_seen,y_seen,frame_had_contact,coordinate_frame;
    int x,y,old_x,old_y,slot;
    bool slot_selected;
    int tracking[TP_MAX_SLOTS];
};
static void tp_reset(struct tp_state *s) {
    memset(s,0,sizeof *s);
    for(int i=0;i<TP_MAX_SLOTS;i++)s->tracking[i]=-1;
}
static bool tp_active(const struct tp_state *s) {
    if(s->touch||s->finger)return true;
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
static enum tp_result tp_event(struct tp_state *s,const struct input_event *e,const struct tp_limits *l) {
    if(!s||!e||!tp_valid_limits(l))return TP_UNSUPPORTED;
    if(e->type==EV_SYN) {
        if(e->code!=SYN_REPORT||e->value!=0)return TP_UNSUPPORTED;
        int contacts=0;
        for(int i=0;i<TP_MAX_SLOTS;i++)contacts+=s->tracking[i]>=0;
        if(s->touch!=s->finger||(l->mt&&contacts!=(s->touch?1:0)))return TP_UNSUPPORTED;
        if(!s->touch&&s->coordinate_frame&&!s->frame_had_contact)return TP_UNSUPPORTED;
        s->pending=false;
        s->frame_had_contact=s->coordinate_frame=false;
        if(!s->touch){tp_new_contact(s);return TP_NONE;}
        if(!s->x_seen||!s->y_seen)return TP_NONE;
        bool moved=s->baseline&&(s->x!=s->old_x||s->y!=s->old_y);
        s->old_x=s->x;s->old_y=s->y;s->baseline=true;
        return moved?TP_MOTION:TP_NONE;
    }
    if(e->type==EV_MSC&&e->code==MSC_TIMESTAMP)return TP_NONE;
    s->frame_had_contact|=tp_active(s);
    s->pending=true;
    if(e->type==EV_KEY) {
        if((e->code!=BTN_TOUCH&&e->code!=BTN_TOOL_FINGER)||(e->value!=0&&e->value!=1))return TP_UNSUPPORTED;
        bool before=tp_active(s);
        bool *bit=e->code==BTN_TOUCH?&s->touch:&s->finger;
        if(*bit==(bool)e->value)return TP_UNSUPPORTED;
        *bit=e->value!=0;
        if(!e->value)tp_new_contact(s);
        else if(!before)tp_new_contact(s);
        s->frame_had_contact|=e->value!=0;
        return e->value?TP_CONTACT:TP_NONE;
    }
    if(e->type!=EV_ABS)return TP_UNSUPPORTED;
    switch(e->code) {
    case ABS_X: case ABS_Y: {
        bool x=e->code==ABS_X;
        if(e->value<(x?l->x_min:l->y_min)||e->value>(x?l->x_max:l->y_max))return TP_UNSUPPORTED;
        if(x){s->x=e->value;s->x_seen=true;}else{s->y=e->value;s->y_seen=true;}
        s->coordinate_frame=true;
        return TP_NONE;
    }
    case ABS_MT_SLOT:
        if(!l->mt||e->value<l->slot_min||e->value>l->slot_max)return TP_UNSUPPORTED;
        s->slot=e->value;s->slot_selected=true;return TP_NONE;
    case ABS_MT_TRACKING_ID: {
        if(!l->mt||e->value< -1||e->value>l->tracking_max)return TP_UNSUPPORTED;
        /* Type-B slot zero is implicit before its first explicit selection. */
        int slot=s->slot_selected?s->slot:0;
        if(slot<l->slot_min||slot>l->slot_max)return TP_UNSUPPORTED;
        if(e->value==-1) {
            if(s->tracking[slot]<0)return TP_UNSUPPORTED;
            s->tracking[slot]=-1;tp_new_contact(s);return TP_NONE;
        }
        if(s->tracking[slot]>=0)return TP_UNSUPPORTED;
        for(int i=0;i<TP_MAX_SLOTS;i++)if(s->tracking[i]>=0)return TP_UNSUPPORTED;
        s->tracking[slot]=e->value;tp_new_contact(s);s->frame_had_contact=true;return TP_CONTACT;
    }
    case ABS_MT_POSITION_X: case ABS_MT_POSITION_Y:
        if(!l->mt||s->tracking[s->slot_selected?s->slot:0]<0)return TP_UNSUPPORTED;
        if(e->value<(e->code==ABS_MT_POSITION_X?l->x_min:l->y_min)||
           e->value>(e->code==ABS_MT_POSITION_X?l->x_max:l->y_max))return TP_UNSUPPORTED;
        return TP_NONE;
    /* Metadata never earns motion credit. Opener verifies this device class. */
    case ABS_PRESSURE: case ABS_TOOL_WIDTH:
        return e->value>=0?TP_NONE:TP_UNSUPPORTED;
    case ABS_MT_PRESSURE: case ABS_MT_TOUCH_MAJOR: case ABS_MT_TOUCH_MINOR:
    case ABS_MT_WIDTH_MAJOR: case ABS_MT_WIDTH_MINOR:
        return l->mt&&s->tracking[s->slot_selected?s->slot:0]>=0&&e->value>=0?TP_NONE:TP_UNSUPPORTED;
    default:return TP_UNSUPPORTED;
    }
}
#endif
