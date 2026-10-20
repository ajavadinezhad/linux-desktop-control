import sys,json,time,copy,importlib.util
from pathlib import Path
r=Path(__file__).resolve().parents[1];sys.path.insert(0,str(r/'tests'))
from test_control import Tests
from test_monitor_mapping import Bus,state,m

d=Tests().backend();counts={'pointer_reads':0,'mapping_checks':0,'requested_wait_seconds':0}
def reader():counts['pointer_reads']+=1;return d.observed_pointer
def mapping():counts['mapping_checks']+=1
def wait(seconds):counts['requested_wait_seconds']+=seconds;d.check()
d.pointer_reader=reader;d.mapping_guard=mapping;d.wait_interruptibly=wait
path=[[20+i*4,30+i*2] for i in range(40)]
d.action({'type':'drag','path':path})
value=state();modes=value[1][0][1]
for i in range(150):
 mode=copy.deepcopy(modes[0]);mode[0]='inactive-'+str(i);mode[6]={};modes.append(mode)
bus=Bus(value);guard=m.MonitorMapping(bus,{'position':(240,0),'logical_size':(1720,720)})
t=time.perf_counter()
for _ in range(250):guard.check()
print(json.dumps({'40_point_drag':counts,'250_mapping_checks_seconds':round(time.perf_counter()-t,4),'read_only_dbus_calls':len(bus.calls)-3}))
