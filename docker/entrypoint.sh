#!/bin/bash
# Copies the developer's public key (bind-mounted read-only at /pubkey.pub)
# into the test user's authorized_keys, then hands PID 1 over to systemd.
set -euo pipefail

MLA_USER="${MLA_USER:-mla}"
SSH_DIR="/home/${MLA_USER}/.ssh"

if [ -f /pubkey.pub ] && [ -s /pubkey.pub ]; then
    install -d -o "${MLA_USER}" -g "${MLA_USER}" -m 700 "${SSH_DIR}"
    install -o "${MLA_USER}" -g "${MLA_USER}" -m 600 \
        /pubkey.pub "${SSH_DIR}/authorized_keys"
else
    echo "WARN: /pubkey.pub missing or empty -> public-key auth will not work" >&2
fi

exec "$@"
