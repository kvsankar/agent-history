# HTML Timeline Export Spec

## Status

Draft, with product decisions captured from the initial design discussion. This spec captures the intended direction for an enhanced offline HTML export that visualizes exported sessions on a shared time axis and lets the user inspect a selected session's conversation.

## Decisions

- Timeline HTML is the default `--format html` experience.
- Single-session HTML exports still show the same timeline shell with one session bar for consistency.
- Session intervals use wall-clock start and end timestamps.
- The timeline covers the resolved scope requested by the user: session, workspace, project, home, all workspaces, or any resolved combination.
- Export scale may be thousands of sessions, so the default architecture must avoid embedding every conversation into one massive HTML file.

## Remaining Product Questions

1. Should the selected conversation display in an iframe below the timeline, or should the panel show a compact preview plus an "open full conversation" link?
2. For very large exports, should the timeline initially group by day/week/workspace and expand on demand, or is a dense searchable list plus zoom sufficient?
3. Should subagent bars be visually nested near their parent session when lineage is known, or should they stay purely track-assigned by time?

## Goals

- Provide an offline, self-contained HTML timeline for exported sessions.
- Show the full export time span, whether minutes, hours, days, or months.
- Render each session as a horizontal interval positioned by start and end timestamp.
- Place concurrent sessions into separate visual tracks so overlapping work is legible.
- Color code sessions by coding agent.
- Distinguish subagent sessions from main sessions with related shades or visual treatments.
- Let the user select a session or subagent session and view its conversation below the timeline.
- Preserve the current conversation rendering quality: turns, tool calls, tool results, raw views, diffs, and metadata.
- Scale to thousands of sessions without requiring a local web server.

## Non-Goals

- No network dependency or server requirement.
- No live playback or animation in the first version.
- No editing, merging, annotating, or deleting sessions.
- No dependency on external JavaScript or CSS CDNs.
- No replacement for Markdown or NDJSON export.

## Current State

`agent_history/export/html.py` renders one self-contained HTML document per session. `SessionExportHandler` writes one `.html` file per exported session when `--format html` is used. Multi-workspace and multi-home exports may also produce `index.md`, but there is no HTML overview.

The timeline feature should build on the existing parsed session pipeline. Export tasks already provide the source session, home, workspace, workspace display name, agent type, source file, and parsed messages. The first and last message timestamps can be used to compute session intervals.

## Proposed User Experience

When the user exports any session scope to HTML, cagelens writes a timeline index page:

```bash
cagelens session export myproject --format html
```

Output:

```text
.cagelens/exports/
  index.html
  home/user/myproject/
    20260609101500_session-a.html
    20260609104000_session-b.html
```

The exact folder tree follows the resolved export scope and existing `--flat` behavior, but `index.html` is the entry point for the HTML export. Per-session HTML files remain detail pages.

The `index.html` page contains:

- Export summary: workspace, source homes, session count, visible date range.
- Timeline viewport with adaptive tick marks.
- Track rows containing session bars.
- Agent legend.
- Controls for zooming, panning, fitting to full range, filtering agents, and optionally filtering workspaces/sources.
- Selection panel below the timeline that shows the selected session's conversation detail page or a preview with a link to the detail page.

Initial load behavior:

- The timeline fits the full exported date range.
- Sessions are sorted by start time.
- For one-session exports, the only session is selected by default.
- For larger exports, no session is selected by default unless the session count is below a small threshold.
- The conversation panel shows either the selected session detail page, a compact preview, or an empty state.

Selection behavior:

- Clicking a session bar selects it.
- The selected bar gets a clear outline and is scrolled into view if needed.
- The conversation panel updates to the selected session.
- The user can open the full per-session HTML page directly.
- Keyboard selection is supported with focusable bars and arrow navigation.

## Scope Behavior

The timeline represents exactly the concrete scope resolved by the command:

- `session export <session-file> --format html`: one-session timeline.
- `session export <workspace> --format html`: timeline for that workspace's resolved sessions.
- `project export <project> --format html`: timeline for all sessions in the project scope.
- `session export --aw --format html`: timeline for all workspaces in the selected homes.
- `session export --ah --aw --format html`: timeline for all resolved local/WSL/Windows/remote/web sources.

For very broad scopes, the index page must provide workspace/source filters and search. The timeline data model should include workspace and source dimensions rather than generating a separate timeline unless a later UX pass proves that per-workspace pages are easier to navigate.

## Timeline Semantics

### Session Start

Use the first parseable timestamp from the session's parsed messages.

Fallbacks, in order:

1. Session metadata timestamp, if exposed by the backend.
2. Source file mtime.
3. Export time.

Sessions with fallback timestamps should be marked in metadata so the UI can show "estimated".

### Session End

Use the last parseable timestamp from the session's parsed messages. This is wall-clock duration, including idle gaps inside the session.

If start and end are identical or end is missing, render a minimum visual width while retaining the true timestamp in metadata.

### Export Time Range

The timeline range is:

```text
min(session.start) ... max(session.end)
```

Add a small visual padding at both ends. Tick granularity is adaptive:

- Under 1 hour: minutes.
- 1 to 48 hours: hours.
- 2 to 90 days: days.
- Over 90 days: months.

### Track Assignment

Assign sessions to the first track whose latest end time is less than or equal to the session start. If no track is available, create a new track.

Algorithm:

1. Sort sessions by start time, then end time, then stable session ID.
2. Maintain each track's current end time.
3. Place each session in the first non-overlapping track.
4. Treat subagent sessions as normal intervals for collision purposes.

This produces compact tracks while guaranteeing concurrent sessions do not overlap visually.

## Session Model

The timeline renderer should derive a compact model per session:

```json
{
  "id": "stable-session-id",
  "title": "session filename or first user prompt",
  "agent": "claude",
  "is_subagent": false,
  "parent_session_id": null,
  "parent_message_id": null,
  "lineage_quality": "none",
  "workspace": "/home/user/myproject",
  "workspace_display": "/home/user/myproject",
  "home": "local",
  "source_file": "...",
  "html_file": "20260609101500_session-a.html",
  "start": "2026-06-09T10:15:00Z",
  "end": "2026-06-09T10:42:31Z",
  "duration_seconds": 1651,
  "message_count": 42,
  "turn_count": 9,
  "tool_call_count": 18,
  "timestamp_quality": "message"
}
```

The model should be serialized into the generated HTML as JSON for client-side layout and interaction.

## Lineage and Subagent Detection

Lineage should be captured where the source format exposes it, but the implementation must not assume that every agent currently provides a reliable parent session/message relationship in the normalized parser output.

Current local evidence:

- Claude Code: strong support. Claude records include `uuid`, `parentUuid`, and `sessionId`. Agent files use the `agent-*.jsonl` filename pattern and share the parent conversation `sessionId`; docs also note `isSidechain`, `agentId`, and `userType` for agent files.
- Pi: message-level support. The Pi backend normalizes `id` and `parent_id` from `id` and `parentId`. Session-level subagent detection should use session header or `session_info.parentId` if present.
- Gemini CLI: partial support. Docs say subagent sessions can be nested under `chats/<parentSessionId>/<agentId>.jsonl`. The current workspace resolver already accounts for nested chat paths, but the parser does not currently preserve message `id` in normalized messages. Timeline implementation should add preservation of message IDs and derive parent session ID from the nested path when present.
- Codex CLI: limited support in the current parser. Codex records include session metadata and turn context, but the normalized parser currently does not preserve a message parent chain. Timeline implementation should use explicit session/thread metadata if present and otherwise mark lineage as unavailable.

Lineage fields:

- `is_subagent`: true when source filename/path/metadata identifies a subagent session.
- `parent_session_id`: parent session identifier when known.
- `parent_message_id`: parent/spawn message identifier when known.
- `lineage_quality`: one of `explicit`, `inferred`, or `none`.

Subagent detection rules:

1. Prefer explicit backend metadata.
2. Use known storage conventions such as Claude `agent-*.jsonl` and Gemini nested `chats/<parentSessionId>/<agentId>.jsonl`.
3. Use message parent IDs for intra-session lineage and forks, but do not treat every fork as a subagent.
4. If no reliable parent can be found, still render the session normally and leave lineage fields null.

## Agent Colors

Use stable semantic colors, with main/subagent variants:

- Claude: blue main, lighter/darker blue subagent.
- Codex: green main, lighter/darker green subagent.
- Gemini: amber main, lighter/darker amber subagent.
- Pi: violet main, lighter/darker violet subagent.
- Unknown: gray.

Colors must work in light and dark mode and meet reasonable contrast for labels and outlines.

Subagents should also have a non-color cue, such as a striped fill, dotted border, or "sub" badge, so the distinction is not color-only.

## Conversation Panel

The selected session's conversation should appear below the timeline.

Default scalable implementation:

- Continue writing one full HTML page per session using the existing conversation renderer.
- The timeline `index.html` stores compact session metadata and relative links to those detail pages.
- On selection, update a detail panel below the timeline.
- Preferred panel behavior is an iframe pointed at the selected per-session HTML page, with a plain link fallback.
- If iframe behavior is poor under `file://` in target browsers, fall back to a compact metadata/first-prompt preview plus link.

Reasoning:

- Keeps the export offline and self-contained.
- Scales to thousands of sessions without embedding all conversations in one document.
- Avoids browser restrictions around JavaScript `fetch()` from `file://`.
- Avoids duplicating conversation rendering logic.

Small-export enhancement:

- For exports below a configurable threshold, a future version may embed conversation fragments directly for instant selection.
- This must not be the default for broad scopes.

## Controls

Minimum controls:

- Fit: reset viewport to full exported range.
- Zoom in.
- Zoom out.
- Agent filters.
- Text search by session title, ID, workspace, or first prompt.
- Workspace/source filters for broad scopes.
- Hide/show subagents.

Nice-to-have controls:

- Jump to selected session.
- Density mode for large exports.
- Group by workspace/source/day.

## Accessibility

- Timeline bars are buttons or focusable elements with meaningful accessible names.
- Keyboard users can select sessions.
- Selected state uses `aria-selected` or equivalent.
- Legend and filters have labels.
- Timeline remains usable without hover-only information.
- Colors are not the only carrier of agent/subagent state.

## Responsive Behavior

Desktop:

- Timeline occupies the top of the page.
- Conversation panel appears below.
- Wide timelines support horizontal scroll or zoom/pan.

Mobile:

- Timeline remains horizontally scrollable.
- Tracks keep stable row height.
- Session bars have minimum tap target height.
- Conversation panel stacks below controls.

## Implementation Plan

1. Add a timeline export data builder.
   - Input: export tasks and parsed messages.
   - Output: normalized session models with start/end, counts, agent, workspace, home, output paths, and lineage fields.

2. Add a track layout helper.
   - Pure Python function that assigns `track_index` to each session.
   - Unit test overlapping, touching, nested, and zero-duration sessions.

3. Preserve lineage fields in parser output where available.
   - Claude already exposes message lineage in source records; ensure timeline can access it.
   - Pi already normalizes `id` and `parent_id`.
   - Gemini should preserve message `id` and derive nested parent session IDs.
   - Codex should preserve any explicit session/thread metadata available, but may report lineage as `none`.

4. Add an HTML timeline renderer.
   - New function, likely `render_html_timeline_export(...)`.
   - Reuse styling language from `agent_history/export/html.py`.
   - Keep only compact timeline/session metadata in the index page.
   - Keep all JavaScript inline.

5. Integrate with `SessionExportHandler`.
   - For `--format html`, write the timeline `index.html` as the main entry point.
   - Continue writing per-session HTML files as detail pages.
   - For single-session exports, still write an `index.html` with one timeline item.
   - Respect the resolved scope rather than forcing workspace-only grouping.

6. Update tests.
   - HTML export writes `index.html` for single-session and multi-session exports.
   - Timeline JSON includes sessions with correct agents, timestamps, durations, and tracks.
   - Overlapping sessions occupy different tracks.
   - Non-overlapping sessions can reuse tracks.
   - Subagents get distinguishable class/data attributes.
   - Known lineage fields are populated for Claude, Pi, and Gemini nested sessions.
   - Codex sessions without parent metadata are marked `lineage_quality: "none"`.
   - HTML escapes user content and metadata.
   - Existing per-session HTML renderer tests remain valid, with CLI expectations updated for `index.html`.

7. Update docs.
   - `README.md`
   - `docs/user/usage.md`
   - `CHANGELOG.md`

## Testing Strategy

Unit tests:

- Timestamp extraction from parsed messages.
- Track assignment.
- Agent/subagent classification.
- Lineage extraction and quality classification.
- Timeline model serialization.

CLI tests:

- `session export --format html` with multiple sessions writes timeline index.
- `session export <session-file> --format html` writes a one-item timeline index and a detail page.
- `--flat` behavior is deterministic.
- `--force` rewrites timeline index.
- `--agent` filters affect timeline content.
- `--minimal` still affects per-session detail pages.
- Broad scopes with many sessions do not embed all conversation HTML in the index.

HTML content tests:

- Contains timeline root.
- Contains embedded timeline model JSON.
- Contains session bar data attributes.
- Contains detail-page links and/or iframe target metadata.
- Escapes unsafe content.

Manual/browser checks:

- Light/dark mode.
- Keyboard selection.
- Zoom and fit controls.
- Large export performance.
- Mobile width behavior.

## Risks

- Iframe behavior can vary under `file://`; every selected session must also have a normal link fallback.
- Some agents or historical sessions may lack reliable timestamps.
- Parent/subagent linkage may be incomplete or agent-specific.
- `file://` browser restrictions make JavaScript fetch-based lazy loading unreliable without a server.
- Track density can become visually noisy for exports with many overlapping sessions.

## Future Extensions

- Minimap overview for very long exports.
- Activity heatmap by hour/day.
- Tool-use overlays or badges.
- Token usage overlays.
- Search result highlighting in the timeline.
- Export bundle mode with external JSON and assets for very large exports.
- Compare sessions by selecting multiple bars.
