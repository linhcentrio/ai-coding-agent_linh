# AI Coding Agent

Multi-provider AI coding agent supporting **Gemini**, **OpenAI Codex**, and **Claude**.

## Features

- 🤖 **Multi-Provider**: Gemini, Codex (OAuth), Claude
- 🔄 **Agent Orchestration**: Sequential, Parallel, Round-Robin modes
- 🛠️ **30+ Built-in Tools**: File, Edit, Exec, Search, Git
- 💻 **Rich CLI**: Interactive REPL with syntax highlighting
- 🧪 **Browser Testing**: Playwright + CDP Network Inspector

## Quick Start

```bash
# Install
pip install -e .

# Configure API keys
cp config/default.yaml config/local.yaml
# Edit config/local.yaml with your API keys

# Run
aca
```

## Project Structure

```
ai-coding-agent/
├── src/ai_coding_agent/
│   ├── agent/          # Core agent loop
│   ├── providers/      # LLM providers
│   ├── tools/          # Built-in tools
│   ├── cli/            # CLI interface
│   └── config/         # Configuration
├── config/             # Config files
├── tests/              # Test suite
└── pyproject.toml
```

## Usage

```bash
# Interactive mode
aca

# Single command
aca -c "Create a Python function to sort a list"

# With specific provider
aca --provider gemini
```

## License

MIT
