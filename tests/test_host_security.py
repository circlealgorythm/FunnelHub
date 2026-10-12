from pathlib import Path


def test_harden_host_script_structure() -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "harden-host.sh"
    assert script.exists(), "scripts/harden-host.sh must exist"

    content = script.read_text(encoding="utf-8")
    assert "#!/usr/bin/env bash" in content
    assert "set -euo pipefail" in content

    # Root check
    assert "EUID" in content

    # Zero-Lockout pre-flight safety check
    assert "authorized_keys" in content
    assert "CRITICAL ERROR" in content or "ssh-copy-id" in content

    # UFW firewall
    assert "default deny incoming" in content
    assert "default allow outgoing" in content
    assert "ufw allow" in content
    assert "80/tcp" in content
    assert "443/tcp" in content

    # Fail2ban
    assert "fail2ban" in content
    assert "maxretry" in content
    assert "bantime" in content

    # SSH hardening
    assert "PasswordAuthentication no" in content
    assert "PubkeyAuthentication yes" in content
    assert "sshd -t" in content


def test_host_security_documentation() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = root / "scripts" / "HOST_SECURITY.md"
    assert doc.exists(), "scripts/HOST_SECURITY.md must exist"

    content = doc.read_text(encoding="utf-8")
    assert "Zero-Lockout" in content
    assert "ufw status verbose" in content
    assert "fail2ban-client status sshd" in content
    assert "unbanip" in content
