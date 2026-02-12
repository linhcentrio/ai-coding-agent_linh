"""
CLI Main Entry Point
=====================
Command-line interface for the AI Coding Agent.
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax

from ..agent.core import CodingAgent, AgentConfig
from ..providers.gemini import GeminiProvider
from ..providers.claude import ClaudeProvider
from ..providers.codex import CodexProvider
from ..tools import registry


console = Console()


def get_provider(provider_name: str, model: Optional[str] = None):
    """Get provider by name."""
    providers = {
        "gemini": (GeminiProvider, "gemini-2.0-flash"),
        "claude": (ClaudeProvider, "claude-sonnet-4-20250514"),
        "codex": (CodexProvider, "gpt-4o"),
        "openai": (CodexProvider, "gpt-4o"),
    }
    
    if provider_name not in providers:
        raise ValueError(f"Unknown provider: {provider_name}")
    
    provider_class, default_model = providers[provider_name]
    return provider_class(model=model or default_model)


async def run_interactive(agent: CodingAgent):
    """Run interactive REPL."""
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import FileHistory
    
    # Create history file
    history_path = Path.home() / ".ai_coding_agent_history"
    session = PromptSession(history=FileHistory(str(history_path)))
    
    console.print(Panel.fit(
        "[bold green]AI Coding Agent[/bold green]\n"
        f"Provider: {agent.provider.provider_type.value} | "
        f"Model: {agent.provider.model}\n"
        f"Tools: {len(registry.list_names())} available\n\n"
        "Type [bold]/help[/bold] for commands, [bold]/quit[/bold] to exit",
        title="🤖 Welcome",
    ))
    
    while True:
        try:
            user_input = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: session.prompt("\n[You] > ")
            )
            
            if not user_input.strip():
                continue
            
            # Handle commands
            if user_input.startswith("/"):
                if await handle_command(user_input, agent):
                    continue
                else:
                    break  # /quit
            
            # Process message
            console.print("\n[Assistant]", style="bold blue")
            
            async for chunk in agent.process_message(user_input):
                console.print(chunk, end="")
            
            console.print()
        
        except KeyboardInterrupt:
            console.print("\n[dim]Interrupted. Type /quit to exit.[/dim]")
            continue
        except EOFError:
            break


async def handle_command(cmd: str, agent: CodingAgent) -> bool:
    """Handle slash commands. Returns False to quit."""
    parts = cmd.strip().split(maxsplit=1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    
    if command in ("/quit", "/exit", "/q"):
        console.print("[dim]Goodbye![/dim]")
        return False
    
    elif command == "/help":
        console.print(Panel(
            "[bold]/help[/bold] - Show this help\n"
            "[bold]/quit[/bold] - Exit the agent\n"
            "[bold]/reset[/bold] - Reset conversation\n"
            "[bold]/tools[/bold] - List available tools\n"
            "[bold]/model[/bold] - Show current model\n"
            "[bold]/history[/bold] - Show conversation history count",
            title="Commands",
        ))
    
    elif command == "/reset":
        agent.reset()
        console.print("[green]Conversation reset.[/green]")
    
    elif command == "/tools":
        tools = registry.list_all()
        for tool in tools:
            console.print(f"• [bold]{tool.name}[/bold] ({tool.category.value}): {tool.description[:60]}...")
    
    elif command == "/model":
        console.print(f"Provider: {agent.provider.provider_type.value}")
        console.print(f"Model: {agent.provider.model}")
    
    elif command == "/history":
        count = len(agent.state.messages)
        console.print(f"Messages in history: {count}")
    
    else:
        console.print(f"[red]Unknown command: {command}[/red]")
    
    return True


async def run_single_command(agent: CodingAgent, command: str):
    """Run a single command and exit."""
    async for chunk in agent.process_message(command):
        console.print(chunk, end="")
    console.print()


@click.command()
@click.option(
    "-p", "--provider",
    type=click.Choice(["gemini", "claude", "codex", "openai"]),
    default="gemini",
    help="LLM provider to use",
)
@click.option(
    "-m", "--model",
    type=str,
    default=None,
    help="Model name (optional, provider has defaults)",
)
@click.option(
    "-c", "--command",
    type=str,
    default=None,
    help="Run a single command and exit",
)
@click.option(
    "--no-confirm",
    is_flag=True,
    help="Disable confirmation for dangerous tools",
)
def main(provider: str, model: Optional[str], command: Optional[str], no_confirm: bool):
    """AI Coding Agent - Multi-provider coding assistant."""
    try:
        llm_provider = get_provider(provider, model)
    except Exception as e:
        console.print(f"[red]Error initializing provider: {e}[/red]")
        sys.exit(1)
    
    config = AgentConfig(
        confirm_dangerous_tools=not no_confirm,
    )
    
    agent = CodingAgent(provider=llm_provider, config=config)
    
    if command:
        asyncio.run(run_single_command(agent, command))
    else:
        asyncio.run(run_interactive(agent))


if __name__ == "__main__":
    main()
