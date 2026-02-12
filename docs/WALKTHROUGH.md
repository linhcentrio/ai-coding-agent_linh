# AI Coding Agent - Walkthrough

## All Phases Complete ✅

| Phase | Status | Files |
|-------|--------|-------|
| MVP | ✅ | 17 files |
| Orchestration | ✅ | 6 files |
| Browser Testing | ✅ | 6 files |
| **Total** | **✅** | **31 files** |

## Project Structure

```
ai-coding-agent/
├── config/
│   ├── default.yaml
│   └── workflows/ (5 YAML workflows)
├── src/ai_coding_agent/
│   ├── agent/       (core.py, session.py)
│   ├── orchestrator/ (async_executor.py, workflow.py)
│   ├── providers/   (base, gemini, claude, codex)
│   ├── tools/       (registry, file, edit, exec, search)
│   ├── testing/     (browser, network_inspector, assertions...)
│   └── cli/         (main.py, workflow_cli.py)
```

## Key Features

| Component | Capabilities |
|-----------|-------------|
| **Providers** | Gemini, Claude, Codex (OAuth) - async streaming |
| **Tools** | 17 tools (file, edit, exec, search, browser) |
| **Orchestration** | Sequential, Parallel, Round-Robin, Continuous |
| **Testing** | Playwright, CDP Network, Assertions |

## Quick Start

```bash
cd ai-coding-agent
pip install -e .
set GEMINI_API_KEY=your_key
aca
```

## Usage Examples

```bash
# Interactive agent
aca -p gemini

# Run workflow
aca workflow run code_review "..."

# Browser test
python -c "from ai_coding_agent.testing import TestWorkflowRunner; ..."
```
