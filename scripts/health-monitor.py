#!/usr/bin/env python3
"""Check VPS services and backup freshness; notify on changes via the existing bot."""

from __future__ import annotations

import ftplib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(os.environ.get("FUNNELHUB_ROOT", "/opt/funnelhub"))
STATE = ROOT / "backups" / ".health-monitor-state.json"
SERVICES = (
    "app",
    "telegram-bot",
    "most-telegram-bot",
    "funnel-worker",
    "most-funnel-worker",
    "most-vk-funnel-worker",
    "postgres",
    "redis",
)


def env_file(path: Path) -> dict[str, str]:
    values = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def check(env: dict[str, str]) -> list[str]:
    issues = []
    for name in SERVICES:
        try:
            result = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Running}}", f"funnelhub-{name}-1"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            running = result.returncode == 0 and result.stdout.strip() == "true"
        except (OSError, subprocess.TimeoutExpired):
            running = False
        if not running:
            issues.append(f"Контейнер {name} не работает")
    for label, command in (
        ("PostgreSQL", ["docker", "exec", "funnelhub-postgres-1", "pg_isready"]),
        (
            "Redis",
            [
                "docker",
                "exec",
                "funnelhub-app-1",
                "python",
                "-c",
                'import os,redis; assert redis.Redis.from_url(os.environ["REDIS_URL"]).ping()',
            ],
        ),
    ):
        try:
            result = subprocess.run(command, capture_output=True, timeout=15, check=False)
            if result.returncode:
                issues.append(f"{label} не отвечает на проверку")
        except (OSError, subprocess.TimeoutExpired):
            issues.append(f"{label} не отвечает на проверку")
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=10) as response:
            if response.status != 200:
                issues.append("Приложение не прошло проверку /health")
    except OSError:
        issues.append("Приложение не прошло проверку /health")
    total, _, free = shutil.disk_usage("/")
    if free / total < 0.15:
        issues.append("На диске осталось менее 15% свободного места")
    files = sorted((ROOT / "backups").glob("funnelhub_backup_*.sql.gz.gpg"))
    if not files or time.time() - files[-1].stat().st_mtime > 30 * 3600:
        issues.append("Нет серверного бэкапа за последние 30 часов")
    marker = ROOT / "backups" / ".last-successful-restore"
    if not marker.exists() or time.time() - marker.stat().st_mtime > 8 * 86400:
        issues.append("Нет успешной проверки восстановления за последние 8 дней")
    try:
        host = env.get("BACKUP_FTP_HOST") or env["REGRU_FTP_HOST"]
        user = env.get("BACKUP_FTP_USER") or env["FTP_MAIN_SITE_USER"]
        password = env.get("BACKUP_FTP_PASS") or env["FTP_MAIN_SITE_PASS"]
        with ftplib.FTP(host, timeout=15) as ftp:
            ftp.login(user, password)
            ftp.cwd("backups")
            names = set(ftp.nlst())
            if files and files[-1].name not in names:
                issues.append("Последнего серверного бэкапа нет на FTP")
    except (OSError, ftplib.Error, KeyError):
        issues.append("Не удалось проверить бэкапы на FTP")
    return issues


def notify(env: dict[str, str], message: str) -> None:
    token = env["INBOX_NOTIFY_TELEGRAM_BOT_TOKEN"]
    chat = env["INBOX_NOTIFY_TELEGRAM_CHAT_ID"]
    base = env["TELEGRAM_API_BASE_URL"].rstrip("/")
    url = f"{base}/bot{token}/sendMessage"
    if env.get("TELEGRAM_PROXY_SECRET"):
        url += "?" + urllib.parse.urlencode({"proxy_secret": env["TELEGRAM_PROXY_SECRET"]})
    data = urllib.parse.urlencode({"chat_id": chat, "text": message}).encode()
    request = urllib.request.Request(
        url, data=data, headers={"User-Agent": "Python/3.11 aiohttp/3.9.5"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        if not json.load(response).get("ok"):
            raise RuntimeError("Telegram rejected notification")


def main() -> int:
    env = env_file(ROOT / ".env")
    issues = check(env)
    try:
        previous = json.loads(STATE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        previous = []
    if issues != previous:
        text = (
            "FunnelHub: обнаружены проблемы:\n" + "\n".join(issues)
            if issues
            else "FunnelHub: ранее обнаруженные проблемы устранены."
        )
        notify(env, text)
        STATE.parent.mkdir(parents=True, exist_ok=True)
        temp = STATE.with_suffix(".tmp")
        temp.write_text(json.dumps(issues, ensure_ascii=False), encoding="utf-8")
        temp.replace(STATE)
    print("Проблем: " + str(len(issues)))
    return int(bool(issues))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"Ошибка мониторинга: {type(exc).__name__}", file=sys.stderr)
        sys.exit(2)
