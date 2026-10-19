"""Fake DisplayConfig only; no session bus or GUI operations."""
import copy
import importlib.util
from pathlib import Path
import unittest
import sys
from types import SimpleNamespace
from unittest import mock

SOURCE=Path(__file__).resolve().parents[1]/'plugins/linux-desktop-control/monitor_mapping.py'
spec=importlib.util.spec_from_file_location('mapping_test',SOURCE)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def state(scale=2.,origin=(240,0),size=(3440,1440)):
    identity=('DP-fixture','vendor','product','private-serial')
    return [17,[[identity,[['active',size[0],size[1],60.,scale,[1.,1.25,1.5,2.],{'is-current':True}]],{}]],
            [[origin[0],origin[1],scale,0,True,[identity],{}]],{'layout-mode':1}]

class Bus:
    def __init__(self,value=None):self.value=value or state();self.owner=':1.20';self.calls=[];self.fail=False
    def mapping_call(self,destination,path,interface,method,parameters,timeout):
        self.calls.append((destination,method,timeout))
        if self.fail:raise RuntimeError('untrusted detail must not escape')
        if method=='GetNameOwner':return (self.owner,)
        return copy.deepcopy(self.value)

class MappingTests(unittest.TestCase):
    def bind(self,bus=None,props=None):
        return m.MonitorMapping(bus or Bus(),props or {'position':(240,0),'logical_size':(1720,720)})

    def test_origin_scale_and_fractional_geometry(self):
        for scale,origin,size,logical in ((2.,(240,0),(3440,1440),(1720,720)),(1.,(0,0),(1920,1080),(1920,1080)),(1.25,(-1536,-120),(1920,1080),(1536,864)),(1.5,(240,0),(1920,1080),(1280,720))):
            with self.subTest(scale=scale):
                bus=Bus(state(scale,origin,size));guard=self.bind(bus,{'position':origin,'size':logical})
                self.assertTrue(guard.check())
                self.assertEqual(guard.status()['logical_rect'],list(origin+logical));self.assertEqual(guard.status()['scale'],scale)
                self.assertTrue(all(call[2]==3000 for call in bus.calls))
                self.assertNotIn('private-serial',str(guard.status()))
                self.assertNotIn('DP-fixture',str(guard.status()))
                self.assertTrue(all(destination==':1.20' for destination,method,_ in bus.calls if method=='GetCurrentState'))

    def test_absent_layout_mode_is_documented_logical_default(self):
        bus=Bus();bus.value[3]={};self.assertTrue(self.bind(bus).check())

    def test_missing_current_mode_rotated_mirror_ambiguous_and_wrong_geometry_refused(self):
        mutations=[lambda s:s[1][0][1][0][6].clear(),lambda s:s[2][0].__setitem__(3,1),lambda s:s[2][0][5].append(s[1][0][0]),lambda s:s[2].append(copy.deepcopy(s[2][0])),lambda s:s[3].__setitem__('layout-mode',2),lambda s:s[2][0].__setitem__(2,1.25)]
        for mutate in mutations:
            bus=Bus();mutate(bus.value)
            with self.subTest(state=bus.value),self.assertRaises(m.MappingError):self.bind(bus)
        for props in ({'logical_size':(1720,720)},{'position':(240,0)},{'position':(240,0),'size':(3440,1440)}):
            with self.assertRaises(m.MappingError):self.bind(props=props)

    def test_serial_owner_and_any_layout_change_latch_failure(self):
        for change in ('serial','owner','layout'):
            bus=Bus();guard=self.bind(bus)
            if change=='serial':bus.value[0]+=1
            elif change=='owner':bus.owner=':1.21'
            else:bus.value[1][0][2]['extra']='changed'
            with self.assertRaises(m.MappingError):guard.check()
            bus.owner=':1.20';bus.value=state()
            with self.assertRaises(m.MappingError):guard.check()
            self.assertFalse(guard.status()['supported'])

    def test_owner_change_during_read_refused(self):
        bus=Bus();original=bus.mapping_call
        def call(*args):
            result=original(*args)
            if args[3]=='GetCurrentState':bus.owner=':1.99'
            return result
        bus.mapping_call=call
        with self.assertRaises(m.MappingError):self.bind(bus)

    def test_bus_failure_sanitized_and_latched(self):
        bus=Bus();guard=self.bind(bus);bus.fail=True
        with self.assertRaisesRegex(m.MappingError,'input refused') as error:guard.check()
        self.assertNotIn('untrusted',str(error.exception));self.assertFalse(guard.status()['supported'])

    def test_malformed_bounded_types_refused(self):
        for value in (None,[],[True,[],[],{}],[1,[],[],{}]):
            with self.assertRaises(m.MappingError):m.validate_state(value,{})
        for key,value in (('position',(True,0)),('logical_size',(float('nan'),720))):
            props={'position':(240,0),'logical_size':(1720,720)};props[key]=value
            with self.assertRaises(m.MappingError):self.bind(props=props)
        bus=Bus();bus.value[1][0][1][0][6]['is-current']=1
        with self.assertRaises(m.MappingError):self.bind(bus)

    def test_logical_size_wins_over_buffer_pixel_size(self):
        guard=self.bind(props={'position':(240,0),'logical_size':(1720,720),'size':(3440,1440)})
        self.assertEqual(guard.status()['logical_rect'],[240,0,1720,720])


    def test_gio_adapter_fixed_read_only_calls_no_activation_and_deadlines(self):
        class ReadOnlyBus:
            def __init__(self):self.calls=[]
            def call_sync(self,*args):
                self.calls.append(args)
                return (':1.20',) if args[3]=='GetNameOwner' else state()
        bus=ReadOnlyBus()
        repository=SimpleNamespace(Gio=SimpleNamespace(DBusCallFlags=SimpleNamespace(NO_AUTO_START=123)),GLib=SimpleNamespace(Variant=lambda signature,value:(signature,value)))
        with mock.patch.dict(sys.modules,{'gi.repository':repository}):
            guard=self.bind(bus);guard.check()
        self.assertEqual(len(bus.calls),6)
        self.assertEqual({call[3] for call in bus.calls},{'GetNameOwner','GetCurrentState'})
        self.assertTrue(all(call[6]==123 and call[7]==3000 for call in bus.calls))
        self.assertTrue(all(call[4]==('(s)',(m.NAME,)) for call in bus.calls if call[3]=='GetNameOwner'))

    def test_overlapping_different_logical_rectangles_refused(self):
        bus=Bus();identity=('DP-second','','','')
        bus.value[1].append([identity,[['other',1920,1080,60.,1.,[1.],{'is-current':True}]],{}])
        bus.value[2].append([240,0,1.,0,False,[identity],{}])
        with self.assertRaises(m.MappingError):self.bind(bus)

if __name__=='__main__':unittest.main()
