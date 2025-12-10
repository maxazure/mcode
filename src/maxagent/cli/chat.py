"""Chat command implementation"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from maxagent.config import load_config
from maxagent.core import create_agent, create_thinking_selector
from maxagent.llm import Message
from maxagent.tools import ToolResult, create_registry_with_mcp
from maxagent.utils.console import print_dim, print_error, print_info
from maxagent.utils.thinking import display_thinking, ThinkingResult
from maxagent.utils.tokens import get_token_tracker, reset_token_tracker

if TYPE_CHECKING:
    from maxagent.core import Agent

app = typer.Typer(
    help="Chat with AI assistant",
    context_settings={"help_option_names": ["-h", "--help"]},
)
console = Console()


def _tool_callback(name: str, args: str, result: ToolResult) -> None:
    """Callback to display tool usage"""
    status = "[green]OK[/green]" if result.success else "[red]FAILED[/red]"
    console.print(f"[dim]Tool: {name} {status}[/dim]")


def _tool_callback_jsonl(name: str, args: str, result: ToolResult) -> None:
    """Callback to output tool usage in JSONL format"""
    output = {
        "type": "tool_call",
        "tool": name,
        "arguments": args,
        "success": result.success,
        "output": result.output,
        "error": result.error,
    }
    print(json.dumps(output, ensure_ascii=False), flush=True)


@app.callback(invoke_without_command=True)
def chat(
    ctx: typer.Context,
    message: Optional[str] = typer.Argument(None, help="Message to send"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override model"),
    no_tools: bool = typer.Option(False, "--no-tools", help="Disable tool usage"),
    no_history: bool = typer.Option(False, "--no-history", help="Don't save history"),
    project: Optional[Path] = typer.Option(None, "--project", help="Project directory"),
    # Pipe mode for programmatic usage
    pipe: bool = typer.Option(
        False, "--pipe", "-p", help="Pipe mode: output JSONL for programmatic use"
    ),
    # Thinking options
    think: Optional[bool] = typer.Option(
        None, "--think/--no-think", help="Enable/disable deep thinking mode (overrides config)"
    ),
    thinking_mode: Optional[str] = typer.Option(
        None, "--thinking-mode", "-t", help="Thinking mode: auto, enabled, disabled"
    ),
) -> None:
    """
    Chat with the AI assistant.

    Examples:
        llc chat "Explain this code"
        llc chat --think "Analyze this complex algorithm"
        llc chat --thinking-mode=auto "Design a solution"
        llc chat -p "What is Python?" | jq  # Pipe mode with JSONL output
        llc chat  # Enter REPL mode
    """
    if message:
        # Single message mode
        asyncio.run(_single_chat(message, model, no_tools, project, think, thinking_mode, pipe))
    else:
        if pipe:
            # Pipe mode requires a message
            error_output = {"type": "error", "message": "Pipe mode requires a message argument"}
            print(json.dumps(error_output, ensure_ascii=False))
            raise typer.Exit(1)
        # REPL mode
        asyncio.run(_repl_mode(model, no_tools, no_history, project, think, thinking_mode))


async def _single_chat(
    message: str,
    model: Optional[str],
    no_tools: bool,
    project: Optional[Path],
    think: Optional[bool] = None,
    thinking_mode: Optional[str] = None,
    pipe: bool = False,
) -> None:
    """Handle single message chat"""
    try:
        config = load_config(project)

        # Determine thinking strategy
        if think is True:
            strategy = "enabled"
        elif think is False:
            strategy = "disabled"
        elif thinking_mode:
            strategy = thinking_mode
        else:
            strategy = config.model.thinking_strategy

        # Create thinking selector
        thinking_selector = create_thinking_selector(strategy)

        # Check if thinking should be used
        use_thinking = thinking_selector.should_use_thinking(message)

        # Select model based on thinking decision
        if use_thinking:
            effective_model = model or config.model.thinking_model
            if not pipe:
                print_dim(f"[Thinking mode: {effective_model}]")
        else:
            effective_model = model or config.model.default

        config.model.default = effective_model

        # Disable tools if requested
        if no_tools:
            config.tools.enabled = []

        project_root = project or Path.cwd()

        # Choose callback based on mode
        tool_callback = _tool_callback_jsonl if pipe else _tool_callback

        # Create tool registry with MCP tools
        tool_registry = await create_registry_with_mcp(project_root, load_mcp=not no_tools)

        agent = create_agent(
            config=config,
            project_root=project_root,
            tool_registry=tool_registry,
            on_tool_call=tool_callback,
        )

        if pipe:
            # Pipe mode: no status indicator
            response = await agent.run(message)
            _output_jsonl(response, agent)
        else:
            # Normal mode: with status indicator
            with console.status("[bold green]Thinking...[/bold green]"):
                response = await agent.run(message)
            # Display response with thinking support and token usage
            _display_response(response, config.model.show_thinking, agent)

    except Exception as e:
        if pipe:
            error_output = {"type": "error", "message": str(e)}
            print(json.dumps(error_output, ensure_ascii=False))
        else:
            print_error(str(e))
        raise typer.Exit(1)


def _output_jsonl(response: str, agent: "Agent") -> None:
    """Output response in JSONL format for pipe mode"""
    usage = agent.get_last_usage()

    output = {
        "type": "response",
        "content": response,
        "model": agent.llm.config.model,
    }

    if usage:
        output["usage"] = {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
        }
        # Calculate cost using the private method
        cost = agent.token_tracker._calculate_cost(usage, agent.llm.config.model)
        output["cost_usd"] = cost

    print(json.dumps(output, ensure_ascii=False), flush=True)


async def _repl_mode(
    model: Optional[str],
    no_tools: bool,
    no_history: bool,
    project: Optional[Path],
    think: Optional[bool] = None,
    thinking_mode: Optional[str] = None,
) -> None:
    """Interactive REPL mode"""
    console.print("[bold green]MaxAgent Chat Mode[/bold green]")
    console.print("Type 'exit' or press Ctrl+C to quit")
    console.print("Type 'clear' to clear history")
    console.print()
    console.print("[dim]Thinking commands:[/dim]")
    console.print("  /think  - Enable deep thinking mode")
    console.print("  /quick  - Disable thinking (fast mode)")
    console.print("  /auto   - Auto thinking mode")
    console.print("  /mode   - Show current thinking mode")
    console.print("  /tokens - Show token usage statistics")
    console.print("[dim]Model commands:[/dim]")
    console.print("  /model        - Show current model")
    console.print("  /model <name> - Switch to specified model")
    console.print("  /models       - List available models")
    console.print()

    try:
        config = load_config(project)

        # Initialize thinking strategy
        if think is True:
            current_strategy = "enabled"
        elif think is False:
            current_strategy = "disabled"
        elif thinking_mode:
            current_strategy = thinking_mode
        else:
            current_strategy = config.model.thinking_strategy

        if model:
            config.model.default = model

        if no_tools:
            config.tools.enabled = []

        project_root = project or Path.cwd()

        # Create tool registry with MCP tools
        tool_registry = await create_registry_with_mcp(project_root, load_mcp=not no_tools)

        agent = create_agent(
            config=config,
            project_root=project_root,
            tool_registry=tool_registry,
            on_tool_call=_tool_callback,
        )

        history: list[Message] = []
        show_thinking = config.model.show_thinking

        while True:
            try:
                # Show current mode in prompt if not auto
                if current_strategy == "enabled":
                    prompt_text = "[bold blue]You[/bold blue] [cyan](think)[/cyan]"
                elif current_strategy == "disabled":
                    prompt_text = "[bold blue]You[/bold blue] [yellow](quick)[/yellow]"
                else:
                    prompt_text = "[bold blue]You[/bold blue]"

                user_input = Prompt.ask(prompt_text)

                if not user_input.strip():
                    continue

                # Exit commands
                if user_input.lower() in ("exit", "quit", "q"):
                    print_dim("Goodbye!")
                    break

                # History commands
                if user_input.lower() == "clear":
                    history = []
                    agent.clear_history()
                    print_info("History cleared")
                    continue

                if user_input.lower() == "history":
                    console.print(f"[dim]History: {len(history)} messages[/dim]")
                    continue

                # Thinking mode commands
                if user_input.lower() == "/think":
                    current_strategy = "enabled"
                    print_info("Deep thinking mode enabled")
                    continue

                if user_input.lower() == "/quick":
                    current_strategy = "disabled"
                    print_info("Quick mode enabled (no thinking)")
                    continue

                if user_input.lower() == "/auto":
                    current_strategy = "auto"
                    print_info("Auto thinking mode enabled")
                    continue

                if user_input.lower() == "/mode":
                    print_info(f"Current thinking mode: {current_strategy}")
                    continue

                if user_input.lower() == "/thinking on":
                    show_thinking = True
                    print_info("Thinking display enabled")
                    continue

                if user_input.lower() == "/thinking off":
                    show_thinking = False
                    print_info("Thinking display disabled")
                    continue

                # Token statistics command
                if user_input.lower() == "/tokens":
                    agent.token_tracker.display(console)
                    continue

                # Model commands
                if user_input.lower() == "/model":
                    print_info(f"Current model: {agent.llm.config.model}")
                    continue

                if user_input.lower() == "/models":
                    console.print("[bold]Available models:[/bold]")
                    for m in config.model.available_models:
                        marker = " [green]*[/green]" if m == agent.llm.config.model else ""
                        console.print(f"  {m}{marker}")
                    continue

                if user_input.lower().startswith("/model "):
                    new_model = user_input[7:].strip()
                    if new_model:
                        agent.llm.config.model = new_model
                        config.model.default = new_model
                        print_info(f"Switched to model: {new_model}")
                    continue

                # Create thinking selector for this message
                thinking_selector = create_thinking_selector(current_strategy)
                use_thinking = thinking_selector.should_use_thinking(user_input)

                # Select model
                if use_thinking:
                    effective_model = config.model.thinking_model
                    print_dim(f"[Using: {effective_model}]")
                    # Temporarily override model
                    original_model = agent.llm.config.model
                    agent.llm.config.model = effective_model
                else:
                    original_model = None

                # Run agent
                with console.status("[bold green]Thinking...[/bold green]"):
                    response = await agent.chat(
                        message=user_input,
                        history=None if no_history else history,
                    )

                # Restore original model if changed
                if original_model:
                    agent.llm.config.model = original_model

                # Display response with thinking support and token usage
                _display_response(response, show_thinking, agent)

                # Update history
                if not no_history:
                    history = agent.get_history()

            except KeyboardInterrupt:
                console.print()
                print_dim("Goodbye!")
                break

    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


def _display_response(
    response: str, show_thinking: bool = True, agent: Optional["Agent"] = None
) -> None:
    """Display response with optional thinking content and token usage

    Args:
        response: Response string (may contain thinking content from agent)
        show_thinking: Whether to display thinking content
        agent: Optional agent to get token usage from
    """
    # Display the response
    console.print(
        Panel(
            Markdown(response),
            title="[bold green]Assistant[/bold green]",
            border_style="green",
        )
    )

    # Display token usage if agent is provided
    if agent:
        usage = agent.get_last_usage()
        if usage and usage.total_tokens > 0:
            tracker = agent.token_tracker
            console.print(tracker.format_last(usage, agent.llm.config.model))


if __name__ == "__main__":
    app()
