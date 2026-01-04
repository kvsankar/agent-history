# Claude Collaboration Playbook

**Timeframe:** Oct–Dec 2025
**Scope:** Variety of CLI tools, web apps, visualization, documentation systems, and developer tooling

This playbook distills collaboration patterns observed across multiple teams. It delivers an action-first checklist for Claude and for human collaborators, combining tactical habits with nuanced communication guidance.

---

## 1. Claude’s Working Principles

### 1.1 Rebuild Context Before Typing
- Re-open README / CLAUDE.md / WIP / decision logs each session; teams change standards fast.
- Cache environment facts (package manager, lint configs, target frameworks, deployment flow) in your scratch space.
- When resuming long-running work, skim recent commits or iteration checklists so you don’t redo completed items.

### 1.2 Validate Everything Upfront
- Run `--help` or list subcommands before executing new CLIs; avoid “command not found” detours.
- `ls` before `cd` in repos with backend/, docs/, scripts/, etc.; run framework CLIs instead of brittle shell pipelines.
- Treat sub-agent output as untrusted until you verify paths, counts, and metadata.

### 1.3 Communicate in Structured Bursts
- State a lightweight plan when edits span multiple files, execute, and recap results (plan ➝ act ➝ report).
- Narrate investigations (symptom → hypothesis → evidence → conclusion) before applying fixes.
- Record decisions and todos in-line so future sessions inherit a living log, not guesswork.

### 1.4 Match Response Style to User Needs
- Default to concise, action-oriented answers; expand only when the problem is ambiguous.
- Use progressive disclosure: deliver essentials first, then add detail when asked.
- Format output consistently—markdown headings, code fences with language tags, tables for comparisons, checkmarks/crosses for status.

### 1.5 Respect Technical Constraints
- Assume professional-level collaborators; skip basic tutorials and focus on project-specific nuances.
- Align with established conventions (naming, folder layout, quality standards) and call them out when you spot inconsistencies.
- When reading older sessions, preserve terminology and architecture choices for continuity.

### 1.6 Keep Quality Bars Visible
- Mirror repo standards (line length, lint rules, complexity thresholds). Treat them as pass/fail gates.
- Show verification evidence: test command output, screenshots/notes for UX, or docs that were updated.
- When compromises are needed (dependency pinning, partial test coverage), note the risk plus remediation steps.

### 1.7 Adapt Quickly When Tools Push Back
- If legacy libraries or tight lint rules block progress, explore modern replacements instead of layering hacks.
- Document migrations: why they were needed, how to run them, how to roll back.
- Propagate related changes fully (config + docs + scripts); never leave “TODO: update later.”

### 1.8 Investigation & Iteration Patterns
- Expect spec-first workflows: read the spec, reference it while coding, validate against requirements.
- Support tight feedback loops: implement, self-test, summarize results, ask for confirmation.
- For complex bugs, run an investigation phase before proposing fixes; users often add context mid-analysis.
- Use sub-agents only for exploratory tasks and double-check their output.

### 1.9 Domain-Specific Reminders
- **CLI tools:** favor single-file utilities when requested, follow UNIX composability, include thorough help text, support both interactive and scripted modes.
- **Web apps:** respect framework idioms, include validation/error handling, consider security, and handle user input edge cases.
- **Visualization:** avoid magic constants, document coordinate transforms, optimize for large datasets, and ensure user interactions have clear visual cues.
- **Documentation systems:** support multiple output formats, generate real artifacts (not descriptions), maintain link integrity, and keep styling consistent.

---

## 2. User Playbook

### 2.1 Front-Load Context
- Link to canonical docs (WIP, decisions, specs) at the start of each request; mention the current dev phase and recent changes.
- State environment constraints (package tools, test suites, deployment targets) so Claude doesn’t discover them mid-task.
- If the session continues prior work, recap what’s done vs. pending.

### 2.2 Define Scope and Success
- Specify boundaries (“touch only config/docs,” “no sub-agents,” “don’t change public APIs”).
- Provide acceptance checkpoints (tests rerun, docs updated, scripts executable) and how you’ll verify them.
- Include validation steps you expect (commands to run, URLs to check, manual flows).

### 2.3 Give Focused Feedback
- Respond with numbered deltas: each bullet = one fix. Claude can then address them deterministically.
- Use topic bookends: explicitly close one task before switching contexts (e.g., “Blog deploy looks good; now let’s debug DNS.”).
- Ask Claude to show `--help` or list options before running complex commands to stay aligned.

### 2.4 Maintain Shared Artifacts
- Keep decision logs updated with approvals, rejections, and rationale so future sessions don’t re-litigate choices.
- Provide or request regression checklists, mock-data inventories, or script usage notes; Claude will execute them verbatim later.
- Encourage incremental documentation: ask Claude to update README/CLAUDE.md/WIP entries whenever behavior, APIs, or tooling change.

### 2.5 Balance Autonomy vs. Oversight
- Delegate research/drafts, but personally review critical migrations, infrastructure updates, or production pushes.
- Signal when you expect Claude to propose solutions (“find the best option and justify”) versus follow a strict design.
- Close the loop—confirm when work meets your needs. Positive confirmation prevents unnecessary iteration and clarifies ownership.

---

## 3. Collaboration Pattern That Works

1. **Shared Context** – User supplies docs + expectations; Claude rereads them before coding.
2. **Deliberate Execution** – Claude validates commands, states plan, performs work, documents changes, and surfaces verification proof.
3. **Documented Outcomes** – Code, scripts, and knowledge artifacts all update together; user confirms acceptance or outlines next steps.

Teams that repeated this loop delivered features, research, and tooling upgrades with minimal backtracking. Stick to the rhythm—context ➝ plan ➝ execute ➝ verify ➝ document—and every new session starts where the last one stopped.
