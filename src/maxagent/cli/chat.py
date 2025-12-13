"""Chat command implementation"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import typer
from rich.console import Console
from rich.markup import escape
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from maxagent.config import load_config
from maxagent.core import create_agent, create_thinking_selector
from maxagent.llm import Message
from maxagent.tools import ToolResult, create_full_registry
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


def _truncate_value(value: str, max_len: int = 120) -> str:
    if len(value) <= max_len:
        return value
    return value[: max_len - 3] + "..."


def _one_line(value: object, *, max_len: int = 120) -> str:
    text = str(value) if value is not None else ""
    text = " ".join(text.split())
    return _truncate_value(text, max_len=max_len)


def _summarize_tool_args(name: str, args: str) -> str:
    """Create a compact, human-readable arg summary for common tools."""
    try:
        parsed = json.loads(args) if args else {}
    except Exception:
        return _truncate_value(args)

    if not isinstance(parsed, dict):
        return _truncate_value(str(parsed))

    # Tool-specific summaries
    if name in {"read_file", "write_file"}:
        path = parsed.get("path") or parsed.get("file_path")
        if path:
            return f"path={path}"
    if name == "edit":
        fp = parsed.get("file_path") or parsed.get("path")
        if fp:
            return f"file_path={fp}"
    if name == "todowrite":
        todos = parsed.get("todos", [])
        if isinstance(todos, list):
            titles: list[str] = []
            for t in todos:
                if isinstance(t, dict):
                    title = t.get("content") or t.get("id")
                    if title:
                        titles.append(str(title))
            if titles:
                preview = "; ".join(titles[:3])
                more = f" (+{len(titles)-3} more)" if len(titles) > 3 else ""
                return f"todos={len(titles)} [{preview}{more}]"

    # Generic key highlights
    highlights: list[str] = []
    for key in ("path", "file_path", "pattern", "command", "query", "url", "name"):
        if key in parsed:
            highlights.append(f"{key}={parsed[key]}")
    if highlights:
        return ", ".join(highlights)

    return _truncate_value(json.dumps(parsed, ensure_ascii=False))


def _make_tool_callback() -> callable:
    """Factory for verbose tool callback with request grouping."""
    last_request_id: Optional[int] = None

    def _tool_callback(name: str, args: str, result: ToolResult, request_id: int) -> None:
        nonlocal last_request_id
        if request_id != last_request_id:
            console.print(f"[dim]── Request {request_id} ──[/dim]")
            last_request_id = request_id
        status = "[green]OK[/green]" if result.success else "[red]FAILED[/red]"

        if name == "todowrite":
            try:
                parsed = json.loads(args) if args else {}
            except Exception:
                parsed = {}

            todos = parsed.get("todos") if isinstance(parsed, dict) else None
            if isinstance(todos, list) and todos:
                console.print(
                    f"[dim]Tool(req {request_id}): {name} todos={len(todos)} {status}[/dim]"
                )

                status_icons = {
                    "pending": "⏳",
                    "in_progress": "🔄",
                    "completed": "✅",
                    "cancelled": "❌",
                }
                max_show = 20
                for todo in todos[:max_show]:
                    if not isinstance(todo, dict):
                        continue
                    todo_id = _one_line(todo.get("id", ""), max_len=64)
                    content = _one_line(todo.get("content", ""), max_len=200)
                    todo_status = _one_line(todo.get("status", "pending"), max_len=32) or "pending"
                    priority = _one_line(todo.get("priority", ""), max_len=32)
                    file_path = _one_line(todo.get("file_path", ""), max_len=120)

                    icon = status_icons.get(todo_status, "")
                    marker = ">>" if todo_status == "in_progress" else "  "

                    line = f"{marker} {icon} {todo_status} [{todo_id}] {content}"
                    if priority:
                        line += f" ({priority})"
                    if file_path:
                        line += f" -> {file_path}"
                    console.print(line, style="dim", markup=False)

                if len(todos) > max_show:
                    console.print(
                        f"  ... (+{len(todos) - max_show} more)",
                        style="dim",
                        markup=False,
                    )
                return

        summary = escape(_summarize_tool_args(name, args))
        summary_part = f" {summary}" if summary else ""
        console.print(f"[dim]Tool(req {request_id}): {name}{summary_part} {status}[/dim]")

    return _tool_callback


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


def _make_request_end_callback() -> callable:
    """Factory for printing context stats after each LLM request."""

    def _on_request_end(request_id: int, stats: dict, *_: object) -> None:
        try:
            current_tokens = stats.get("current_tokens", 0)
            max_tokens = stats.get("max_tokens", 0)
            usage_percent = stats.get("usage_percent", 0)
            messages_count = stats.get("messages_count", 0)
            remaining = stats.get("remaining_tokens", 0)
            model = stats.get("model")
            elapsed_s = stats.get("elapsed_s")
            elapsed_part = f", time={elapsed_s:.2f}s" if isinstance(elapsed_s, (int, float)) else ""
            console.print(
                f"[dim]Context(req {request_id}): "
                f"{current_tokens}/{max_tokens} tokens ({usage_percent:.1f}%), "
                f"msgs={messages_count}, remaining={remaining}"
                + (f", model={model}" if model else "")
                + elapsed_part
                + "[/dim]"
            )
        except Exception:
            console.print(f"[dim]Context(req {request_id}): {stats}[/dim]")

    return _on_request_end


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
    # YOLO mode - dangerous but powerful
    yolo: bool = typer.Option(
        False, "--yolo", help="YOLO mode: allow reading/writing files anywhere on the system"
    ),
    # Debug context - show context token usage
    debug_context: bool = typer.Option(
        False, "--debug-context", "-dc", help="Show context token usage before each API call"
    ),
    # Max iterations for tool calls
    max_iterations: Optional[int] = typer.Option(
        None, "--max-iterations", "-i", help="Maximum tool call iterations (default: from config)"
    ),
    tool_planner: Optional[bool] = typer.Option(
        None,
        "--tool-planner/--no-tool-planner",
        help="Enable/disable agent-side tool planner to batch independent tool calls",
    ),
) -> None:
    """
    Chat with the AI assistant.

    Examples:
        llc chat "Explain this code"
        llc chat --think "Analyze this complex algorithm"
        llc chat --thinking-mode=auto "Design a solution"
        llc chat -p "What is Python?" | jq  # Pipe mode with JSONL output
        llc chat --yolo "Read ~/some/file.txt"  # YOLO mode for unrestricted access
        llc chat --debug-context "Research this topic"  # Show context usage
        llc chat --max-iterations 50 "Complex task"  # Limit tool iterations
        llc chat  # Enter REPL mode
    """
    # Get global options from context
    global_opts = ctx.obj or {}
    effective_model = model or global_opts.get("model")
    effective_project = project or global_opts.get("project")
    effective_yolo = yolo or global_opts.get("yolo", False)
    effective_debug_context = debug_context or global_opts.get("debug_context", False)
    effective_max_iterations = max_iterations or global_opts.get("max_iterations")
    effective_tool_planner = (
        tool_planner if tool_planner is not None else global_opts.get("tool_planner")
    )

    if message:
        # Single message mode
        asyncio.run(
            _single_chat(
                message,
                effective_model,
                no_tools,
                effective_project,
                think,
                thinking_mode,
                pipe,
                effective_yolo,
                effective_debug_context,
                effective_max_iterations,
                effective_tool_planner,
            )
        )
    else:
        if pipe:
            # Pipe mode requires a message
            error_output = {"type": "error", "message": "Pipe mode requires a message argument"}
            print(json.dumps(error_output, ensure_ascii=False))
            raise typer.Exit(1)
        # REPL mode
        asyncio.run(
            _repl_mode(
                effective_model,
                no_tools,
                no_history,
                effective_project,
                think,
                thinking_mode,
                effective_yolo,
                effective_debug_context,
                effective_max_iterations,
                effective_tool_planner,
            )
        )


async def _single_chat(
    message: str,
    model: Optional[str],
    no_tools: bool,
    project: Optional[Path],
    think: Optional[bool] = None,
    thinking_mode: Optional[str] = None,
    pipe: bool = False,
    yolo: bool = False,
    debug_context: bool = False,
    max_iterations: Optional[int] = None,
    tool_planner: Optional[bool] = None,
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

        # Enable/disable tool planner if overridden from CLI
        if tool_planner is not None:
            config.model.enable_tool_planner = tool_planner

        # Disable tools if requested
        if no_tools:
            config.tools.enabled = []

        project_root = project or Path.cwd()

        # Choose callback based on mode
        tool_callback = _tool_callback_jsonl if pipe else _make_tool_callback()
        request_end_callback = None if pipe else _make_request_end_callback()

        # Show YOLO mode warning
        if yolo and not pipe:
            print_info("[YOLO mode] File access restrictions disabled")

        # Create shared LLM client and tool registry (native + MCP + SubAgent)
        from maxagent.llm import create_llm_client

        # Pass model_override to enable auto provider selection
        llm_client = create_llm_client(config, model_override=model if model else None)

        # Display actual model and base_url being used
        if not pipe:
            actual_model = llm_client.config.model
            actual_base_url = getattr(
                llm_client.config, "base_url", "https://api.githubcopilot.com"
            )
            print_dim(f"[Model: {actual_model} | URL: {actual_base_url}]")

        tool_registry = await create_full_registry(
            project_root,
            config=config,
            llm_client=llm_client,
            allow_outside_project=yolo,
            load_mcp=not no_tools,
            enable_subagent=not no_tools,
            trace_subagents=not pipe,
        )

        # Single chat mode: interactive_mode=False (auto-execute, no confirmation)
        # User cannot interact in single message mode, so LLM should execute directly
        agent = create_agent(
            config=config,
            project_root=project_root,
            llm_client=llm_client,
            tool_registry=tool_registry,
            on_tool_call=tool_callback,
            on_request_end=request_end_callback,
            yolo_mode=yolo,
            debug_context=debug_context,
            max_iterations=max_iterations,
            interactive_mode=False,  # Single chat = headless, execute directly
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
    yolo: bool = False,
    debug_context: bool = False,
    max_iterations: Optional[int] = None,
    tool_planner: Optional[bool] = None,
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
    console.print("  /context - Show context token usage")
    console.print("[dim]Model commands:[/dim]")
    console.print("  /model        - Show current model")
    console.print("  /model <name> - Switch to specified model")
    console.print("  /models       - List available models")
    console.print()

    # Show YOLO mode warning
    if yolo:
        console.print(
            "[bold yellow]Warning: YOLO mode enabled - file access restrictions disabled[/bold yellow]"
        )
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

        if tool_planner is not None:
            config.model.enable_tool_planner = tool_planner

        if no_tools:
            config.tools.enabled = []

        project_root = project or Path.cwd()

        # Create shared LLM client and tool registry (native + MCP + SubAgent)
        from maxagent.llm import create_llm_client

        # Pass model_override to enable auto provider selection
        llm_client = create_llm_client(config, model_override=model if model else None)
        tool_registry = await create_full_registry(
            project_root,
            config=config,
            llm_client=llm_client,
            allow_outside_project=yolo,
            load_mcp=not no_tools,
            enable_subagent=not no_tools,
            trace_subagents=True,
        )

        agent = create_agent(
            config=config,
            project_root=project_root,
            llm_client=llm_client,
            tool_registry=tool_registry,
            on_tool_call=_make_tool_callback(),
            on_request_end=_make_request_end_callback(),
            yolo_mode=yolo,
            debug_context=debug_context,
            max_iterations=max_iterations,
            interactive_mode=True,  # REPL mode = interactive, ask for confirmation
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

                # Context statistics command
                if user_input.lower() == "/context":
                    agent.display_context_status(detailed=True)
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
