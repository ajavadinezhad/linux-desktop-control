#!/usr/bin/env python3
"""Compile and exercise the private parser without opening input devices."""
import pathlib
import subprocess
import tempfile
import unittest


class TouchpadParserTest(unittest.TestCase):
    def test_frames_and_fail_closed_edges(self):
        directory = pathlib.Path(__file__).resolve().parent
        source = r'''
#include <assert.h>
#include "touchpad.h"
static struct tp_limits plain={0,1000,0,1000,false,0,0,0};
static struct tp_limits multi={0,1000,0,1000,true,0,3,65535};
static enum tp_result ev(struct tp_state*s,struct tp_limits*l,int t,int c,int v){
 struct input_event e={.type=t,.code=c,.value=v};return tp_event(s,&e,l);
}
#define E(t,c,v) ev(&s,&plain,t,c,v)
#define M(t,c,v) ev(&s,&multi,t,c,v)
static void down(struct tp_state*s,struct tp_limits*l){
 assert(ev(s,l,EV_KEY,BTN_TOUCH,1)==TP_CONTACT);
 assert(ev(s,l,EV_KEY,BTN_TOOL_FINGER,1)==TP_CONTACT);
}
int main(void){
 struct tp_state s;tp_reset(&s);
 assert(!tp_active(&s)&&!tp_incomplete(&s));
 down(&s,&plain);assert(tp_active(&s)&&tp_incomplete(&s));
 assert(E(EV_ABS,ABS_X,100)==TP_NONE);
 assert(E(EV_ABS,ABS_Y,100)==TP_NONE);
 assert(E(EV_SYN,SYN_REPORT,0)==TP_NONE); /* baseline only */
 assert(tp_active(&s)&&!tp_incomplete(&s));
 assert(E(EV_ABS,ABS_X,120)==TP_NONE);
 assert(E(EV_SYN,SYN_REPORT,0)==TP_MOTION); /* horizontal */
 assert(E(EV_SYN,SYN_REPORT,0)==TP_NONE);
 assert(E(EV_ABS,ABS_Y,140)==TP_NONE);
 assert(E(EV_SYN,SYN_REPORT,0)==TP_MOTION); /* vertical */
 assert(E(EV_ABS,ABS_PRESSURE,9)==TP_NONE);
 assert(E(EV_SYN,SYN_REPORT,0)==TP_NONE); /* metadata no motion */
 assert(E(EV_KEY,BTN_TOUCH,0)==TP_NONE);
 assert(E(EV_KEY,BTN_TOOL_FINGER,0)==TP_NONE);
 assert(E(EV_SYN,SYN_REPORT,0)==TP_NONE);assert(!tp_active(&s));
 down(&s,&plain);E(EV_ABS,ABS_X,900);E(EV_ABS,ABS_Y,900);
 assert(E(EV_SYN,SYN_REPORT,0)==TP_NONE); /* new finger jump */
 tp_reset(&s);down(&s,&plain);E(EV_ABS,ABS_X,100);
 assert(E(EV_SYN,SYN_REPORT,0)==TP_NONE); /* no mixed Y */
 E(EV_ABS,ABS_Y,200);assert(E(EV_SYN,SYN_REPORT,0)==TP_NONE);
 E(EV_ABS,ABS_X,101);assert(E(EV_SYN,SYN_REPORT,0)==TP_MOTION);
 assert(E(EV_KEY,BTN_LEFT,1)==TP_UNSUPPORTED);
 assert(E(EV_KEY,BTN_TOOL_DOUBLETAP,1)==TP_UNSUPPORTED);
 assert(E(EV_REL,REL_WHEEL,1)==TP_UNSUPPORTED);
 assert(E(EV_ABS,ABS_X,1001)==TP_UNSUPPORTED);
 assert(E(EV_ABS,ABS_Y,-1)==TP_UNSUPPORTED);
 assert(E(EV_ABS,ABS_MT_SLOT,0)==TP_UNSUPPORTED);
 assert(E(EV_SYN,SYN_DROPPED,0)==TP_UNSUPPORTED);
 assert(E(EV_SYN,SYN_REPORT,1)==TP_UNSUPPORTED);
 assert(E(EV_MSC,MSC_SCAN,0)==TP_UNSUPPORTED);
 assert(E(EV_KEY,BTN_TOUCH,2)==TP_UNSUPPORTED);
 tp_reset(&s);E(EV_KEY,BTN_TOUCH,1);
 assert(E(EV_SYN,SYN_REPORT,0)==TP_UNSUPPORTED); /* inconsistent */
 tp_reset(&s);assert(M(EV_ABS,ABS_MT_TRACKING_ID,8)==TP_CONTACT);
 down(&s,&multi);M(EV_ABS,ABS_X,10);M(EV_ABS,ABS_Y,20);
 assert(M(EV_ABS,ABS_MT_POSITION_X,10)==TP_NONE);
 assert(M(EV_ABS,ABS_MT_POSITION_Y,20)==TP_NONE);
 assert(M(EV_SYN,SYN_REPORT,0)==TP_NONE);
 M(EV_ABS,ABS_X,11);assert(M(EV_SYN,SYN_REPORT,0)==TP_MOTION);
 assert(M(EV_ABS,ABS_MT_SLOT,1)==TP_NONE);
 assert(M(EV_ABS,ABS_MT_TRACKING_ID,9)==TP_UNSUPPORTED); /* second */
 tp_reset(&s);assert(M(EV_ABS,ABS_MT_SLOT,4)==TP_UNSUPPORTED);
 assert(M(EV_ABS,ABS_MT_SLOT,-1)==TP_UNSUPPORTED);
 assert(M(EV_ABS,ABS_MT_TRACKING_ID,-2)==TP_UNSUPPORTED);
 assert(M(EV_ABS,ABS_MT_TRACKING_ID,65536)==TP_UNSUPPORTED);
 assert(M(EV_ABS,ABS_MT_TRACKING_ID,-1)==TP_UNSUPPORTED);
 assert(M(EV_ABS,ABS_MT_POSITION_X,10)==TP_UNSUPPORTED);
 assert(M(EV_ABS,ABS_MT_TRACKING_ID,9)==TP_CONTACT);
 assert(M(EV_ABS,ABS_MT_TRACKING_ID,9)==TP_UNSUPPORTED);
 tp_reset(&s);M(EV_ABS,ABS_MT_TRACKING_ID,9);down(&s,&multi);
 M(EV_ABS,ABS_X,30);M(EV_ABS,ABS_Y,40);M(EV_SYN,SYN_REPORT,0);
 M(EV_ABS,ABS_MT_TRACKING_ID,-1);M(EV_KEY,BTN_TOUCH,0);
 M(EV_KEY,BTN_TOOL_FINGER,0);assert(M(EV_SYN,SYN_REPORT,0)==TP_NONE);
 assert(!tp_active(&s));
 /* Contact alone remains active indefinitely without earning motion. */
 tp_reset(&s);down(&s,&plain);
 for(int i=0;i<20;i++)assert(E(EV_SYN,SYN_REPORT,0)==TP_NONE);
 assert(tp_active(&s));
 /* Reset wipes any prior baseline, including after pre-ARM resync. */
 tp_reset(&s);down(&s,&plain);E(EV_ABS,ABS_X,80);
 assert(E(EV_SYN,SYN_REPORT,0)==TP_NONE);
 E(EV_ABS,ABS_Y,90);assert(E(EV_SYN,SYN_REPORT,0)==TP_NONE);
 /* Separately initialized devices do not share contact/baseline state. */
 struct tp_state other;tp_reset(&other);assert(!tp_active(&other));
 assert(tp_active(&s));
 tp_reset(&s);assert(M(EV_ABS,ABS_MT_PRESSURE,2)==TP_UNSUPPORTED);
 multi.slot_max=TP_MAX_SLOTS;
 assert(M(EV_SYN,SYN_REPORT,0)==TP_UNSUPPORTED);
 return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix="ldc-touchpad-") as temporary:
            fixture = pathlib.Path(temporary) / "fixture.c"
            executable = pathlib.Path(temporary) / "fixture"
            fixture.write_text(source)
            subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-I", str(directory), str(fixture), "-o", str(executable)],
                           check=True, capture_output=True)
            subprocess.run([str(executable)], check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
