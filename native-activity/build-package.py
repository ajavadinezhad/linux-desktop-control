#!/usr/bin/python3
"""Build an inspectable optional helper package. Never install or authorize it."""
import argparse,hashlib,os,pathlib,shutil,subprocess,tempfile
p=argparse.ArgumentParser();p.add_argument('--cc',default='cc');p.add_argument('--include');p.add_argument('--output',required=True);args=p.parse_args()
root=pathlib.Path(__file__).resolve().parent
output=pathlib.Path(args.output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='ldc-helper-build-') as work:
 stage=pathlib.Path(work)/'package';binary=stage/'usr/libexec/codex-desktop-activity';binary.parent.mkdir(parents=True)
 command=[args.cc,'-std=c11','-Wall','-Wextra','-Werror','-O2','-fstack-protector-strong','-D_FORTIFY_SOURCE=2','-fPIE','-pie','-Wl,-z,relro,-z,now']
 if args.include:command+=['-I'+str(pathlib.Path(args.include).resolve())]
 command += [str(root/'opener.c'),'/usr/lib/x86_64-linux-gnu/libudev.so.1','/usr/lib/x86_64-linux-gnu/libsystemd.so.0','-o',str(binary)]
 subprocess.run(command,check=True);binary.chmod(0o755)
 policy=stage/'usr/share/polkit-1/actions/org.codex.desktop-activity.policy';policy.parent.mkdir(parents=True);shutil.copyfile(root/policy.name,policy);policy.chmod(0o644)
 control=stage/'DEBIAN/control';control.parent.mkdir();control.write_text('Package: codex-desktop-activity\nVersion: 0.8.14\nArchitecture: amd64\nMaintainer: Independent Linux Desktop Control project\nDepends: libc6, libudev1, libsystemd0, pkexec\nDescription: Optional temporary local device-activity monitor\n Receives input internally and exports only coarse takeover/fault signals.\n No service, setuid binary, input group or persistent device ACL.\n')
 control.chmod(0o644)
 for directory,_,_ in os.walk(stage):pathlib.Path(directory).chmod(0o755)
 subprocess.run(['dpkg-deb','--root-owner-group','--build',str(stage),str(output)],check=True)
print('SHA256',hashlib.sha256(output.read_bytes()).hexdigest())
