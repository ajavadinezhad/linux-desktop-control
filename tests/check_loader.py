#!/usr/bin/python3
"""Verify the real bundled client discovers plugin MCP tools, without a model or desktop consent."""
import json,os,pathlib,select,subprocess,tempfile,time,shutil
ROOT=pathlib.Path(__file__).resolve().parents[1]
CODEX=os.environ.get('CODEX_BIN','/usr/lib/chatgpt/resources/codex')
with tempfile.TemporaryDirectory(prefix='desktop-plugin-loader-') as home:
    env=dict(os.environ,CODEX_HOME=home)
    # Materialize paths in a temporary copy, as install.sh does. Never dirty source.
    bundle=pathlib.Path(home)/'bundle'
    shutil.copytree(ROOT,bundle,ignore=shutil.ignore_patterns('.git','__pycache__','recordings','test-evidence'))
    plugin=bundle/'plugins/linux-desktop-control'
    declaration=plugin/'.mcp.json';config=json.loads((plugin/'.mcp.template.json').read_text())
    config['mcpServers']['linux_desktop']['args']=[str(plugin/'desktop.py')]
    config['mcpServers']['linux_desktop']['cwd']=str(plugin)
    declaration.write_text(json.dumps(config))
    for args in [['plugin','marketplace','add',str(bundle),'--json'],
                 ['plugin','add','linux-desktop-control@local-linux-desktop','--json']]:
        subprocess.run([CODEX,*args],env=env,check=True,capture_output=True,text=True,timeout=15)
    p=subprocess.Popen([CODEX,'app-server'],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
    def rpc(i,method,params):
        p.stdin.write(json.dumps({'id':i,'method':method,'params':params})+'\n');p.stdin.flush()
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            if select.select([p.stdout],[],[],.2)[0]:
                line=p.stdout.readline()
                if not line:raise RuntimeError('app-server exited')
                r=json.loads(line)
                if r.get('id')==i:
                    if 'error' in r:raise RuntimeError(r['error'])
                    return r['result']
        raise TimeoutError(method)
    try:
        rpc(1,'initialize',{'clientInfo':{'name':'desktop-plugin-loader-test','version':'1'},'capabilities':{'experimentalApi':True}})
        p.stdin.write('{"method":"initialized","params":{}}\n');p.stdin.flush()
        inventory=rpc(2,'mcpServerStatus/list',{'serverName':'linux_desktop'})
        server=inventory['data'][0]
        expected={'desktop_start','desktop_observe','desktop_action','desktop_status','desktop_close'}
        assert server['toolsError'] is None,server['toolsError']
        assert set(server['tools'])==expected,server['tools']
        assert not server['tools']['desktop_status']['inputSchema']['properties']
        assert 'target_id' in server['tools']['desktop_action']['inputSchema']['properties']
        observe=server['tools']['desktop_observe']['inputSchema']
        assert 'inspect_target' in observe['properties'] and not observe.get('required'),observe
        print(json.dumps({'passed':True,'server':server['name'],'version':server['serverInfo']['version'],'tools':sorted(server['tools'])},indent=2))
    finally:
        p.terminate()
        try:p.wait(timeout=1)
        except subprocess.TimeoutExpired:p.kill();p.wait()
