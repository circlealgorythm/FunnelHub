import paramiko
import os

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('31.129.110.56', username='root', password='QNgJj2pc&9j%')

sftp = ssh.open_sftp()

FILES_TO_DEPLOY = [
    "inbox_app_dist.zip",
    "src/funnelhub/api/inbox.py",
    "src/funnelhub/services/inbox_database.py",
]

for local_path in FILES_TO_DEPLOY:
    remote_path = f"/opt/funnelhub/{local_path}"
    print(f"Uploading {local_path} to {remote_path}...")
    sftp.put(local_path, remote_path)

cmd = 'cd /opt/funnelhub && docker compose -f docker-compose.prod.yml restart app funnel-worker telegram-bot'
stdin, stdout, stderr = ssh.exec_command(cmd)

out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')

try:
    print('STDOUT:')
    print(out.encode('cp1251', errors='replace').decode('cp1251'))
    print('STDERR:')
    print(err.encode('cp1251', errors='replace').decode('cp1251'))
except Exception as e:
    pass

sftp.close()
ssh.close()
