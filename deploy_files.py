import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('31.129.110.56', username='root', password='QNgJj2pc&9j%')

sftp = ssh.open_sftp()

FILES_TO_DEPLOY = [
    "inbox_app_dist.zip"
]

for local_path in FILES_TO_DEPLOY:
    remote_path = f"/opt/funnelhub/{local_path}"
    print(f"Uploading {local_path} to {remote_path}...")
    sftp.put(local_path, remote_path)

cmd = 'cd /opt/funnelhub && git pull && .venv/bin/alembic upgrade head && rm -rf inbox-app/dist/* && unzip -o inbox_app_dist.zip -d inbox-app/dist && docker compose -f docker-compose.prod.yml up -d --build app funnel-worker telegram-bot'
stdin, stdout, stderr = ssh.exec_command(cmd)

out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')

try:
    print('STDOUT:')
    print(out)
    print('STDERR:')
    print(err)
except Exception:
    pass

sftp.close()
ssh.close()
