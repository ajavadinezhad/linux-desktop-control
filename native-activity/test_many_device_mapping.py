"""Exercise the exact opener remapping block with tagged anonymous pipes.

No privileged entry point, device, session bus or desktop is opened. This is
descriptor-layout evidence, not physical-event coverage or evdev semantics.
"""
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
COMPILER = shutil.which(os.environ.get('CC', 'cc')) or shutil.which('gcc') or shutil.which('clang')


@unittest.skipUnless(COMPILER, 'C compiler unavailable; remapping not build-validated')
class ManyDeviceMappingTests(unittest.TestCase):
    def test_actual_opener_block_preserves_all_stream_and_snapshot_identities(self):
        opener = (ROOT / 'opener.c').read_text()
        start = opener.index('    int source[2*MAX_DEVICES+3];')
        stop = opener.index('    phase=9;', start)
        mapping = opener[start:stop]  # Execute production statements, not a copied algorithm.
        source = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>
#define MAX_DEVICES 64
static int tagged(unsigned char kind,unsigned char index,int relocate) {
    int pair[2];assert(pipe2(pair,O_NONBLOCK|O_CLOEXEC)==0);
    unsigned char tag[2]={kind,index};assert(write(pair[1],tag,2)==2);close(pair[1]);
    if(relocate) {
        int fd=fcntl(pair[0],F_DUPFD_CLOEXEC,500+index*3);
        assert(fd>=500+index*3);close(pair[0]);return fd;
    }
    return pair[0];
}
int main(int argc,char **argv) {
    assert(argc==2);int count=atoi(argv[1]);assert(count>=1&&count<=MAX_DEVICES);
    int control=tagged('C',0,1),topology=tagged('T',0,0),parent=tagged('P',0,1);
    int devices[MAX_DEVICES],snapshots[MAX_DEVICES];
    struct stat identities[2*MAX_DEVICES+3];
    assert(fstat(control,&identities[0])==0);
    for(int i=0;i<count;i++) {
        /* Interleave originals and move alternating descriptors above the
         * staging floor. Every pipe has a distinct kernel object/tag. */
        devices[i]=tagged('S',(unsigned char)i,i%2);
        snapshots[i]=tagged('N',(unsigned char)i,!(i%2));
        assert(fstat(devices[i],&identities[i+1])==0);
        assert(fstat(snapshots[i],&identities[count+3+i])==0);
    }
    assert(fstat(topology,&identities[count+1])==0);
    assert(fstat(parent,&identities[count+2])==0);
/* PRODUCTION_MAPPING */
    for(int i=0;i<2*count+3;i++) {
        struct stat actual;unsigned char tag[2],expected;
        unsigned index=0;
        if(i==0)expected='C';
        else if(i<=count){expected='S';index=(unsigned)(i-1);}
        else if(i==count+1)expected='T';
        else if(i==count+2)expected='P';
        else {expected='N';index=(unsigned)(i-count-3);}
        if(fstat(3+i,&actual))return 10;
        if(actual.st_dev!=identities[i].st_dev||actual.st_ino!=identities[i].st_ino)return 11;
        if(read(3+i,tag,2)!=2||tag[0]!=expected||tag[1]!=index)return 12;
        int flags=fcntl(3+i,F_GETFL);
        if(flags<0||(flags&O_ACCMODE)!=O_RDONLY||!(flags&O_NONBLOCK))return 13;
    }
    for(int fd=2*count+6;fd<1024;fd++) {
        if(fcntl(fd,F_GETFD)!=-1||errno!=EBADF)return 14;
    }
    return 0;
fault:
    return 90;
}
'''.replace('/* PRODUCTION_MAPPING */', mapping)
        with tempfile.TemporaryDirectory(prefix='many-device-layout-') as directory:
            path = pathlib.Path(directory)
            (path / 'fixture.c').write_text(source)
            built = subprocess.run([COMPILER, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                                    str(path / 'fixture.c'), '-o', str(path / 'fixture')],
                                   capture_output=True, timeout=20)
            self.assertEqual(built.returncode, 0, built.stderr.decode(errors='replace'))
            for count in (1, 20, 21, 32, 64):
                with self.subTest(device_count=count):
                    result = subprocess.run([str(path / 'fixture'), str(count)], capture_output=True, timeout=3)
                    self.assertEqual(result.returncode, 0,
                                     f'{count} devices: layout stage {result.returncode}; '
                                     + result.stderr.decode(errors='replace'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
