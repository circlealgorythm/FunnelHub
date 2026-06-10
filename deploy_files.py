import os
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('31.129.110.56', username='root', password='QNgJj2pc&9j%')

sftp = ssh.open_sftp()

def upload_dir(local_dir, remote_dir):
    try:
        sftp.stat(remote_dir)
    except FileNotFoundError:
        sftp.mkdir(remote_dir)
    for root, dirs, files in os.walk(local_dir):
        if '__pycache__' in root or '.venv' in root or '.pytest_cache' in root:
            continue
        for d in dirs:
            if d == '__pycache__' or d == '.pytest_cache': continue
            remote_path = os.path.join(remote_dir, os.path.relpath(os.path.join(root, d), local_dir)).replace('\\\\', '/').replace('\\', '/')
            try:
                sftp.stat(remote_path)
            except FileNotFoundError:
                sftp.mkdir(remote_path)
        for f in files:
            if f.endswith('.pyc') or f == '.DS_Store': continue
            local_path = os.path.join(root, f)
            remote_path = os.path.join(remote_dir, os.path.relpath(local_path, local_dir)).replace('\\\\', '/').replace('\\', '/')
            print(f"Uploading {local_path} to {remote_path}...")
            sftp.put(local_path, remote_path)

upload_dir('src', '/opt/funnelhub/src')
upload_dir('migrations', '/opt/funnelhub/migrations')
upload_dir('tests', '/opt/funnelhub/tests')

cmd = 'cd /opt/funnelhub && docker compose -f docker-compose.prod.yml up -d --build app funnel-worker telegram-bot ; docker compose -f docker-compose.prod.yml exec app alembic upgrade head'
stdin, stdout, stderr = ssh.exec_command(cmd)

out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')

print('STDOUT:', out)
print('STDERR:', err)

sftp.close()
ssh.close()
