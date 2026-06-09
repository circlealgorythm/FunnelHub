import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('31.129.110.56', username='root', password='QNgJj2pc&9j%')

cmd = 'ls -la /opt/funnelhub'
stdin, stdout, stderr = ssh.exec_command(cmd)

print('STDOUT:')
print(stdout.read().decode('utf-8', errors='replace'))
print('STDERR:')
print(stderr.read().decode('utf-8', errors='replace'))

ssh.close()
