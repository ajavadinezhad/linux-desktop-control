"""Private parser branch reasons, fixed terminal vocabulary, no input payload logging."""
import unittest
import test_multi_contact_pause as multi

PREP=multi.PREP+r'''
static struct tp_limits limits={0,1000,0,1000,true,0,5,65535};
static void rejected(struct tp_state *s,enum tp_reject_reason reason,unsigned type,unsigned code,int value,int maximum){
 struct input_event e={.type=type,.code=code,.value=value};
 assert(tp_event_contacts(s,&e,&limits,maximum)==TP_UNSUPPORTED);assert(s->reject_reason==reason);
 /* The parser's first private rejection survives any subsequent invalid data. */
 e=(struct input_event){.type=EV_REL,.code=REL_WHEEL,.value=99};
 assert(tp_event_contacts(s,&e,&limits,maximum)==TP_UNSUPPORTED);assert(s->reject_reason==reason);
}
'''
def run(body,prefix=None):
 multi.fixture.fixture.run('int main(void){(void)multi_setup;(void)contacts;(void)click_setup;(void)one;(void)two;(void)lift;(void)rejected;'+body+'return 0;}',(prefix or multi.PREFIX)+PREP)

class TouchpadRejectionTests(unittest.TestCase):
 def test_every_fixed_parser_reason_is_reproducible(self):
  scenarios=[
   ('limits.x_max=0;', 'TP_REJECT_CONFIGURATION','EV_SYN,SYN_REPORT,0,4'),
   ('', 'TP_REJECT_FRAME','EV_SYN,SYN_DROPPED,0,4'),
   ('s.touch=s.finger=s.quad_finger=true;', 'TP_REJECT_TOOLS','EV_SYN,SYN_REPORT,0,4'),
   ('s.touch=true;', 'TP_REJECT_STATE','EV_SYN,SYN_REPORT,0,4'),
   ('s.touch=s.quad_finger=true;', 'TP_REJECT_LIMIT','EV_SYN,SYN_REPORT,0,2'),
   ('s.touch=s.quad_finger=true;s.tracking[0]=10;', 'TP_REJECT_COUNT','EV_SYN,SYN_REPORT,0,4'),
   ('s.coordinate_frame=true;', 'TP_REJECT_COORDINATE_CONTACT','EV_SYN,SYN_REPORT,0,4'),
   ('', 'TP_REJECT_EVENT_TYPE','EV_REL,REL_WHEEL,1,4'),
   ('', 'TP_REJECT_KEY','EV_KEY,BTN_TOOL_QUINTTAP,1,4'),
   ('', 'TP_REJECT_AXIS_TYPE','EV_ABS,ABS_MT_ORIENTATION,1,4'),
   ('', 'TP_REJECT_VALUE','EV_KEY,BTN_TOUCH,2,4'),
   ('', 'TP_REJECT_VALUE','EV_ABS,ABS_PRESSURE,-1,4'),
   ('s.tracking[0]=10;', 'TP_REJECT_VALUE','EV_ABS,ABS_MT_PRESSURE,-1,4'),
   ('s.touch=true;', 'TP_REJECT_DUPLICATE_STATE','EV_KEY,BTN_TOUCH,1,4'),
   ('', 'TP_REJECT_AXIS','EV_ABS,ABS_X,1001,4'),
   ('s.tracking[0]=10;', 'TP_REJECT_AXIS','EV_ABS,ABS_MT_POSITION_X,-1,4'),
   ('', 'TP_REJECT_SLOT','EV_ABS,ABS_MT_SLOT,6,4'),
   ('s.slot_selected=true;s.slot=6;', 'TP_REJECT_SLOT','EV_ABS,ABS_MT_TRACKING_ID,10,4'),
   ('', 'TP_REJECT_TRACKING','EV_ABS,ABS_MT_TRACKING_ID,-2,4'),
   ('', 'TP_REJECT_CONTACT_SLOT','EV_ABS,ABS_MT_POSITION_X,50,4'),
   ('', 'TP_REJECT_CONTACT_SLOT','EV_ABS,ABS_MT_WIDTH_MAJOR,50,4'),
   ('s.tracking[0]=10;', 'TP_REJECT_DUPLICATE_CONTACT','EV_ABS,ABS_MT_TRACKING_ID,11,4'),
   ('s.tracking[1]=10;', 'TP_REJECT_DUPLICATE_CONTACT','EV_ABS,ABS_MT_TRACKING_ID,10,4'),
   ('', 'TP_REJECT_RELEASE','EV_ABS,ABS_MT_TRACKING_ID,-1,4'),
   ('for(int i=1;i<=4;i++)s.tracking[i]=i;', 'TP_REJECT_LIMIT','EV_ABS,ABS_MT_TRACKING_ID,10,4'),
  ]
  for setup,reason,event in scenarios:
   with self.subTest(reason=reason,event=event):run('struct tp_state s;tp_reset(&s);'+setup+'rejected(&s,'+reason+','+event+');')
 def test_terminal_broker_report_preserves_first_reason_after_all_fds_closed(self):
  prefix=multi.PREFIX.replace('if(!strncmp(reply,"CAL_DIAG_",9))assert(closed_mask==15);','if(strstr(reply,"TP_REJECT_"))assert(closed_mask==15);if(!strncmp(reply,"CAL_DIAG_",9))assert(closed_mask==15);')
  run(r'''multi_setup();touchpad_limits[0]=(struct tp_limits){0,1000,0,1000,true,0,3,65535};
 assert(event(EV_KEY,BTN_TOUCH,1)==0);assert(event(EV_KEY,BTN_TOOL_QUADTAP,1)==0);
 assert(!strstr(reply,"TP_REJECT_"));assert(!closed_mask);
 assert(event(EV_SYN,SYN_REPORT,0)==-1);assert(collector_phase==50);
 assert(touchpad_terminal_reject==TP_REJECT_COUNT);assert(!strstr(reply,"TP_REJECT_"));
 assert(event(EV_ABS,ABS_X,1001)==-1);assert(touchpad_terminal_reject==TP_REJECT_COUNT);
 assert(report("FAULT\n")==0);assert(!strcmp(reply,"FAULT\nOBS_TPAD_0101\nTP_REJECT_contact-count\n"));''',prefix)
 def test_other_terminal_reports_keep_legacy_shape(self):
  run('multi_setup();assert(report("FAULT\\n")==0);assert(!strstr(reply,"TP_REJECT_"));')
 def test_reason_vocabulary_is_fixed_and_bounded(self):
  run(r'''const char *expected[]={"none","invalid-configuration","frame-invalid","tool-cardinality","contact-state","contact-limit","contact-count","coordinate-without-contact","unsupported-key","unsupported-event-type","unsupported-axis","invalid-value","duplicate-state","axis-range","slot-range","tracking-range","contact-without-slot","duplicate-contact","contact-release"};
 for(unsigned i=0;i<sizeof expected/sizeof expected[0];i++){assert(!strcmp(tp_reject_name((enum tp_reject_reason)i),expected[i]));assert(strlen(expected[i])<32);}
 assert(!strcmp(tp_reject_name((enum tp_reject_reason)999),"invalid-configuration"));''')
