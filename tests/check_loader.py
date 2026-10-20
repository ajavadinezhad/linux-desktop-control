#!/usr/bin/python3
"""Verify the real bundled client discovers plugin MCP tools, without a model or desktop consent."""
import json,os,pathlib,select,subprocess,tempfile,time,shutil
ROOT=pathlib.Path(__file__).resolve().parents[1]
CODEX=os.environ.get('CODEX_BIN','/usr/lib/chatgpt/resources/codex')
with tempfile.TemporaryDirectory(prefix='desktop-plugin-loader-') as home:
    env=dict(os.environ,CODEX_HOME=home)
    # Materialize paths in a temporary copy, as install.sh does. Never dirty source.
    bundle=pathlib.Path(home)/'bundle'
    shutil.copytree(ROOT,bundle,ignore=shutil.ignore_patterns('.git','__pycache__','recordings','test-evidence','work','extension-backups'))
    plugin=bundle/'plugins/linux-desktop-control'
    subprocess.run(['/usr/bin/python3',str(bundle/'configure-runtime.py'),str(bundle)],
                   env=env,check=True,capture_output=True,text=True,timeout=5)
    version=json.loads((plugin/'.codex-plugin/plugin.json').read_text())['version']
    runtime=pathlib.Path(home)/'plugins/cache/local-linux-desktop/linux-desktop-control'/version
    expected_launch={'args':[str(runtime/'desktop.py')],'cwd':str(runtime)}
    declaration=plugin/'.mcp.json'
    launch=json.loads(declaration.read_text())['mcpServers']['linux_desktop']
    assert all(launch[key]==value for key,value in expected_launch.items()),launch
    assert not launch['args'][0].startswith(str(bundle)),launch
    for args in [['plugin','marketplace','add',str(bundle),'--json'],
                 ['plugin','add','linux-desktop-control@local-linux-desktop','--json']]:
        subprocess.run([CODEX,*args],env=env,check=True,capture_output=True,text=True,timeout=15)
    installed=json.loads((runtime/'.mcp.json').read_text())['mcpServers']['linux_desktop']
    assert all(installed[key]==value for key,value in expected_launch.items()),installed
    assert (runtime/'desktop.py').is_file(),runtime
    assert json.loads((runtime/'.codex-plugin/plugin.json').read_text())['version']==version
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
        expected={'desktop_start','desktop_observe','desktop_action','desktop_status','desktop_close','desktop_pause','desktop_resume'}
        assert server['serverInfo']['version']=='0.8.31',server['serverInfo']
        assert server['toolsError'] is None,server['toolsError']
        assert set(server['tools'])==expected,server['tools']
        assert not server['tools']['desktop_status']['inputSchema']['properties']
        assert 'target_id' in server['tools']['desktop_action']['inputSchema']['properties']
        assert 'window_observation_id' in server['tools']['desktop_action']['inputSchema']['required']
        assert 'focus_transition' in server['tools']['desktop_action']['inputSchema']['properties']
        assert server['tools']['desktop_start']['inputSchema']['properties']['cursor_glow']['type']=='boolean'
        physical=server['tools']['desktop_start']['inputSchema']['properties']['physical_takeover']
        assert physical['type']=='boolean' and physical['default'] is False,physical
        assert 'administrator' in physical['description'] and 'raw' in physical['description'],physical
        start_schema=server['tools']['desktop_start']['inputSchema']['properties']
        assert start_schema['interruption_policy']['enum']==['close','retain-sharing']
        assert start_schema['interruption_policy']['default']=='close'
        assert start_schema['pointer_motion_return']['type']=='boolean' and start_schema['pointer_motion_return']['default'] is False
        assert server['tools']['desktop_pause']['inputSchema']['properties']=={}
        assert server['tools']['desktop_resume']['inputSchema']['required']==['pause_id']
        assert server['tools']['desktop_resume']['inputSchema']['properties']['pause_id']['minLength']==32
        observe=server['tools']['desktop_observe']['inputSchema']
        assert 'inspect_target' in observe['properties'] and not observe.get('required'),observe
        print(json.dumps({'passed':True,'server':server['name'],'version':server['serverInfo']['version'],'tools':sorted(server['tools'])},indent=2))
    finally:
        p.terminate()
        try:p.wait(timeout=1)
        except subprocess.TimeoutExpired:p.kill();p.wait()
