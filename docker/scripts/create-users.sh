#!/bin/bash
# Create test users and set up SSH keys
# Usage: create-users.sh user1,user2,...

set -e

USERS="${1:-alice,bob}"
SSH_KEYS_DIR="/ssh-keys"

# Ensure SSH keys directory exists
mkdir -p "$SSH_KEYS_DIR"

# Generate shared SSH key pair if not exists (used by all users and test-runner)
if [ ! -f "$SSH_KEYS_DIR/id_ed25519" ]; then
    ssh-keygen -t ed25519 -f "$SSH_KEYS_DIR/id_ed25519" -N "" -q
    chmod 644 "$SSH_KEYS_DIR/id_ed25519.pub"
    chmod 600 "$SSH_KEYS_DIR/id_ed25519"
fi

# Read public key
PUB_KEY=$(cat "$SSH_KEYS_DIR/id_ed25519.pub")

# Create each user
IFS=',' read -ra USER_ARRAY <<< "$USERS"
for user in "${USER_ARRAY[@]}"; do
    echo "Creating user: $user"

    # Create user if not exists
    if ! id "$user" &>/dev/null; then
        useradd -m -s /bin/bash "$user"
    fi

    # Set up SSH authorized_keys
    SSH_DIR="/home/$user/.ssh"
    mkdir -p "$SSH_DIR"
    echo "$PUB_KEY" > "$SSH_DIR/authorized_keys"
    chmod 700 "$SSH_DIR"
    chmod 600 "$SSH_DIR/authorized_keys"
    chown -R "$user:$user" "$SSH_DIR"

    # Also set up private key for outbound SSH (user can SSH to other nodes)
    cp "$SSH_KEYS_DIR/id_ed25519" "$SSH_DIR/id_ed25519"
    cp "$SSH_KEYS_DIR/id_ed25519.pub" "$SSH_DIR/id_ed25519.pub"
    chmod 600 "$SSH_DIR/id_ed25519"
    chown -R "$user:$user" "$SSH_DIR"

    echo "User $user created with SSH access"
done

echo "All users created successfully"
