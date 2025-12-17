#!/bin/bash
# Entrypoint for SSH node containers
# Sets up users and generates session data before starting SSH

set -e

echo "=== Node Entrypoint ==="
echo "Hostname: $(hostname)"
echo "Users to create: ${NODE_USERS:-alice,bob}"

# Wait for SSH keys volume to be ready (might be created by another container)
echo "Waiting for SSH keys volume..."
sleep 2

# Create users with SSH access
/usr/local/bin/create-users.sh "${NODE_USERS:-alice,bob}"

# Generate synthetic session data
/usr/local/bin/generate-sessions.sh "${NODE_USERS:-alice,bob}"

# Add known_hosts entries for other nodes (to prevent host key prompts)
# This runs for each user
IFS=',' read -ra USER_ARRAY <<< "${NODE_USERS:-alice,bob}"
for user in "${USER_ARRAY[@]}"; do
    SSH_DIR="/home/$user/.ssh"
    mkdir -p "$SSH_DIR"

    # Create SSH config to disable strict host checking for test network
    cat > "$SSH_DIR/config" << EOF
Host node-alpha node-beta
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    LogLevel ERROR
EOF
    chmod 600 "$SSH_DIR/config"
    chown "$user:$user" "$SSH_DIR/config"
done

echo "=== Starting SSH Server ==="
exec "$@"
