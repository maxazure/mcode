"""Instructions loader for project-specific rules (like AGENTS.md or CLAUDE.md)"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..config.schema import InstructionsConfig


class InstructionSource:
    """Represents a single instruction file source"""

    def __init__(self, path: Path, content: str, source_type: str = "project"):
        self.path = path
        self.content = content
        self.source_type = source_type  # "global", "project", "parent"

    def __repr__(self) -> str:
        return f"InstructionSource({self.path}, type={self.source_type})"


class InstructionsLoader:
    """Loads and combines instruction files from various sources

    Priority order (later overrides earlier):
    1. Global instructions (~/.llc/MAXAGENT.md)
    2. Parent directory instructions (progressive discovery)
    3. Project root instructions (MAXAGENT.md, AGENTS.md, CLAUDE.md)
    4. Additional files specified in config
    """

    def __init__(self, config: InstructionsConfig, project_root: Optional[Path] = None):
        self.config = config
        self.project_root = project_root or Path.cwd()
        self._sources: list[InstructionSource] = []

    def load(self) -> str:
        """Load all instruction files and combine them"""
        self._sources = []

        # 1. Load global instructions
        self._load_global()

        # 2. Progressive discovery from parent directories
        if self.config.auto_discover:
            self._discover_parent_instructions()

        # 3. Load project root instructions
        self._load_project_root()

        # 4. Load additional files
        self._load_additional_files()

        return self._combine_instructions()

    def _load_global(self) -> None:
        """Load global instruction file"""
        global_path = Path(self.config.global_file).expanduser()
        if global_path.exists() and global_path.is_file():
            try:
                content = global_path.read_text(encoding="utf-8")
                self._sources.append(InstructionSource(global_path, content, source_type="global"))
            except Exception:
                pass  # Silently ignore read errors

    def _discover_parent_instructions(self) -> None:
        """Progressive discovery: traverse parent directories for instruction files"""
        all_names = [self.config.filename] + self.config.alternative_names
        current = self.project_root.parent
        home = Path.home()

        # Collect parent instruction files (from root to project parent)
        parent_sources: list[InstructionSource] = []

        while current != current.parent:
            # Stop at home directory or filesystem root
            if current == home or current == Path("/"):
                break

            for name in all_names:
                instruction_file = current / name
                if instruction_file.exists() and instruction_file.is_file():
                    try:
                        content = instruction_file.read_text(encoding="utf-8")
                        parent_sources.append(
                            InstructionSource(instruction_file, content, source_type="parent")
                        )
                    except Exception:
                        pass
                    break  # Only load one instruction file per directory

            current = current.parent

        # Reverse to get root-to-project order (more general -> more specific)
        parent_sources.reverse()
        self._sources.extend(parent_sources)

    def _load_project_root(self) -> None:
        """Load instruction file from project root"""
        all_names = [self.config.filename] + self.config.alternative_names

        for name in all_names:
            instruction_file = self.project_root / name
            if instruction_file.exists() and instruction_file.is_file():
                try:
                    content = instruction_file.read_text(encoding="utf-8")
                    self._sources.append(
                        InstructionSource(instruction_file, content, source_type="project")
                    )
                except Exception:
                    pass
                break  # Only load the first matching file

    def _load_additional_files(self) -> None:
        """Load additional instruction files specified in config"""
        import glob as glob_module

        for pattern in self.config.additional_files:
            # Expand user home and resolve pattern
            expanded = Path(pattern).expanduser()
            if expanded.is_absolute():
                matches = glob_module.glob(str(expanded))
            else:
                matches = glob_module.glob(str(self.project_root / pattern))

            for match in matches:
                match_path = Path(match)
                if match_path.exists() and match_path.is_file():
                    try:
                        content = match_path.read_text(encoding="utf-8")
                        self._sources.append(
                            InstructionSource(match_path, content, source_type="additional")
                        )
                    except Exception:
                        pass

    def _combine_instructions(self) -> str:
        """Combine all instruction sources into a single string"""
        if not self._sources:
            return ""

        parts: list[str] = []

        for source in self._sources:
            header = f"# Instructions from: {source.path}"
            parts.append(header)
            parts.append(source.content.strip())
            parts.append("")  # Empty line between sources

        return "\n".join(parts)

    def get_sources(self) -> list[InstructionSource]:
        """Get list of loaded instruction sources"""
        return self._sources.copy()

    def get_project_instructions(self) -> Optional[str]:
        """Get only project-level instructions (without global/parent)"""
        for source in self._sources:
            if source.source_type == "project":
                return source.content
        return None


def load_instructions(
    config: InstructionsConfig,
    project_root: Optional[Path] = None,
) -> str:
    """Convenience function to load instructions

    Args:
        config: Instructions configuration
        project_root: Project root directory (defaults to cwd)

    Returns:
        Combined instruction text from all sources
    """
    loader = InstructionsLoader(config, project_root)
    return loader.load()


def find_instruction_file(
    project_root: Optional[Path] = None,
    filename: str = "MAXAGENT.md",
    alternative_names: Optional[list[str]] = None,
) -> Optional[Path]:
    """Find instruction file in project root

    Args:
        project_root: Project root directory (defaults to cwd)
        filename: Primary filename to search
        alternative_names: Alternative filenames

    Returns:
        Path to instruction file or None
    """
    root = project_root or Path.cwd()
    names = [filename] + (alternative_names or ["AGENTS.md", "CLAUDE.md", ".maxagent.md"])

    for name in names:
        path = root / name
        if path.exists() and path.is_file():
            return path

    return None
