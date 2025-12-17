#!/bin/bash
# Set up SSH client for test runner
# Copies shared SSH keys and configures SSH for passwordless auth

set -e

SSH_KEYS_DIR="/ssh-keys"
USER_SSH_DIR="$HOME/.ssh"

echo "Setting up SSH client for $(whoami)..."

# Create SSH directory
mkdir -p "$USER_SSH_DIR"
chmod 700 "$USER_SSH_DIR"

# Wait for SSH keys to be available
echo "Waiting for SSH keys..."
for i in {1..30}; do
    if [ -f "$SSH_KEYS_DIR/id_ed25519" ]; then
        break
    fi
    sleep 1
done

if [ ! -f "$SSH_KEYS_DIR/id_ed25519" ]; then
    echo "ERROR: SSH keys not found in $SSH_KEYS_DIR"
    exit 1
fi

# Copy SSH keys
cp "$SSH_KEYS_DIR/id_ed25519" "$USER_SSH_DIR/"
cp "$SSH_KEYS_DIR/id_ed25519.pub" "$USER_SSH_DIR/"
chmod 600 "$USER_SSH_DIR/id_ed25519"
chmod 644 "$USER_SSH_DIR/id_ed25519.pub"

# Create SSH config for test network
cat > "$USER_SSH_DIR/config" << EOF
# Test network SSH config
Host node-alpha node-beta
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    LogLevel ERROR
    BatchMode yes
    ConnectTimeout 10
EOF
chmod 600 "$USER_SSH_DIR/config"

echo "SSH client configured successfully"
