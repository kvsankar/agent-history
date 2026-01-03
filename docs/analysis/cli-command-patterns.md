# CLI Command Structure Patterns: Research Report

Based on analysis of industry-leading CLI tools (git, docker, kubectl, GitHub CLI, AWS CLI, npm, Terraform).

## 1. Primary Command Structure Patterns

### Pattern A: Noun-Verb (Docker, GitHub CLI)
```
<noun> <action> [arguments]
```

**Examples:**
- `docker container run` / `docker container stop`
- `gh repo create` / `gh issue list` / `gh pr view`

**Advantages:**
- Groups related operations under a single noun
- Naturally extensible for new object types
- Clear semantic meaning: "What object? What do I do with it?"

**Best for:** Tools managing multiple resource types with consistent CRUD operations

### Pattern B: Verb-Noun (kubectl, AWS CLI)
```
<action> <noun> [arguments]
```

**Examples:**
- `kubectl create deployment` / `kubectl delete pod`
- `aws s3 ls` / `aws cloudformation create-change-set`

**Advantages:**
- Verb-first mirrors natural language
- Tab-completion groups related operations by verb

**Best for:** Tools with primary workflow actions (create, delete, apply)

### Pattern C: Simple Command (npm, git core)
```
<action> [arguments]
```

**Examples:**
- `npm install` / `npm publish`
- `git commit` / `git push`

**Best for:** Single-purpose tools or dominant workflows

## 2. CRUD Operation Conventions

### Create Operations

| Tool | Pattern | Example |
|------|---------|---------|
| git | `add` verb | `git remote add origin <url>` |
| docker | implicit | `docker run` (creates container) |
| kubectl | explicit | `kubectl create deployment my-app` |
| gh | explicit | `gh issue create --title "Bug"` |

**Key insight:** `add` typically auto-creates the parent object.

### Read Operations (List vs Show)

| Operation | Verbs Used | Example |
|-----------|------------|---------|
| List many | `list`, `ls` | `gh issue list`, `docker ps` |
| View one | `show`, `view`, `describe` | `gh issue view 123`, `kubectl describe pod` |

**Convention:** Distinguish between listing multiple items and viewing single item details.

### Delete Operations

All tools use consistent verbs: `rm`, `delete`, `remove`

| Tool | Example |
|------|---------|
| git | `git remote remove origin` |
| docker | `docker container rm` |
| kubectl | `kubectl delete pod` |

## 3. Hierarchical Subcommand Organization

### Two-Level (Most Common)
```
<primary-noun> <action> [name]
```

Examples:
- `gh repo list`
- `docker image build`
- `git remote add`

### Three-Level (Complex Systems)
```
<noun> <sub-type> <action> [name]
```

Examples:
- `kubectl create service clusterip my-service`

**Recommendation:** Avoid going deeper than 3 levels.

## 4. Standard Flags (Universal Conventions)

| Flag | Meaning | Used By |
|------|---------|---------|
| `-h`, `--help` | Show help | All |
| `-v`, `--version` | Show version | All |
| `-q`, `--quiet` | Suppress output | Most |
| `-f`, `--force` | Override safety | git, docker, kubectl |
| `-o`, `--output` | Output format | kubectl, docker |
| `--dry-run` | Preview without executing | terraform, kubectl |
| `--json` | Machine-readable output | All modern tools |

## 5. Output Format Conventions

```bash
# Default: Human-readable table
docker ps
gh issue list

# Machine-readable
kubectl get pods -o json
gh issue list --json title,number

# Quiet/minimal (just IDs)
docker ps --quiet
```

**Convention:**
- Default: Human-readable, tabular
- `--json`, `-o json`: Structured data
- `--quiet`: Minimal output (IDs/names only)

## 6. Tool-Specific Patterns

### Git (Most Mature)
- Separates concerns: remotes, branches, staging
- `add` creates implicitly: `git remote add origin` (no `git remote create`)
- Consistent patterns within each domain

### Docker (Object-Centric)
- Structure: `docker <object> <command>`
- Objects: `container`, `image`, `network`, `volume`
- Legacy shortcuts: `docker run` = `docker container run`

### kubectl (Verb-First)
- Primary verbs: `create`, `get`, `apply`, `delete`
- Prefers declarative `apply` over imperative `create`
- Rich object hierarchy with sub-resources

### GitHub CLI (Nested Subcommands)
- Structure: `gh <domain> <action>`
- Domains: `repo`, `issue`, `pr`, `release`
- Clear `list` vs `view` distinction

## 7. Anti-Patterns to Avoid

| Anti-Pattern | Problem |
|--------------|---------|
| Inconsistent naming | `list-homes`, `show-workspace`, `get_session` |
| Too many levels | `tool project workspace session add` |
| Ambiguous verbs | `get` (fetch? retrieve?), `do` (what?) |
| Positional args only | `tool myws 2025-01-01` (what's the date?) |
| Hidden functionality | No `--help` per subcommand |

## 8. Recommendations for agent-history

### Current Structure (Good)
```
agent-history <object> <action> [arguments] [flags]
```

This follows the Docker/GitHub CLI noun-verb pattern.

### Objects
- `home` - sources (local, WSL, Windows, SSH)
- `workspace` / `ws` - query workspaces
- `session` / `ss` - browse conversations
- `project` - group workspaces
- `export` - save to files
- `stats` - metrics

### Standard Actions
- `list` / `ls` - show many items
- `show` - show single item details
- `add` - add/create (auto-create parent)
- `remove` / `rm` - delete item

### Key Simplification: Auto-create on Add
```bash
# Like git remote add (no separate create step)
agent-history project add myproj workspace1   # creates project if needed
agent-history project add myproj workspace2   # adds to existing
```

This matches git's `remote add` pattern and eliminates the confusing two-step create-then-add workflow.

## Sources

- [Git Documentation](https://git-scm.com/docs)
- [Docker CLI Reference](https://docs.docker.com/reference/cli/)
- [Kubernetes kubectl Conventions](https://kubernetes.io/docs/reference/generated/kubectl/kubectl-commands/)
- [GitHub CLI Manual](https://cli.github.com/manual/)
- [AWS CLI User Guide](https://docs.aws.amazon.com/cli/latest/userguide/)
- [CLI Guidelines](https://clig.dev/)
