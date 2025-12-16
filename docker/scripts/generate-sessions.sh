#!/bin/bash
# Generate synthetic AI session data for testing
# Usage: generate-sessions.sh user1,user2,...

set -e

USERS="${1:-alice,bob}"
TIMESTAMP="2025-01-15T10:00:00Z"
TIMESTAMP2="2025-01-15T10:00:05Z"

generate_claude_session() {
    local user=$1
    local workspace=$2
    local session_id=$3

    local projects_dir="/home/$user/.claude/projects"
    local workspace_encoded="-home-$user-$workspace"
    local session_dir="$projects_dir/$workspace_encoded"

    mkdir -p "$session_dir"

    # Create main session JSONL
    cat > "$session_dir/$session_id.jsonl" << EOF
{"type":"user","message":{"role":"user","content":"Hello from $workspace"},"timestamp":"$TIMESTAMP","uuid":"user-msg-1","sessionId":"$session_id","cwd":"/home/$user/$workspace"}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Hi! I'm helping you with $workspace."}]},"timestamp":"$TIMESTAMP2","uuid":"asst-msg-1","sessionId":"$session_id","model":"claude-sonnet-4-20250514"}
EOF

    chown -R "$user:$user" "/home/$user/.claude"
    echo "  Created Claude session: $user/$workspace/$session_id"
}

generate_codex_session() {
    local user=$1
    local workspace=$2
    local session_id=$3

    # Codex uses date-based directory structure: ~/.codex/sessions/YYYY/MM/DD/
    local sessions_dir="/home/$user/.codex/sessions/2025/01/15"
    mkdir -p "$sessions_dir"

    # Create Codex JSONL (different format from Claude)
    cat > "$sessions_dir/$session_id.jsonl" << EOF
{"type":"message","role":"user","content":[{"type":"input_text","text":"Help me with $workspace"}],"create_time":"2025-01-15T10:00:00.000Z"}
{"type":"message","role":"assistant","content":[{"type":"output_text","text":"I'll help you with $workspace."}],"create_time":"2025-01-15T10:00:05.000Z"}
EOF

    # Codex also needs a workspace marker
    local cwd_dir="/home/$user/.codex/cwd"
    mkdir -p "$cwd_dir"
    echo "/home/$user/$workspace" > "$cwd_dir/$session_id"

    chown -R "$user:$user" "/home/$user/.codex"
    echo "  Created Codex session: $user/2025/01/15/$session_id"
}

generate_gemini_session() {
    local user=$1
    local workspace=$2
    local session_id=$3

    # Gemini uses hash-based structure: ~/.gemini/sessions/HASH.json
    local sessions_dir="/home/$user/.gemini/sessions"
    mkdir -p "$sessions_dir"

    # Generate a fake hash for the workspace
    local project_hash=$(echo -n "/home/$user/$workspace" | md5sum | cut -c1-32)

    # Create Gemini JSON (single JSON file, not JSONL)
    cat > "$sessions_dir/$project_hash.json" << EOF
{
  "id": "$session_id",
  "cwd": "$project_hash",
  "startTime": "2025-01-15T10:00:00.000Z",
  "lastUpdated": "2025-01-15T10:00:10.000Z",
  "messages": [
    {
      "role": "user",
      "content": "Help with $workspace please",
      "timestamp": "2025-01-15T10:00:00.000Z"
    },
    {
      "role": "model",
      "content": "I'll help you with $workspace.",
      "timestamp": "2025-01-15T10:00:05.000Z"
    }
  ]
}
EOF

    # Create hash index for workspace resolution
    local index_dir="/home/$user/.gemini"
    mkdir -p "$index_dir"
    echo "{\"$project_hash\": \"/home/$user/$workspace\"}" > "$index_dir/hash_index.json"

    chown -R "$user:$user" "/home/$user/.gemini"
    echo "  Created Gemini session: $user/$project_hash"
}

# Create sessions for each user
IFS=',' read -ra USER_ARRAY <<< "$USERS"
for user in "${USER_ARRAY[@]}"; do
    echo "Generating sessions for user: $user"

    # Create project directories (the actual code directories)
    mkdir -p "/home/$user/myproject"
    mkdir -p "/home/$user/another-project"
    chown -R "$user:$user" "/home/$user/myproject" "/home/$user/another-project"

    # Generate Claude sessions
    generate_claude_session "$user" "myproject" "session-claude-001"
    generate_claude_session "$user" "another-project" "session-claude-002"

    # Generate Codex sessions
    generate_codex_session "$user" "myproject" "session-codex-001"

    # Generate Gemini sessions
    generate_gemini_session "$user" "myproject" "session-gemini-001"

    echo "Sessions created for $user"
done

echo "All sessions generated successfully"
