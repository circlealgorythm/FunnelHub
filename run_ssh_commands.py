
import paramiko


def run_ssh_command(cmd):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    hostname = "31.129.110.56"
    username = "root"
    password = "QNgJj2pc&9j%"
    try:
        print(f"Connecting to {hostname}...")
        client.connect(hostname, username=username, password=password)
        print(f"Running: {cmd}")
        stdin, stdout, stderr = client.exec_command(cmd)
        out = stdout.read().decode('utf-8', errors='replace')
        err = stderr.read().decode('utf-8', errors='replace')
        exit_status = stdout.channel.recv_exit_status()
        print("STDOUT:")
        print(out.encode('cp1251', errors='replace').decode('cp1251'))
        print("STDERR:")
        print(err.encode('cp1251', errors='replace').decode('cp1251'))
        if exit_status != 0:
            print(f"Command failed with exit status {exit_status}")
    finally:
        client.close()

if __name__ == "__main__":
    commands = [
        "cd /opt/funnelhub && docker compose -f docker-compose.prod.yml logs --tail=100 app telegram-bot"
    ]
    for cmd in commands:
        run_ssh_command(cmd)
