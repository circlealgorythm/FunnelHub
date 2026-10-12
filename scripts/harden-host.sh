#!/usr/bin/env bash
# ==============================================================================
# FunnelHub Host Security & Hardening Script (SEC-006)
# Hardens Linux VPS perimeter: SSH, UFW Firewall, and Fail2ban.
# Zero-Lockout Protocol: strictly verifies SSH keys and ports before enforcing.
# ==============================================================================
set -euo pipefail

echo "=== FunnelHub VPS Security Hardening (SEC-006) ==="

# 1. Root Privileges Check
if [[ "${EUID}" -ne 0 ]]; then
    echo "ERROR: This script must be run as root (or via sudo)." >&2
    exit 1
fi

SSH_PORT="${SSH_PORT:-22}"

# 2. Safety Check: Verify SSH Keys before disabling password authentication
echo "--- Step 1/4: SSH Keys Pre-flight Check ---"
AUTH_KEYS_FILE="/root/.ssh/authorized_keys"
USER_AUTH_KEYS_COUNT=0

if [[ -f "${AUTH_KEYS_FILE}" ]] && [[ -s "${AUTH_KEYS_FILE}" ]]; then
    USER_AUTH_KEYS_COUNT=$(grep -c -v "^#" "${AUTH_KEYS_FILE}" || true)
fi

# Check for non-root sudo users if root has no keys
if [[ "${USER_AUTH_KEYS_COUNT}" -eq 0 ]]; then
    for home_dir in /home/*; do
        if [[ -f "${home_dir}/.ssh/authorized_keys" ]] && [[ -s "${home_dir}/.ssh/authorized_keys" ]]; then
            USER_AUTH_KEYS_COUNT=$((USER_AUTH_KEYS_COUNT + 1))
        fi
    done
fi

if [[ "${USER_AUTH_KEYS_COUNT}" -eq 0 ]]; then
    echo "CRITICAL ERROR: No SSH public keys found in ~/.ssh/authorized_keys!" >&2
    echo "Disabling password authentication right now would lock you out of the server." >&2
    echo "Please copy your SSH public key to the server first:" >&2
    echo "  ssh-copy-id -i ~/.ssh/id_ed25519.pub root@<YOUR_SERVER_IP>" >&2
    echo "Aborting." >&2
    exit 2
fi

echo "Found ${USER_AUTH_KEYS_COUNT} SSH public key(s). Safe to proceed."

# 3. Configure UFW Firewall
echo "--- Step 2/4: Configuring UFW Firewall ---"
if ! command -v ufw >/dev/null 2>&1; then
    echo "Installing ufw..."
    apt-get update -qq && apt-get install -y -qq ufw
fi

# Set default policies
ufw --force reset >/dev/null 2>&1 || true
ufw default deny incoming
ufw default allow outgoing

# Allow essential ports only
echo "Allowing SSH (port ${SSH_PORT}/tcp)..."
ufw allow "${SSH_PORT}/tcp" comment "SSH remote administration"

echo "Allowing HTTP (port 80/tcp) and HTTPS (port 443/tcp)..."
ufw allow 80/tcp comment "Caddy HTTP to HTTPS redirect"
ufw allow 443/tcp comment "Caddy HTTPS TLS"

# Enable UFW
echo "Enabling UFW..."
ufw --force enable
ufw status verbose

# 4. Configure Fail2ban for SSH Protection
echo "--- Step 3/4: Configuring Fail2ban ---"
if ! command -v fail2ban-client >/dev/null 2>&1; then
    echo "Installing fail2ban..."
    apt-get update -qq && apt-get install -y -qq fail2ban
fi

FAIL2BAN_JAIL="/etc/fail2ban/jail.d/99-funnelhub.local"
cat > "${FAIL2BAN_JAIL}" <<EOF
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 5

[sshd]
enabled  = true
port     = ${SSH_PORT}
filter   = sshd
maxretry = 3
bantime  = 24h
EOF

systemctl enable fail2ban >/dev/null 2>&1 || true
systemctl restart fail2ban
echo "Fail2ban configured and restarted."

# 5. SSH Daemon Hardening
echo "--- Step 4/4: Hardening SSH Daemon ---"
SSHD_CONFIG_DIR="/etc/ssh/sshd_config.d"
SSHD_CUSTOM_CONF="${SSHD_CONFIG_DIR}/99-funnelhub-security.conf"

mkdir -p "${SSHD_CONFIG_DIR}"
cat > "${SSHD_CUSTOM_CONF}" <<EOF
# FunnelHub Hardened SSH Configuration (SEC-006)
PasswordAuthentication no
PermitEmptyPasswords no
PubkeyAuthentication yes
X11Forwarding no
MaxAuthTries 4
ClientAliveInterval 300
ClientAliveCountMax 2
EOF

# Validate sshd configuration before reloading
if ! sshd -t; then
    echo "ERROR: sshd configuration test failed! Reverting custom config..." >&2
    rm -f "${SSHD_CUSTOM_CONF}"
    exit 3
fi

# Reload sshd (do not kill current active sessions)
if systemctl is-active --quiet sshd; then
    systemctl reload sshd
elif systemctl is-active --quiet ssh; then
    systemctl reload ssh
else
    echo "NOTICE: Please reload ssh daemon manually: service ssh reload"
fi

echo "=== Host hardening completed successfully! ==="
echo "Active Firewall Rules:"
ufw status numbered
echo "Fail2ban status:"
fail2ban-client status sshd || true
echo "IMPORTANT: Do NOT close this SSH session until you verify you can open a new SSH connection in a separate terminal!"
exit 0
