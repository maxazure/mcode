"""Test command - Testing framework detection, test generation, and execution"""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich.syntax import Syntax
from rich.table import Table

from maxagent.config import load_config
from maxagent.utils.console import console

app = typer.Typer(
    help="Testing framework detection, test generation, and execution",
    context_settings={"help_option_names": ["-h", "--help"]},
)


class TestFramework(str, Enum):
    """Supported testing frameworks"""

    PYTEST = "pytest"
    UNITTEST = "unittest"
    JEST = "jest"
    VITEST = "vitest"
    MOCHA = "mocha"
    GO_TEST = "go_test"
    CARGO_TEST = "cargo_test"
    UNKNOWN = "unknown"


@dataclass
class TestFrameworkInfo:
    """Information about detected test framework"""

    framework: TestFramework
    config_file: Optional[Path] = None
    test_dir: Optional[Path] = None
    run_command: str = ""
    description: str = ""


def detect_test_framework(project_root: Path) -> TestFrameworkInfo:
    """
    Detect the testing framework used in the project.

    Args:
        project_root: Project root directory

    Returns:
        TestFrameworkInfo with detected framework details
    """
    # Check for Python testing frameworks
    pyproject = project_root / "pyproject.toml"
    setup_py = project_root / "setup.py"
    pytest_ini = project_root / "pytest.ini"
    setup_cfg = project_root / "setup.cfg"

    # Check for pytest
    if pytest_ini.exists():
        return TestFrameworkInfo(
            framework=TestFramework.PYTEST,
            config_file=pytest_ini,
            test_dir=_find_test_dir(project_root, ["tests", "test"]),
            run_command="pytest",
            description="pytest - Python testing framework",
        )

    if pyproject.exists():
        content = pyproject.read_text()
        if "pytest" in content or "[tool.pytest" in content:
            return TestFrameworkInfo(
                framework=TestFramework.PYTEST,
                config_file=pyproject,
                test_dir=_find_test_dir(project_root, ["tests", "test"]),
                run_command="pytest",
                description="pytest - Python testing framework (via pyproject.toml)",
            )

    if setup_cfg.exists():
        content = setup_cfg.read_text()
        if "[tool:pytest]" in content:
            return TestFrameworkInfo(
                framework=TestFramework.PYTEST,
                config_file=setup_cfg,
                test_dir=_find_test_dir(project_root, ["tests", "test"]),
                run_command="pytest",
                description="pytest - Python testing framework (via setup.cfg)",
            )

    # Check for unittest (Python standard library)
    test_dirs = ["tests", "test"]
    for test_dir_name in test_dirs:
        test_dir = project_root / test_dir_name
        if test_dir.exists() and test_dir.is_dir():
            for py_file in test_dir.glob("test_*.py"):
                content = py_file.read_text()
                if "import unittest" in content or "from unittest" in content:
                    return TestFrameworkInfo(
                        framework=TestFramework.UNITTEST,
                        test_dir=test_dir,
                        run_command=f"python -m unittest discover -s {test_dir_name}",
                        description="unittest - Python standard library",
                    )

    # Check for JavaScript/TypeScript testing frameworks
    package_json = project_root / "package.json"
    if package_json.exists():
        content = package_json.read_text()

        # Check for Jest
        if '"jest"' in content or "jest.config" in str(list(project_root.glob("jest.config.*"))):
            jest_config = _find_config_file(
                project_root, ["jest.config.js", "jest.config.ts", "jest.config.json"]
            )
            return TestFrameworkInfo(
                framework=TestFramework.JEST,
                config_file=jest_config,
                test_dir=_find_test_dir(project_root, ["__tests__", "tests", "test"]),
                run_command="npm test" if '"test"' in content else "npx jest",
                description="Jest - JavaScript testing framework",
            )

        # Check for Vitest
        if '"vitest"' in content:
            vitest_config = _find_config_file(
                project_root, ["vitest.config.js", "vitest.config.ts", "vite.config.ts"]
            )
            return TestFrameworkInfo(
                framework=TestFramework.VITEST,
                config_file=vitest_config,
                test_dir=_find_test_dir(project_root, ["tests", "test", "__tests__"]),
                run_command="npx vitest run",
                description="Vitest - Vite-native testing framework",
            )

        # Check for Mocha
        if '"mocha"' in content:
            mocha_config = _find_config_file(
                project_root, [".mocharc.js", ".mocharc.json", ".mocharc.yml"]
            )
            return TestFrameworkInfo(
                framework=TestFramework.MOCHA,
                config_file=mocha_config,
                test_dir=_find_test_dir(project_root, ["test", "tests"]),
                run_command="npm test" if '"test"' in content else "npx mocha",
                description="Mocha - JavaScript testing framework",
            )

    # Check for Go testing
    go_mod = project_root / "go.mod"
    if go_mod.exists():
        # Look for _test.go files
        test_files = list(project_root.rglob("*_test.go"))
        if test_files:
            return TestFrameworkInfo(
                framework=TestFramework.GO_TEST,
                config_file=go_mod,
                test_dir=project_root,
                run_command="go test ./...",
                description="Go test - Go standard testing",
            )

    # Check for Rust/Cargo testing
    cargo_toml = project_root / "Cargo.toml"
    if cargo_toml.exists():
        return TestFrameworkInfo(
            framework=TestFramework.CARGO_TEST,
            config_file=cargo_toml,
            test_dir=project_root / "tests"
            if (project_root / "tests").exists()
            else project_root / "src",
            run_command="cargo test",
            description="Cargo test - Rust testing",
        )

    # Fallback: check if pytest is installed and tests dir exists
    test_dir = _find_test_dir(project_root, ["tests", "test"])
    if test_dir:
        # Assume pytest for Python projects with test directories
        if any(test_dir.glob("*.py")) or any(test_dir.glob("**/*.py")):
            return TestFrameworkInfo(
                framework=TestFramework.PYTEST,
                test_dir=test_dir,
                run_command="pytest",
                description="pytest - Python testing framework (assumed)",
            )

    return TestFrameworkInfo(
        framework=TestFramework.UNKNOWN,
        description="No testing framework detected",
    )


def _find_test_dir(project_root: Path, candidates: list[str]) -> Optional[Path]:
    """Find the test directory from a list of candidates"""
    for name in candidates:
        test_dir = project_root / name
        if test_dir.exists() and test_dir.is_dir():
            return test_dir
    return None


def _find_config_file(project_root: Path, candidates: list[str]) -> Optional[Path]:
    """Find a config file from a list of candidates"""
    for name in candidates:
        config_file = project_root / name
        if config_file.exists():
            return config_file
    return None


@app.callback(invoke_without_command=True)
def test_main(
    ctx: typer.Context,
    file: Optional[str] = typer.Argument(
        None,
        help="File or directory to generate tests for (or run tests on)",
    ),
    detect: bool = typer.Option(
        False,
        "--detect",
        "-d",
        help="Detect testing framework and show info",
    ),
    run: bool = typer.Option(
        False,
        "--run",
        "-r",
        help="Run existing tests",
    ),
    generate: bool = typer.Option(
        False,
        "--generate",
        "-g",
        help="Generate tests for the specified file",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show verbose output",
    ),
    coverage: bool = typer.Option(
        False,
        "--coverage",
        "-c",
        help="Run tests with coverage report",
    ),
    watch: bool = typer.Option(
        False,
        "--watch",
        "-w",
        help="Run tests in watch mode (if supported)",
    ),
):
    """
    Testing framework detection, test generation, and execution.

    This command helps you:

    1. **Detect** testing frameworks used in your project
    2. **Run** existing tests
    3. **Generate** new tests using AI

    Examples:

        # Detect testing framework
        llc test --detect

        # Run all tests
        llc test --run

        # Run tests for a specific file
        llc test --run src/utils.py

        # Generate tests for a file
        llc test --generate src/utils.py

        # Run tests with coverage
        llc test --run --coverage
    """
    # Default: if no options, show detect info
    if not any([detect, run, generate]):
        detect = True

    project_root = Path.cwd()

    if detect:
        _show_framework_info(project_root, verbose)
    elif run:
        asyncio.run(_run_tests(project_root, file, verbose, coverage, watch))
    elif generate:
        if not file:
            console.print("[red]Please specify a file to generate tests for[/]")
            console.print("\nUsage: llc test --generate src/module.py")
            raise typer.Exit(1)
        asyncio.run(_generate_tests(project_root, file, verbose))


def _show_framework_info(project_root: Path, verbose: bool = False) -> None:
    """Show detected testing framework information"""
    info = detect_test_framework(project_root)

    # Create info table
    table = Table(title="Testing Framework Detection", show_header=True, header_style="bold cyan")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Framework", info.framework.value)
    table.add_row("Description", info.description)

    if info.config_file:
        table.add_row("Config File", str(info.config_file.relative_to(project_root)))

    if info.test_dir:
        table.add_row("Test Directory", str(info.test_dir.relative_to(project_root)))

        # Count test files
        if info.framework in [TestFramework.PYTEST, TestFramework.UNITTEST]:
            test_files = list(info.test_dir.rglob("test_*.py")) + list(
                info.test_dir.rglob("*_test.py")
            )
        elif info.framework in [TestFramework.JEST, TestFramework.VITEST, TestFramework.MOCHA]:
            test_files = (
                list(info.test_dir.rglob("*.test.js"))
                + list(info.test_dir.rglob("*.test.ts"))
                + list(info.test_dir.rglob("*.spec.js"))
                + list(info.test_dir.rglob("*.spec.ts"))
            )
        elif info.framework == TestFramework.GO_TEST:
            test_files = list(project_root.rglob("*_test.go"))
        else:
            test_files = []

        table.add_row("Test Files", str(len(test_files)))

    if info.run_command:
        table.add_row("Run Command", f"[green]{info.run_command}[/]")

    console.print()
    console.print(table)
    console.print()

    if info.framework == TestFramework.UNKNOWN:
        console.print("[yellow]No testing framework detected.[/]")
        console.print("\nTo set up testing, you can:")
        console.print("  - For Python: pip install pytest")
        console.print("  - For JavaScript: npm install --save-dev jest")
        console.print("  - For Go: Tests are built-in")
        console.print("  - For Rust: Tests are built-in")
    else:
        console.print("Run tests with: [bold green]llc test --run[/]")
        console.print("Generate tests: [bold blue]llc test --generate <file>[/]")

    if verbose and info.test_dir:
        console.print("\n[bold]Test files found:[/]")
        if info.framework in [TestFramework.PYTEST, TestFramework.UNITTEST]:
            test_files = list(info.test_dir.rglob("test_*.py")) + list(
                info.test_dir.rglob("*_test.py")
            )
        elif info.framework in [TestFramework.JEST, TestFramework.VITEST, TestFramework.MOCHA]:
            test_files = (
                list(info.test_dir.rglob("*.test.js"))
                + list(info.test_dir.rglob("*.test.ts"))
                + list(info.test_dir.rglob("*.spec.js"))
                + list(info.test_dir.rglob("*.spec.ts"))
            )
        elif info.framework == TestFramework.GO_TEST:
            test_files = list(project_root.rglob("*_test.go"))
        else:
            test_files = []

        for tf in test_files[:20]:  # Show first 20
            console.print(f"  - {tf.relative_to(project_root)}")
        if len(test_files) > 20:
            console.print(f"  ... and {len(test_files) - 20} more")


async def _run_tests(
    project_root: Path,
    file: Optional[str],
    verbose: bool,
    coverage: bool,
    watch: bool,
) -> None:
    """Run tests using the detected framework"""
    info = detect_test_framework(project_root)

    if info.framework == TestFramework.UNKNOWN:
        console.print("[red]No testing framework detected.[/]")
        console.print("\nPlease set up a testing framework first.")
        return

    # Build the test command
    cmd = info.run_command

    # Add coverage option
    if coverage:
        if info.framework == TestFramework.PYTEST:
            cmd = "pytest --cov"
        elif info.framework == TestFramework.JEST:
            cmd = cmd.replace("jest", "jest --coverage")
        elif info.framework == TestFramework.VITEST:
            cmd = "npx vitest run --coverage"
        elif info.framework == TestFramework.GO_TEST:
            cmd = "go test -cover ./..."
        elif info.framework == TestFramework.CARGO_TEST:
            # Rust coverage requires additional setup
            console.print(
                "[yellow]Coverage for Rust requires additional setup (cargo-tarpaulin)[/]"
            )

    # Add watch mode
    if watch:
        if info.framework == TestFramework.PYTEST:
            cmd = "pytest-watch" if not coverage else "pytest-watch -- --cov"
        elif info.framework == TestFramework.JEST:
            cmd = cmd.replace("jest", "jest --watch").replace("npm test", "npm test -- --watch")
        elif info.framework == TestFramework.VITEST:
            cmd = "npx vitest"  # Vitest has watch by default
        else:
            console.print(f"[yellow]Watch mode not supported for {info.framework.value}[/]")

    # Add specific file
    if file:
        if info.framework in [TestFramework.PYTEST, TestFramework.UNITTEST]:
            # For pytest, can run specific file or directory
            cmd = f"{cmd} {file}"
        elif info.framework in [TestFramework.JEST, TestFramework.VITEST]:
            cmd = f"{cmd} {file}"
        elif info.framework == TestFramework.GO_TEST:
            # For Go, file must be in the same package
            cmd = f"go test {file}"

    # Add verbose flag
    if verbose:
        if info.framework == TestFramework.PYTEST:
            cmd = f"{cmd} -v"
        elif info.framework == TestFramework.JEST:
            cmd = f"{cmd} --verbose"
        elif info.framework == TestFramework.GO_TEST:
            cmd = f"{cmd} -v"

    console.print(f"\n[bold]Running:[/] [green]{cmd}[/]\n")
    console.print("-" * 60)

    # Run the command
    try:
        process = await asyncio.create_subprocess_shell(
            cmd,
            cwd=project_root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        # Stream output in real-time
        if process.stdout:
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                console.print(line.decode("utf-8", errors="replace").rstrip())

        await process.wait()

        console.print("-" * 60)

        if process.returncode == 0:
            console.print("\n[bold green]All tests passed![/]")
        else:
            console.print(f"\n[bold red]Tests failed with exit code {process.returncode}[/]")

    except Exception as e:
        console.print(f"[red]Error running tests: {e}[/]")


async def _generate_tests(
    project_root: Path,
    file: str,
    verbose: bool,
) -> None:
    """Generate tests for a file using AI"""
    from maxagent.agents.tester import create_tester_agent
    from maxagent.config import load_config

    target_path = Path(file)
    if not target_path.is_absolute():
        target_path = project_root / target_path

    if not target_path.exists():
        console.print(f"[red]File not found: {file}[/]")
        return

    if not target_path.is_file():
        console.print(f"[red]Not a file: {file}[/]")
        return

    # Detect framework
    info = detect_test_framework(project_root)

    # Read the source file
    source_code = target_path.read_text()

    console.print(f"\n[bold]Generating tests for:[/] {file}")
    console.print(f"[bold]Framework:[/] {info.description}")
    console.print()

    # Load config and create tester agent
    config = load_config()

    # Initialize tester to None for safe cleanup
    tester = None

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            task_id = progress.add_task("Analyzing code and generating tests...", total=None)

            tester = create_tester_agent(
                config=config,
                project_root=project_root,
            )

            # Build the prompt
            prompt = f"""Generate comprehensive tests for the following file.

**File:** {target_path.relative_to(project_root)}
**Testing Framework:** {info.framework.value}
**Test Directory:** {info.test_dir.relative_to(project_root) if info.test_dir else 'tests'}

**Source Code:**
```
{source_code}
```

Please:
1. Analyze the code and identify all functions/methods that need testing
2. Generate comprehensive tests including:
   - Normal/happy path tests
   - Edge cases and boundary conditions
   - Error handling tests
3. Follow the existing project conventions
4. Include docstrings explaining what each test verifies
5. Use appropriate fixtures if needed

Output the complete test file that can be run directly.
"""

            # Execute the agent (non-streaming to get complete result)
            result = await tester.run(prompt, stream=False)

            # Ensure result is a string
            if not isinstance(result, str):
                # Shouldn't happen with stream=False, but handle it
                result = "".join([chunk async for chunk in result])

        # Display results
        console.print(
            Panel(
                Markdown(result),
                title="[bold blue]Generated Tests[/]",
                border_style="blue",
            )
        )

        # Extract code blocks from result
        import re

        code_blocks = re.findall(
            r"```(?:python|javascript|typescript|go|rust)?\n(.*?)```", result, re.DOTALL
        )

        if code_blocks:
            # Ask to save
            save = Confirm.ask("\n[bold]Save generated tests to file?[/]", default=True)

            if save:
                # Determine test file path
                if info.test_dir:
                    test_dir = info.test_dir
                else:
                    test_dir = project_root / "tests"
                    test_dir.mkdir(exist_ok=True)

                # Generate test filename
                source_name = target_path.stem
                if info.framework in [TestFramework.PYTEST, TestFramework.UNITTEST]:
                    test_filename = f"test_{source_name}.py"
                elif info.framework in [
                    TestFramework.JEST,
                    TestFramework.VITEST,
                    TestFramework.MOCHA,
                ]:
                    ext = target_path.suffix
                    test_filename = f"{source_name}.test{ext}"
                elif info.framework == TestFramework.GO_TEST:
                    test_filename = f"{source_name}_test.go"
                elif info.framework == TestFramework.CARGO_TEST:
                    test_filename = f"{source_name}_test.rs"
                else:
                    test_filename = f"test_{source_name}.py"

                test_path = test_dir / test_filename

                # Check if file exists
                if test_path.exists():
                    overwrite = Confirm.ask(
                        f"[yellow]File {test_path.relative_to(project_root)} already exists. Overwrite?[/]",
                        default=False,
                    )
                    if not overwrite:
                        # Ask for alternative name
                        alt_name = Prompt.ask(
                            "Enter alternative filename",
                            default=f"test_{source_name}_new.py",
                        )
                        test_path = test_dir / alt_name

                # Write the test file
                test_content = code_blocks[0]  # Use first code block
                test_path.write_text(test_content)
                console.print(f"\n[green]Tests saved to:[/] {test_path.relative_to(project_root)}")

                # Ask to run
                run_now = Confirm.ask("\n[bold]Run the generated tests now?[/]", default=True)
                if run_now:
                    await _run_tests(
                        project_root,
                        str(test_path.relative_to(project_root)),
                        verbose,
                        False,
                        False,
                    )

    except Exception as e:
        console.print(f"[red]Error generating tests: {e}[/]")
        if verbose:
            import traceback

            console.print(traceback.format_exc())

    finally:
        if tester is not None:
            await tester.llm.close()


@app.command()
def detect(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed information"),
) -> None:
    """Detect the testing framework used in the project"""
    project_root = Path.cwd()
    _show_framework_info(project_root, verbose)


@app.command()
def run(
    file: Optional[str] = typer.Argument(None, help="Specific test file or directory to run"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    coverage: bool = typer.Option(False, "--coverage", "-c", help="Run with coverage"),
    watch: bool = typer.Option(False, "--watch", "-w", help="Watch mode"),
) -> None:
    """Run tests"""
    project_root = Path.cwd()
    asyncio.run(_run_tests(project_root, file, verbose, coverage, watch))


@app.command()
def generate(
    file: str = typer.Argument(..., help="File to generate tests for"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
) -> None:
    """Generate tests for a file using AI"""
    project_root = Path.cwd()
    asyncio.run(_generate_tests(project_root, file, verbose))


if __name__ == "__main__":
    app()
