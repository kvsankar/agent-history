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
    local rollout_id="rollout-2025-01-15T10-00-00-${session_id}"

    # Current Codex rollouts use event envelopes under rollout-*.jsonl.
    cat > "$sessions_dir/$rollout_id.jsonl" << EOF
{"timestamp":"2025-01-15T10:00:00.000Z","type":"session_meta","payload":{"id":"$session_id","cwd":"/home/$user/$workspace","cli_version":"0.99.0-test"}}
{"timestamp":"2025-01-15T10:00:00.100Z","type":"turn_context","payload":{"cwd":"/home/$user/$workspace","model":"gpt-5-codex-test"}}
{"timestamp":"2025-01-15T10:00:01.000Z","type":"response_item","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"Help me with $workspace"}]}}
{"timestamp":"2025-01-15T10:00:03.000Z","type":"response_item","payload":{"type":"function_call","name":"shell","call_id":"call_${session_id}","arguments":"{\"cmd\":\"pwd\"}"}}
{"timestamp":"2025-01-15T10:00:04.000Z","type":"response_item","payload":{"type":"function_call_output","call_id":"call_${session_id}","output":"/home/$user/$workspace"}}
{"timestamp":"2025-01-15T10:00:05.000Z","type":"response_item","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"I'll help you with $workspace."}]}}
{"timestamp":"2025-01-15T10:00:06.000Z","type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":42,"cached_input_tokens":4,"output_tokens":12,"reasoning_output_tokens":3}}}}
EOF

    # Codex also needs a workspace marker in cwd directory
    local cwd_dir="/home/$user/.codex/cwd"
    mkdir -p "$cwd_dir"
    echo "/home/$user/$workspace" > "$cwd_dir/$session_id"

    chown -R "$user:$user" "/home/$user/.codex"
    echo "  Created Codex session: $user/2025/01/15/$rollout_id"
}

generate_gemini_session() {
    local user=$1
    local workspace=$2
    local session_id=$3

    # Use a stable project identifier. Current Gemini can use registry slugs
    # rather than SHA-only identifiers.
    local project_hash="project-${user}-${workspace}"

    # Current Gemini sessions are append-only JSONL under
    # ~/.gemini/tmp/{project-id}/chats/session-*.jsonl.
    local sessions_dir="/home/$user/.gemini/tmp/$project_hash/chats"
    mkdir -p "$sessions_dir"

    cat > "$sessions_dir/$session_id.jsonl" << EOF
{"sessionId":"$session_id","projectHash":"$project_hash","startTime":"2025-01-15T10:00:00.000Z","lastUpdated":"2025-01-15T10:00:10.000Z","kind":"conversation"}
{"id":"${session_id}-user-1","timestamp":"2025-01-15T10:00:00.000Z","type":"user","content":[{"text":"Help with $workspace please"}]}
{"id":"${session_id}-gemini-1","timestamp":"2025-01-15T10:00:05.000Z","type":"gemini","model":"gemini-2.5-flash-test","content":[{"text":"I'll inspect the workspace."},{"functionCall":{"name":"read_file","args":{"path":"README.md"}}}],"tokens":{"input":30,"output":10,"cached":2,"total":42}}
{"id":"${session_id}-tool-1","timestamp":"2025-01-15T10:00:06.000Z","type":"tool","content":[{"functionResponse":{"name":"read_file","response":{"output":"synthetic docker fixture"}}}]}
{"id":"${session_id}-gemini-2","timestamp":"2025-01-15T10:00:08.000Z","type":"gemini","model":"gemini-2.5-flash-test","content":[{"text":"I'll help you with $workspace."}],"tokens":{"input":12,"output":8,"cached":0,"total":20}}
{"$set":{"summary":"Synthetic Gemini Docker session","lastUpdated":"2025-01-15T10:00:10.000Z"}}
EOF

    # Keep one legacy JSON session to verify backward compatibility.
    cat > "$sessions_dir/${session_id}-legacy.json" << EOF
{"id":"${session_id}-legacy","cwd":"$project_hash","startTime":"2025-01-15T10:00:00.000Z","lastUpdated":"2025-01-15T10:00:10.000Z","messages":[{"role":"user","content":"Legacy Gemini help with $workspace","timestamp":"2025-01-15T10:00:00.000Z"},{"role":"model","content":"Legacy Gemini response for $workspace.","timestamp":"2025-01-15T10:00:05.000Z"}]}
EOF

    # Create hash index for workspace resolution.
    local index_dir="/home/$user/.gemini"
    mkdir -p "$index_dir"
    echo "{\"$project_hash\": \"/home/$user/$workspace\"}" > "$index_dir/hash_index.json"

    chown -R "$user:$user" "/home/$user/.gemini"
    echo "  Created Gemini session: $user/$project_hash/chats/$session_id"
}

generate_pi_session() {
    local user=$1
    local workspace=$2
    local session_id=$3

    local encoded_workspace="--home-$user-$workspace--"
    local sessions_dir="/home/$user/.pi/agent/sessions/$encoded_workspace"
    mkdir -p "$sessions_dir"

    cat > "$sessions_dir/$session_id.jsonl" << EOF
{"type":"session","id":"$session_id","cwd":"/home/$user/$workspace","version":"0.99.0-test","model":"openai/gpt-4o-mini"}
{"type":"message","id":"${session_id}-user-1","timestamp":"2025-01-15T10:00:00.000Z","message":{"role":"user","content":"Help with $workspace from Pi"}}
{"type":"message","id":"${session_id}-assistant-1","parentId":"${session_id}-user-1","timestamp":"2025-01-15T10:00:05.000Z","message":{"role":"assistant","model":"openai/gpt-4o-mini","content":[{"type":"text","text":"I'll help you with $workspace."},{"type":"toolCall","id":"tool_${session_id}","name":"readFile","arguments":{"path":"README.md"}}],"usage":{"input_tokens":24,"output_tokens":9}}}
{"type":"message","id":"${session_id}-tool-1","parentId":"${session_id}-assistant-1","timestamp":"2025-01-15T10:00:06.000Z","message":{"role":"toolResult","toolCallId":"tool_${session_id}","toolName":"readFile","content":"synthetic docker fixture","isError":false}}
EOF

    chown -R "$user:$user" "/home/$user/.pi"
    echo "  Created Pi session: $user/$encoded_workspace/$session_id"
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

    # Generate Pi sessions
    generate_pi_session "$user" "myproject" "session-pi-001"

    echo "Sessions created for $user"
done

echo "All sessions generated successfully"
