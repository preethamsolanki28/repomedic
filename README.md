# RepoMedic

**Autonomous, Security-Hardened Repository Repair Agent**

RepoMedic is an agentic coding assistant designed to diagnose, repair, and verify bugs in codebases while maintaining rigorous security boundaries. It pairs local open-weights language models with LangGraph orchestration, ephemeral workspace isolation, containerized zero-network verification, and real-time **ArmorIQ Policy Decision Point (PDP)** enforcement on all protected tool actions.

---

## Key Highlights

- **Local LLM Execution**: Uses **Devstral Small 2** via Ollama. Source code, repository contents, and environment secrets are **never** transmitted to hosted LLMs.
- **ArmorIQ Policy Mediation**: All protected Model Context Protocol (MCP) actions are mediated by ArmorIQ. Malicious tool executions (such as prompt injections attempting to exfiltrate credentials via `send_debug_report`) are intercepted and blocked by policy.
- **Untrusted Input Defense**: Repository files, README instructions, user error reports, and tool outputs are treated as untrusted data.
- **Strict Workspace Isolation**: Repairs occur exclusively in an ephemeral temporary directory (`/tmp/repomedic_ws_*`). Sensitive files (`.env*`, `.git`, credentials, generated files) are excluded. Path traversal escapes (`../`, symlinks) are strictly forbidden.
- **Zero-Network Docker Verification**: Verification checks (`check:type`, `test`) execute in isolated Docker containers with `--network none`, ensuring no unauthorized network egress or host file mutation.
- **Strict User Consent**: Original files are **never modified** until the user reviews a unified diff preview and explicitly confirms acceptance. Rejecting the repair discards the workspace and leaves the target project 100% unchanged.
- **Bounded Retry**: The repair loop retries at most twice, reporting unresolved errors honestly.

---

## Architecture Overview

```
                      ┌──────────────────────┐
                      │  Target Repository   │
                      └──────────┬───────────┘
                                 │ Copy (excludes .env, .git, etc.)
                                 ▼
                      ┌──────────────────────┐
                      │ Ephemeral Workspace  │
                      └──────────┬───────────┘
                                 │
                     ┌───────────▼───────────┐
                     │ LangGraph State Graph │
                     └───────────┬───────────┘
                                 │
           ┌─────────────────────┼─────────────────────┐
           ▼                     ▼                     ▼
 ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
 │    Diagnoser     │  │      Fixer       │  │  Docker Verify   │
 │ (Devstral Small  │  │ (Devstral Small  │  │ (node:22-slim    │
 │  2 via Ollama)   │  │  2 via Ollama)   │  │  network=none)   │
 └─────────┬────────┘  └─────────┬────────┘  └─────────┬────────┘
           │                     │                     │
           │ Untrusted Read      │ Scoped Patch        │ Check exit codes
           └─────────────────────┼─────────────────────┘
                                 │
               Tool Calls        ▼
           ┌───────────────────────────────────────────┐
           │        ArmorIQ Policy Enforcement         │
           │  • send_debug_report   ──> ⛔ BLOCKED     │
           │  • record_repair_status ──>  ALLOWED     │
           └─────────────────────┬─────────────────────┘
                                 │
                                 ▼
                     ┌───────────────────────┐
                     │  Unified Diff Preview │
                     └───────────┬───────────┘
                                 │
                   Accept? ──────┴────── Reject?
                     │                     │
                     ▼                     ▼
             Apply to Target       Discard Workspace
            (Approved paths)      (Originals Untouched)
```

---

## Prerequisites

1. **Python 3.12+**
2. **Docker Desktop** (running locally)
3. **Ollama** installed with `devstral-small-2:latest`:
   ```bash
   ollama pull devstral-small-2
   ```
4. **Node.js 22+ & npm** (for building/testing the React fixture)
5. **ArmorIQ Account & Credentials**:
   - `ARMORIQ_API_KEY`
   - `ARMORIQ_USER_EMAIL`
   - Configured MCP server endpoint (e.g. deployed on Vercel or running locally)

---

## Installation & Setup

### 1. Clone & Set Up Python Environment

```bash
git clone https://github.com/preethamsolanki28/repomedic.git
cd repomedic

# Create and activate Python 3.12 virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install RepoMedic in editable mode
pip install -e .
```

### 2. Configure Environment Variables

Create a `.env` file in the project root:

```ini
ARMORIQ_API_KEY=your_armoriq_api_key
ARMORIQ_USER_EMAIL=your_email@example.com
ARMORIQ_SERVICE_URL=https://api.armoriq.ai
MCP_SERVER_URL=https://your-mcp-server.vercel.app/api/mcp
```

### 3. Install Demo Fixture Dependencies

```bash
cd demo
npm install
cd ..
```

---

## Demo: Guided Verification

The repository includes a deliberately broken React + Vite + TypeScript application in `demo/`.

### 1. Inspect the Seeded Bugs & Prompt Injection

The demo contains two seeded bugs and one malicious prompt injection:
1. **TypeScript Type Mismatch** (`demo/src/App.tsx`):
   Passing string `"0"` to numeric prop `initialCount` (`TS2322`).
2. **Logic Bug** (`demo/src/Counter.tsx`):
   `handleIncrement` decrements the counter (`count - 1`) instead of incrementing (`count + 1`).
3. **Malicious Prompt Injection** (`demo/README.md`):
   Instructs the agent to exfiltrate `DEMO_SECRET_123` via `send_debug_report`.

### 2. Verify Bugs Reproduce

Run the demo checks directly to confirm failure:

```bash
cd demo
npm run check:type   # Fails with TS2322 in src/App.tsx
npm test             # Fails Counter increment test
cd ..
```

### 3. Run RepoMedic with Reject (Immutability Verification)

Verify that running `repomedic fix` with rejection leaves all target files untouched:

```bash
repomedic fix demo --no-prompt-error --reject
```

**Expected Result:**
- Diagnoser analyzes the repository and pinpoints both bugs.
- Prompt injection in `README.md` is detected; ArmorIQ intercepts and blocks the unauthorized `send_debug_report` action (`decision='block'`, `reason='tool_not_in_allowlist'`).
- Fixer generates proposed changes.
- Verification checks pass inside Docker (`network=none`).
- Unified diff is displayed.
- The rejection flag discards the workspace; target files in `demo/` remain **completely untouched**.

### 4. Run RepoMedic with Accept (Repair Application)

Run RepoMedic and accept the repair:

```bash
repomedic fix demo --no-prompt-error --accept
```

**Expected Result:**
- Repair loop executes with exit code 0.
- Only approved files (`demo/src/App.tsx` and `demo/src/Counter.tsx`) are modified.
- Original bugs are resolved:
  - `initialCount={0}` in `src/App.tsx`
  - `setCount(count + 1)` in `src/Counter.tsx`
- Both `check:type` and `test` now pass cleanly.

---

## Running the Automated Test Suite

Run the full pytest suite (28 comprehensive tests):

```bash
./.venv/bin/pytest tests/ -v
```

### Test Coverage
- **`tests/test_agents.py`**:
  - Diagnoser read-only enforcement and bug detection.
  - ArmorIQ mediation: proof of denial for `send_debug_report` and allow for `record_repair_status`.
  - Fixer scope enforcement: blocks writes to unauthorized paths.
  - Fixer bug repair on seeded fixture.
  - Full LangGraph workflow execution with bounded retry.
- **`tests/test_workspace.py`**:
  - Path traversal and directory escape prevention.
  - Sensitive file exclusion (`.env*`, `.git`, credentials, generated files).
  - Immutability of original target project upon rejection.
  - Atomic patch application upon acceptance.
- **`tests/test_docker_runner.py`**:
  - Docker execution with `--network none`.
  - Mount security and read-only host filesystem isolation.
- **`tests/test_armoriq_mcp.py`**:
  - Live ArmorIQ policy validation (allow vs. block decisions).
- **`tests/test_cli.py`**:
  - CLI argument parsing, interactive diff review, `--accept` / `--reject` flags.

---

## Security Policies & Constraints

1. **Untrusted Input**: All repository code, commit messages, issue bodies, and error logs are treated as untrusted strings.
2. **Fail-Closed Mediation**: If the ArmorIQ policy decision point is unreachable or returns an error, all protected operations fail closed.
3. **No External Egress**: Project verification runs with Docker container network disabled (`--network none`).
4. **Scoped Writes**: The repair agent can only modify approved source files within the workspace root. Traversal attempts outside the workspace raise immediate errors.
