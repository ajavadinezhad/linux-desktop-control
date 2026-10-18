"""Compile/fake-bus lifecycle tests. Never connects to a real system bus."""
import os,pathlib,shutil,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parent
BUNDLED=pathlib.Path('/tmp/ldc-build/root')
CC=os.environ.get('CC') or shutil.which('cc') or str(BUNDLED/'usr/bin/x86_64-linux-gnu-gcc-15')
HEADERS=BUNDLED/'usr/include'
FAKE=r'''
#define _GNU_SOURCE
#define sd_bus_open_system fake_open
#define sd_bus_set_method_call_timeout fake_timeout
#define sd_bus_call_method fake_method
#define sd_bus_message_read fake_read
#define sd_bus_message_enter_container fake_enter
#define sd_bus_message_exit_container fake_exit
#define sd_bus_message_skip fake_skip
#define sd_bus_message_at_end fake_at_end
#define sd_bus_match_signal fake_match
#define sd_bus_get_property_trivial fake_property
#define sd_bus_message_unref fake_message_unref
#define sd_bus_slot_unref fake_slot_unref
#define sd_bus_close fake_close
#define sd_bus_unref fake_unref
#define sd_bus_is_open fake_is_open
#define sd_bus_process fake_process
#define sd_bus_get_fd fake_fd
#define getuid fake_uid
#define geteuid fake_euid
#include "session_watch.h"
#include <assert.h>
#include <stdarg.h>
static int opens, closes, kind, active=1, locked, remote, processing, error_property, register_fault;
static int owner_slot, properties_slot, removed_slot, uid=65534, broken, process_calls;
static sd_bus_message_handler_t prop_cb, removed_cb, owner_cb;
static int prop_container, prop_entry_done, prop_invalid_done, prop_malformed;
static const char *prop_interface=SW_SESSION, *prop_changed="Active", *prop_invalidated;
static void invoke_properties(void) {
 prop_container=prop_entry_done=prop_invalid_done=0;
 sw_properties((sd_bus_message *)2,NULL,NULL);
}
static const char *signal_id="c7", *signal_path="/org/freedesktop/login1/session/c7";
uid_t fake_uid(void){return uid;}
uid_t fake_euid(void){return uid;}
int fake_open(sd_bus **out){opens++;*out=(sd_bus *)1;return 0;}
int fake_timeout(sd_bus *b,uint64_t timeout){(void)b;assert(timeout==100000);return 0;}
int fake_method(sd_bus *b,const char *dest,const char *path,const char *interface,const char *method,sd_bus_error *error,sd_bus_message **reply,const char *types,...){
 (void)b;(void)path;(void)interface;(void)error;assert(!strcmp(types,"s"));
 if(!strcmp(method,"GetNameOwner")){assert(!strcmp(dest,"org.freedesktop.DBus"));kind=1;}
 else {assert(!strcmp(dest,":1.42"));assert(!strcmp(method,"GetSession"));kind=2;}
 *reply=(sd_bus_message *)1;return 0;
}
int fake_read(sd_bus_message *m,const char *types,...){
 va_list args;va_start(args,types);
 if(m==(sd_bus_message *)2){
  assert(!strcmp(types,"s"));const char **v=va_arg(args,const char **);
  if(prop_container==0)*v=prop_interface;
  else if(prop_container==2)*v=prop_changed;
  else if(prop_container==3 && prop_invalidated && !prop_invalid_done){*v=prop_invalidated;prop_invalid_done=1;}
  else {va_end(args);return 0;}
  va_end(args);return 1;
 }
 if(!strcmp(types,"s") || !strcmp(types,"o")){const char **v=va_arg(args,const char **);*v=kind==1?":1.42":signal_path;}
 else if(!strcmp(types,"so")){*va_arg(args,const char **)=signal_id;*va_arg(args,const char **)=signal_path;}
 else if(!strcmp(types,"sss")){*va_arg(args,const char **)=SW_LOGIND;*va_arg(args,const char **)=":1.42";*va_arg(args,const char **)="";}
 else assert(0);
 va_end(args);return 1;
}
int fake_enter(sd_bus_message *m,char type,const char *contents){
 assert(m==(sd_bus_message *)2);
 if(type=='a' && !strcmp(contents,"{sv}")){prop_container=1;return 1;}
 if(type=='a' && !strcmp(contents,"s")){prop_container=3;return 1;}
 assert(type=='e' && !strcmp(contents,"sv"));
 if(prop_changed && !prop_entry_done){prop_container=2;return 1;}
 return 0;
}
int fake_exit(sd_bus_message *m){
 assert(m==(sd_bus_message *)2);
 if(prop_container==2){prop_container=1;prop_entry_done=1;}
 else prop_container=0;
 return 1;
}
int fake_skip(sd_bus_message *m,const char *types){assert(m==(sd_bus_message *)2);assert(!strcmp(types,"v"));return prop_malformed==2?-1:1;}
int fake_at_end(sd_bus_message *m,int complete){assert(m==(sd_bus_message *)2);assert(complete==1);return !prop_malformed;}
int fake_match(sd_bus *b,sd_bus_slot **slot,const char *sender,const char *path,const char *interface,const char *member,sd_bus_message_handler_t cb,void *userdata){
 (void)b;(void)interface;(void)userdata;
 if(!strcmp(member,"NameOwnerChanged")){assert(!strcmp(sender,"org.freedesktop.DBus"));owner_slot++;owner_cb=cb;}
 else {assert(!strcmp(sender,":1.42"));
  if(!strcmp(member,"PropertiesChanged")){assert(!strcmp(path,signal_path));properties_slot++;prop_cb=cb;}
  else {assert(!strcmp(member,"SessionRemoved"));assert(!strcmp(path,SW_MANAGER));removed_slot++;removed_cb=cb;}}
 *slot=(sd_bus_slot *)1;
 if(register_fault)sw_properties(NULL,NULL,NULL);
 return 0;
}
int fake_property(sd_bus *b,const char *dest,const char *path,const char *interface,const char *member,sd_bus_error *error,char type,void *out){
 (void)b;(void)error;assert(!strcmp(dest,":1.42"));assert(!strcmp(path,signal_path));assert(!strcmp(interface,SW_SESSION));assert(type=='b');
 if(error_property)return -1;
 if(!strcmp(member,"Active"))*(int *)out=active;
 else if(!strcmp(member,"LockedHint"))*(int *)out=locked;
 else {assert(!strcmp(member,"Remote"));*(int *)out=remote;}
 return 0;
}
sd_bus_message *fake_message_unref(sd_bus_message *m){(void)m;return NULL;}
sd_bus_slot *fake_slot_unref(sd_bus_slot *s){(void)s;return NULL;}
void fake_close(sd_bus *b){(void)b;closes++;}
sd_bus *fake_unref(sd_bus *b){(void)b;return NULL;}
int fake_is_open(sd_bus *b){(void)b;return !broken;}
int fake_fd(sd_bus *b){(void)b;return 9;}
int fake_process(sd_bus *b,sd_bus_message **m){
 (void)b;(void)m;process_calls++;
 if(processing==1){processing=0;assert(prop_cb);invoke_properties();return 1;}
 if(processing==2){processing=0;removed_cb((sd_bus_message *)1,NULL,NULL);return 1;}
 if(processing==3){processing=0;owner_cb((sd_bus_message *)1,NULL,NULL);return 1;}
 if(processing==4)return -1;
 if(processing==5)return 1;
 return 0;
}
int main(void){
 uid=0;assert(!session_watch_open("c7"));assert(opens==0);uid=65534;
 assert(!session_watch_open("bad/session"));assert(opens==0);
 assert(session_watch_open("c7"));assert(session_watch_fd()==9);assert(session_watch_ok());
 assert(owner_slot==1 && properties_slot==1 && removed_slot==1);
 processing=1;assert(!session_watch_ok());assert(!session_watch_ok());assert(session_watch_fd()==-1);session_watch_close();
 assert(session_watch_open("c7"));processing=2;assert(!session_watch_ok());session_watch_close();
 assert(session_watch_open("c7"));processing=3;assert(!session_watch_ok());session_watch_close();
 assert(session_watch_open("c7"));processing=4;assert(!session_watch_ok());session_watch_close();processing=0;
 assert(session_watch_open("c7"));processing=5;int before=process_calls;assert(!session_watch_ok());assert(process_calls-before==64);session_watch_close();processing=0;
 locked=1;assert(!session_watch_open("c7"));locked=0;
 remote=1;assert(!session_watch_open("c7"));remote=0;
 active=0;assert(!session_watch_open("c7"));active=1;
 error_property=1;assert(!session_watch_open("c7"));error_property=0;
 register_fault=1;assert(!session_watch_open("c7"));register_fault=0;
 assert(session_watch_open("c7"));broken=1;assert(!session_watch_ok());session_watch_close();broken=0;
 const char *relevant[]={"Active","LockedHint","Remote","Type","Seat","State"};
 for(unsigned i=0;i<sizeof relevant/sizeof relevant[0];i++){
  assert(session_watch_open("c7"));prop_changed=relevant[i];invoke_properties();assert(!session_watch_ok());session_watch_close();
  assert(session_watch_open("c7"));prop_changed=NULL;prop_invalidated=relevant[i];invoke_properties();assert(!session_watch_ok());session_watch_close();prop_invalidated=NULL;
 }
 const char *irrelevant[]={"IdleHint","IdleSinceHint","IdleSinceHintMonotonic","Timestamp"};
 for(unsigned i=0;i<sizeof irrelevant/sizeof irrelevant[0];i++){
  assert(session_watch_open("c7"));prop_changed=irrelevant[i];invoke_properties();assert(session_watch_ok());
  prop_changed=NULL;prop_invalidated=irrelevant[i];invoke_properties();assert(session_watch_ok());session_watch_close();prop_invalidated=NULL;
 }
 assert(session_watch_open("c7"));prop_changed="Active";prop_interface="org.example.Other";invoke_properties();assert(session_watch_ok());session_watch_close();prop_interface=SW_SESSION;
 for(prop_malformed=1;prop_malformed<=2;prop_malformed++){
  assert(session_watch_open("c7"));prop_changed="IdleHint";invoke_properties();assert(!session_watch_ok());session_watch_close();
 }
 prop_malformed=0;
 assert(closes==opens);assert(!session_watch_state.bus);assert(!session_watch_state.properties);
 return 0;
}
'''
class SessionWatchTests(unittest.TestCase):
    def compile(self,source,run):
        with tempfile.TemporaryDirectory(prefix='session-watch-fake-') as directory:
            d=pathlib.Path(directory);c=d/'test.c';c.write_text(source)
            cmd=[CC,'-std=c11','-Wall','-Wextra','-Werror','-I',str(ROOT)]
            if HEADERS.exists():cmd+=['-I',str(HEADERS)]
            cmd += [str(c),'-o',str(d/'test')] if run else ['-fsyntax-only',str(c)]
            built=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
            self.assertEqual(built.returncode,0,built.stderr)
            if run:
                result=subprocess.run([str(d/'test')],capture_output=True,text=True,timeout=3)
                self.assertEqual(result.returncode,0,result.stderr)
    def test_real_header_types_compile_without_bus_connection(self):
        self.compile('#include "session_watch.h"\nint main(void){return 0;}\n',False)
    def test_fake_bus_safe_initial_state_signals_latches_and_cleanup(self):
        self.compile(FAKE,True)
if __name__=='__main__':unittest.main()
