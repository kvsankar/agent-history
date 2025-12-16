#!/bin/bash
# Entrypoint for test runner container
# Sets up SSH client and waits for nodes to be ready

set -e

echo "=== Test Runner Entrypoint ==="
echo "User: $(whoami)"
echo "Working directory: $(pwd)"

# Set up SSH client
/usr/local/bin/setup-ssh-client.sh

# Wait for SSH nodes to be ready
echo "Waiting for SSH nodes to be ready..."

wait_for_ssh() {
    local host=$1
    local user=$2
    local max_attempts=30

    for i in $(seq 1 $max_attempts); do
        if ssh -o ConnectTimeout=2 "$user@$host" "echo ready" 2>/dev/null; then
            echo "  $host is ready (as $user)"
            return 0
        fi
        sleep 1
    done

    echo "ERROR: $host not ready after $max_attempts attempts"
    return 1
}

# Test connectivity to both nodes with first user
NODE_ALPHA="${NODE_ALPHA:-node-alpha}"
NODE_BETA="${NODE_BETA:-node-beta}"

# Get first user from each node
ALPHA_USER=$(echo "${ALPHA_USERS:-alice}" | cut -d',' -f1)
BETA_USER=$(echo "${BETA_USERS:-charlie}" | cut -d',' -f1)

wait_for_ssh "$NODE_ALPHA" "$ALPHA_USER"
wait_for_ssh "$NODE_BETA" "$BETA_USER"

echo "=== All nodes ready ==="
echo ""

# Run the command (default: pytest)
exec "$@"
