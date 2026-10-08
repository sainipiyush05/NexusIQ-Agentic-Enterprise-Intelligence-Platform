"""Manage only the project-owned development cluster; never system services."""
import getpass
import json
import shutil
import subprocess
from .config import ROOT

RUNTIME=ROOT/'.runtime/postgres'
CLUSTER=RUNTIME/'cluster'
SOCKET=RUNTIME/'socket'
PORT=55432


def run(args):
    result=subprocess.run(args,capture_output=True,text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result


def db_config():
    path=RUNTIME/'connections.json'
    if not path.exists():
        raise RuntimeError('Run db-start first to create the isolated local cluster')
    return json.loads(path.read_text())


def start():
    for binary in ('initdb','pg_ctl'):
        if not shutil.which(binary):
            raise RuntimeError('PostgreSQL binaries unavailable; install PostgreSQL with pgvector or configure an external development database')
    RUNTIME.mkdir(parents=True,exist_ok=True)
    SOCKET.mkdir(exist_ok=True,mode=0o700)
    SOCKET.chmod(0o700)
    if not (CLUSTER/'PG_VERSION').exists():
        run(['initdb','-D',str(CLUSTER),'-U','nexusiq_owner','--auth-local=peer','--auth-host=reject','--encoding=UTF8','--locale=C'])
        (CLUSTER/'pg_hba.conf').write_text('local all all peer map=nexusiq_local\n')
        user=getpass.getuser()
        (CLUSTER/'pg_ident.conf').write_text(f'nexusiq_local {user} nexusiq_owner\nnexusiq_local {user} nexusiq_project_reader\n')
        with (CLUSTER/'postgresql.conf').open('a') as f:
            f.write(f"\nlisten_addresses = ''\nport = {PORT}\nunix_socket_directories = '{SOCKET}'\nunix_socket_permissions = 0700\n")
    config=dict(owner=dict(host=str(SOCKET),port=PORT,dbname='postgres',user='nexusiq_owner',connect_timeout=5),reader=dict(host=str(SOCKET),port=PORT,dbname='postgres',user='nexusiq_project_reader',connect_timeout=5))
    (RUNTIME/'connections.json').write_text(json.dumps(config,indent=2))
    status=subprocess.run(['pg_ctl','-D',str(CLUSTER),'status'],capture_output=True)
    if status.returncode != 0:
        run(['pg_ctl','-D',str(CLUSTER),'-l',str(RUNTIME/'server.log'),'-w','start'])
    import psycopg
    with psycopg.connect(**config['owner'],autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname='nexusiq_project'").fetchone():
            conn.execute('CREATE DATABASE nexusiq_project OWNER nexusiq_owner')
            conn.execute('REVOKE ALL ON DATABASE nexusiq_project FROM PUBLIC')
    config['owner']['dbname']='nexusiq_project'
    config['reader']['dbname']='nexusiq_project'
    (RUNTIME/'connections.json').write_text(json.dumps(config,indent=2))
    return dict(status='running',socket=str(SOCKET),port=PORT,network_listener=False)


def stop():
    if db_config().get('mode')=='existing_local':
        raise RuntimeError('This uses an existing server. Do not stop shared PostgreSQL services; no server stop is needed.')
    if (CLUSTER/'PG_VERSION').exists():
        run(['pg_ctl','-D',str(CLUSTER),'-m','fast','-w','stop'])
    return dict(status='stopped',data_preserved=True)


def use_existing_local():
    """Create only the dedicated NexusIQ database on an available local server."""
    import psycopg
    from psycopg import sql
    user=getpass.getuser()
    bootstrap=dict(host='/tmp',port=5432,dbname='postgres',user=user,connect_timeout=5)
    with psycopg.connect(**bootstrap,autocommit=True) as conn:
        row=conn.execute("SELECT datname FROM pg_database WHERE datname='nexusiq_project'").fetchone()
        config_path=RUNTIME/'connections.json'
        if row and not config_path.exists():
            raise RuntimeError('A database with this name already exists without project ownership metadata; refusing to adopt it')
        if not row:
            if conn.execute("SELECT 1 FROM pg_roles WHERE rolname='nexusiq_project_reader'").fetchone():
                raise RuntimeError('The project reader role already exists; refusing to reuse an unrelated role')
            conn.execute(sql.SQL('CREATE DATABASE nexusiq_project OWNER {}').format(sql.Identifier(user)))
            conn.execute('REVOKE ALL ON DATABASE nexusiq_project FROM PUBLIC')
    owner=dict(bootstrap,dbname='nexusiq_project')
    reader=dict(owner,user='nexusiq_project_reader')
    RUNTIME.mkdir(parents=True,exist_ok=True)
    config=dict(mode='existing_local',owner=owner,reader=reader)
    (RUNTIME/'connections.json').write_text(json.dumps(config,indent=2))
    return dict(status='database_ready',database='nexusiq_project',mode='existing_local',server_configuration_changed=False)
