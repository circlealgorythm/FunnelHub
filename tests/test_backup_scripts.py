from pathlib import Path


def test_backup_script_structure() -> None:
    root = Path(__file__).resolve().parents[1]
    backup_script = root / "scripts" / "backup-db.sh"
    assert backup_script.exists(), "scripts/backup-db.sh must exist"

    content = backup_script.read_text(encoding="utf-8")
    assert "#!/usr/bin/env bash" in content
    assert "set -euo pipefail" in content
    assert "pg_dump" in content
    assert "--clean" in content
    assert "--if-exists" in content
    assert "gzip -9" in content
    assert "AES256" in content
    assert "RETENTION_DAYS" in content
    assert "find" in content and "-mtime" in content


def test_restore_script_structure() -> None:
    root = Path(__file__).resolve().parents[1]
    restore_script = root / "scripts" / "restore-db.sh"
    assert restore_script.exists(), "scripts/restore-db.sh must exist"

    content = restore_script.read_text(encoding="utf-8")
    assert "#!/usr/bin/env bash" in content
    assert "set -euo pipefail" in content
    assert "psql" in content
    assert "gpg" in content
    assert "gzip -d" in content
    assert "--force" in content


def test_cron_example_structure() -> None:
    root = Path(__file__).resolve().parents[1]
    cron_file = root / "scripts" / "backup-cron.example"
    assert cron_file.exists(), "scripts/backup-cron.example must exist"

    content = cron_file.read_text(encoding="utf-8")
    assert "backup-db.sh" in content
    assert "0 3 * * *" in content


def test_gitignore_protects_backups() -> None:
    root = Path(__file__).resolve().parents[1]
    gitignore = root / ".gitignore"
    assert gitignore.exists()

    content = gitignore.read_text(encoding="utf-8")
    assert "backups/" in content
    assert "*.sql.gz" in content
