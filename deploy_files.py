from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import paramiko

PROJECT_ROOT = Path(__file__).resolve().parent
REMOTE_ROOT = "/opt/funnelhub"
UPLOAD_DIRS = ("src", "migrations", "tests", "inbox-app/dist")
UPLOAD_FILES = ("Dockerfile", "docker-compose.prod.yml", "pyproject.toml", "alembic.ini")
CLEAN_REMOTE_DIRS = {"inbox-app/dist"}
SKIP_DIRS = {"__pycache__", ".venv", ".pytest_cache", "node_modules"}
SKIP_FILES = {".DS_Store"}


def load_local_env(path: Path = PROJECT_ROOT / ".env") -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required.")
    return value


def remote_path_for(local_dir: Path, local_path: Path, remote_dir: str) -> str:
    relative_path = local_path.relative_to(local_dir).as_posix()
    return f"{remote_dir}/{relative_path}"


def ensure_remote_dir(sftp: paramiko.SFTPClient, remote_dir: str) -> None:
    try:
        sftp.stat(remote_dir)
    except FileNotFoundError:
        sftp.mkdir(remote_dir)


def remove_remote_tree(sftp: paramiko.SFTPClient, remote_dir: str) -> None:
    try:
        entries = sftp.listdir_attr(remote_dir)
    except FileNotFoundError:
        return

    for entry in entries:
        path = f"{remote_dir}/{entry.filename}"
        if stat.S_ISDIR(entry.st_mode or 0):
            remove_remote_tree(sftp, path)
            sftp.rmdir(path)
        else:
            sftp.remove(path)


def upload_dir(sftp: paramiko.SFTPClient, local_dir: Path, remote_dir: str) -> None:
    ensure_remote_dir(sftp, remote_dir)
    for root, dirs, files in os.walk(local_dir):
        dirs[:] = [directory for directory in dirs if directory not in SKIP_DIRS]
        root_path = Path(root)
        remote_root = remote_path_for(local_dir, root_path, remote_dir)
        ensure_remote_dir(sftp, remote_root)

        for file_name in files:
            if file_name in SKIP_FILES or file_name.endswith(".pyc"):
                continue
            local_path = root_path / file_name
            remote_path = remote_path_for(local_dir, local_path, remote_dir)
            print(f"Uploading {local_path} to {remote_path}...")
            sftp.put(str(local_path), remote_path)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")

    load_local_env()
    ssh_host = required_env("SSH_HOST")
    ssh_user = required_env("SSH_USER")
    ssh_password = required_env("SSH_PASSWORD")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ssh_host, username=ssh_user, password=ssh_password)

    try:
        sftp = ssh.open_sftp()
        try:
            for directory in UPLOAD_DIRS:
                if directory in CLEAN_REMOTE_DIRS:
                    remove_remote_tree(sftp, f"{REMOTE_ROOT}/{directory}")
                upload_dir(sftp, PROJECT_ROOT / directory, f"{REMOTE_ROOT}/{directory}")
            for file_name in UPLOAD_FILES:
                local_path = PROJECT_ROOT / file_name
                remote_path = f"{REMOTE_ROOT}/{file_name}"
                print(f"Uploading {local_path} to {remote_path}...")
                sftp.put(str(local_path), remote_path)
        finally:
            sftp.close()

        command = (
            f"cd {REMOTE_ROOT} && "
            "docker compose -f docker-compose.prod.yml build app funnel-worker telegram-bot && "
            "docker compose -f docker-compose.prod.yml run --rm app alembic upgrade head && "
            "docker compose -f docker-compose.prod.yml up -d app funnel-worker telegram-bot"
        )
        _, stdout, stderr = ssh.exec_command(command)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        exit_status = stdout.channel.recv_exit_status()
        print("STDOUT:", out)
        print("STDERR:", err)
        if exit_status != 0:
            raise RuntimeError(f"Remote deploy command failed with exit status {exit_status}.")
    finally:
        ssh.close()


if __name__ == "__main__":
    main()
