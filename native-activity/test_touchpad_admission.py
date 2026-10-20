"""Exercise the real opener admission predicate using synthetic capabilities."""
import os
import pathlib
import shlex
import subprocess
import tempfile
import unittest


class TouchpadAdmissionTests(unittest.TestCase):
    def test_classification_capabilities_ranges_and_slot_bounds(self):
        directory = pathlib.Path(__file__).resolve().parent
        source = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <libudev.h>
#include <linux/input.h>
#include <stdarg.h>
#include <string.h>
#include <sys/ioctl.h>
static int variant;
static const char *fake_property(struct udev_device*d,const char*key){
 (void)d;
 if(!strcmp(key,"ID_INPUT_TOUCHPAD"))return "1";
 if(variant==9&&!strcmp(key,"ID_INPUT_TOUCHSCREEN"))return "1";
 if(variant==10&&!strcmp(key,"ID_INPUT_MOUSE"))return "1";
 return NULL;
}
static void bit(void*out,unsigned code){((unsigned char*)out)[code/8]|=1U<<(code%8);}
static int fake_ioctl(int fd,unsigned long request,...){
 (void)fd;va_list ap;va_start(ap,request);void*out=va_arg(ap,void*);va_end(ap);
 if(variant==8)return -1;
 if(request==EVIOCGPROP((INPUT_PROP_MAX+8)/8)){
  memset(out,0,(INPUT_PROP_MAX+8)/8);if(variant!=2)bit(out,INPUT_PROP_POINTER);
  if(variant==1)bit(out,INPUT_PROP_DIRECT);
  return 0;
 }
 if(request==EVIOCGBIT(EV_KEY,(KEY_MAX+8)/8)){
  memset(out,0,(KEY_MAX+8)/8);bit(out,BTN_TOOL_FINGER);if(variant!=3)bit(out,BTN_TOUCH);return 0;
 }
 if(request==EVIOCGBIT(EV_ABS,(ABS_MAX+8)/8)){
  memset(out,0,(ABS_MAX+8)/8);bit(out,ABS_X);if(variant!=4)bit(out,ABS_Y);
  if(variant>=5&&variant<=7){bit(out,ABS_MT_SLOT);bit(out,ABS_MT_TRACKING_ID);bit(out,ABS_MT_POSITION_X);bit(out,ABS_MT_POSITION_Y);}
  if(variant==11){bit(out,ABS_MT_SLOT);bit(out,ABS_MT_TRACKING_ID);bit(out,ABS_MT_POSITION_X);bit(out,ABS_MT_POSITION_Y);}
  return 0;
 }
 struct input_absinfo info={.minimum=0,.maximum=1000};
 if(request==EVIOCGABS(ABS_MT_SLOT))info.maximum=variant==6?16:3;
 else if(request==EVIOCGABS(ABS_MT_TRACKING_ID)){info.maximum=65535;if(variant==11)info.minimum=1;}
 else if(request==EVIOCGABS(ABS_MT_POSITION_X)&&variant==7)info.maximum=2000;
 else if(request!=EVIOCGABS(ABS_X)&&request!=EVIOCGABS(ABS_Y)&&
         request!=EVIOCGABS(ABS_MT_POSITION_X)&&request!=EVIOCGABS(ABS_MT_POSITION_Y))return -1;
 memcpy(out,&info,sizeof info);return 0;
}
#define udev_device_get_property_value fake_property
#define ioctl fake_ioctl
OPENER_SOURCE
int main(void){
 struct tp_limits limits;
 assert(verified_touchpad(-1,(struct udev_device*)1,&limits));assert(!limits.mt);
 for(variant=1;variant<=11;variant++){
  bool ok=verified_touchpad(-1,(struct udev_device*)1,&limits);
  assert(ok==(variant==5));
  if(ok)assert(limits.mt&&limits.slot_max==3&&limits.tracking_max==65535);
 }
 return 0;
}
'''
        source = source.replace("OPENER_SOURCE", (directory / "opener.c").read_text().replace(
            "int main(int argc,char **argv)", "int unused_opener_main(int argc,char **argv)"))
        with tempfile.TemporaryDirectory(prefix="ldc-pad-admission-") as temporary:
            root = pathlib.Path(temporary)
            fixture = root / "fixture.c"
            fixture.write_text(source)
            subprocess.run(shlex.split(os.environ.get("CC", "cc")) +
                           shlex.split(os.environ.get("CFLAGS", "")) +
                           ["-std=c11", "-Wall", "-Wextra", "-Werror", "-I", str(directory),
                            str(fixture), "/usr/lib/x86_64-linux-gnu/libudev.so.1",
                            "/usr/lib/x86_64-linux-gnu/libsystemd.so.0", "-o", str(root / "fixture")],
                           check=True)
            subprocess.run([str(root / "fixture")], check=True, timeout=5)


if __name__ == "__main__":
    unittest.main()
