"""Edit tool for precise code modifications using search-and-replace.

This module implements an edit tool similar to Claude Code and OpenCode,
using exact string replacement with multiple fallback strategies for
flexible matching.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, ClassVar, Generator, Optional, Protocol

from .base import BaseTool, ToolParameter, ToolResult


class FileReadTracker:
    """Track file read times to enforce read-before-edit pattern.
    
    This implements the FileTime pattern from OpenCode to ensure
    files are read before editing, preventing blind edits.
    """
    
    # Class-level storage for read timestamps
    _read_times: ClassVar[dict[str, float]] = {}
    # Expiration time in seconds (5 minutes)
    READ_EXPIRATION = 300
    
    @classmethod
    def mark_read(cls, file_path: str) -> None:
        """Mark a file as read with current timestamp"""
        cls._read_times[file_path] = time.time()
    
    @classmethod
    def was_read_recently(cls, file_path: str) -> bool:
        """Check if file was read recently (within expiration time)"""
        read_time = cls._read_times.get(file_path)
        if read_time is None:
            return False
        return (time.time() - read_time) < cls.READ_EXPIRATION
    
    @classmethod
    def clear(cls, file_path: str | None = None) -> None:
        """Clear read tracking for a file or all files"""
        if file_path is None:
            cls._read_times.clear()
        elif file_path in cls._read_times:
            del cls._read_times[file_path]
    
    @classmethod
    def get_all_read_files(cls) -> list[str]:
        """Get list of all recently read files"""
        current_time = time.time()
        return [
            path for path, read_time in cls._read_times.items()
            if (current_time - read_time) < cls.READ_EXPIRATION
        ]


def validate_indentation(old_string: str, new_string: str) -> list[str]:
    """Validate indentation consistency between old and new strings.
    
    Returns a list of warning messages if indentation issues are detected.
    """
    warnings = []
    
    old_lines = old_string.split('\n')
    new_lines = new_string.split('\n')
    
    # Check for mixed tabs and spaces in new_string
    has_tabs = any('\t' in line for line in new_lines)
    has_spaces = any(line.startswith(' ') for line in new_lines if line.strip())
    if has_tabs and has_spaces:
        warnings.append(
            "WARNING: new_string contains mixed tabs and spaces. "
            "This may cause indentation errors."
        )
    
    # Detect indentation style of old content
    old_indent_char = None
    for line in old_lines:
        if line and not line.strip():
            continue
        if line.startswith('\t'):
            old_indent_char = '\t'
            break
        elif line.startswith(' '):
            old_indent_char = ' '
            break
    
    # Check if new content matches old indentation style
    if old_indent_char:
        new_indent_char = None
        for line in new_lines:
            if line and not line.strip():
                continue
            if line.startswith('\t'):
                new_indent_char = '\t'
                break
            elif line.startswith(' '):
                new_indent_char = ' '
                break
        
        if new_indent_char and old_indent_char != new_indent_char:
            warnings.append(
                f"WARNING: Indentation style mismatch. "
                f"File uses {'tabs' if old_indent_char == chr(9) else 'spaces'}, "
                f"but new_string uses {'tabs' if new_indent_char == chr(9) else 'spaces'}."
            )
    
    # Check for common indentation mistakes
    # e.g., unindented code that should be indented
    if old_lines and new_lines:
        old_first_indent = len(old_lines[0]) - len(old_lines[0].lstrip())
        new_first_indent = len(new_lines[0]) - len(new_lines[0].lstrip())
        
        if old_first_indent > 0 and new_first_indent == 0 and new_lines[0].strip():
            warnings.append(
                f"WARNING: First line of new_string has no indentation, "
                f"but original has {old_first_indent} characters of indent. "
                f"Make sure the indentation is correct."
            )
    
    return warnings


class Replacer(Protocol):
    """Protocol for string replacement strategies"""

    def __call__(self, content: str, find: str) -> Generator[str, None, None]:
        """Generate possible matches for the search string in content"""
        ...


def levenshtein(a: str, b: str) -> int:
    """Calculate Levenshtein distance between two strings"""
    if a == "" or b == "":
        return max(len(a), len(b))

    matrix = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]

    for i in range(len(a) + 1):
        matrix[i][0] = i
    for j in range(len(b) + 1):
        matrix[0][j] = j

    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            matrix[i][j] = min(
                matrix[i - 1][j] + 1,  # deletion
                matrix[i][j - 1] + 1,  # insertion
                matrix[i - 1][j - 1] + cost,  # substitution
            )

    return matrix[len(a)][len(b)]


def simple_replacer(content: str, find: str) -> Generator[str, None, None]:
    """Exact string matching - the most precise replacer"""
    if find in content:
        yield find


def line_trimmed_replacer(content: str, find: str) -> Generator[str, None, None]:
    """Match lines after trimming whitespace from both ends"""
    original_lines = content.split("\n")
    search_lines = find.split("\n")

    # Remove trailing empty line if present
    if search_lines and search_lines[-1] == "":
        search_lines.pop()

    for i in range(len(original_lines) - len(search_lines) + 1):
        matches = True

        for j in range(len(search_lines)):
            original_trimmed = original_lines[i + j].strip()
            search_trimmed = search_lines[j].strip()

            if original_trimmed != search_trimmed:
                matches = False
                break

        if matches:
            # Calculate the actual match position
            match_start_index = sum(len(original_lines[k]) + 1 for k in range(i))
            match_end_index = match_start_index
            for k in range(len(search_lines)):
                match_end_index += len(original_lines[i + k])
                if k < len(search_lines) - 1:
                    match_end_index += 1  # newline

            yield content[match_start_index:match_end_index]


def block_anchor_replacer(content: str, find: str) -> Generator[str, None, None]:
    """Match blocks using first and last line as anchors with similarity scoring"""
    original_lines = content.split("\n")
    search_lines = find.split("\n")

    if len(search_lines) < 3:
        return

    if search_lines and search_lines[-1] == "":
        search_lines.pop()

    first_line_search = search_lines[0].strip()
    last_line_search = search_lines[-1].strip()
    search_block_size = len(search_lines)

    # Collect all candidate positions
    candidates: list[tuple[int, int]] = []
    for i in range(len(original_lines)):
        if original_lines[i].strip() != first_line_search:
            continue

        for j in range(i + 2, len(original_lines)):
            if original_lines[j].strip() == last_line_search:
                candidates.append((i, j))
                break

    if not candidates:
        return

    # Single candidate - use relaxed threshold
    SINGLE_CANDIDATE_THRESHOLD = 0.0
    MULTIPLE_CANDIDATES_THRESHOLD = 0.3

    if len(candidates) == 1:
        start_line, end_line = candidates[0]
        actual_block_size = end_line - start_line + 1

        similarity = 0.0
        lines_to_check = min(search_block_size - 2, actual_block_size - 2)

        if lines_to_check > 0:
            for j in range(1, min(search_block_size - 1, actual_block_size - 1)):
                original_line = original_lines[start_line + j].strip()
                search_line = search_lines[j].strip()
                max_len = max(len(original_line), len(search_line))
                if max_len == 0:
                    continue
                distance = levenshtein(original_line, search_line)
                similarity += (1 - distance / max_len) / lines_to_check
        else:
            similarity = 1.0

        if similarity >= SINGLE_CANDIDATE_THRESHOLD:
            match_start = sum(len(original_lines[k]) + 1 for k in range(start_line))
            match_end = match_start
            for k in range(start_line, end_line + 1):
                match_end += len(original_lines[k])
                if k < end_line:
                    match_end += 1
            yield content[match_start:match_end]
        return

    # Multiple candidates - find best match
    best_match: Optional[tuple[int, int]] = None
    max_similarity = -1.0

    for start_line, end_line in candidates:
        actual_block_size = end_line - start_line + 1

        similarity = 0.0
        lines_to_check = min(search_block_size - 2, actual_block_size - 2)

        if lines_to_check > 0:
            for j in range(1, min(search_block_size - 1, actual_block_size - 1)):
                original_line = original_lines[start_line + j].strip()
                search_line = search_lines[j].strip()
                max_len = max(len(original_line), len(search_line))
                if max_len == 0:
                    continue
                distance = levenshtein(original_line, search_line)
                similarity += 1 - distance / max_len
            similarity /= lines_to_check
        else:
            similarity = 1.0

        if similarity > max_similarity:
            max_similarity = similarity
            best_match = (start_line, end_line)

    if max_similarity >= MULTIPLE_CANDIDATES_THRESHOLD and best_match:
        start_line, end_line = best_match
        match_start = sum(len(original_lines[k]) + 1 for k in range(start_line))
        match_end = match_start
        for k in range(start_line, end_line + 1):
            match_end += len(original_lines[k])
            if k < end_line:
                match_end += 1
        yield content[match_start:match_end]


def whitespace_normalized_replacer(content: str, find: str) -> Generator[str, None, None]:
    """Match with normalized whitespace (multiple spaces -> single space)"""

    def normalize(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    normalized_find = normalize(find)
    lines = content.split("\n")

    for line in lines:
        if normalize(line) == normalized_find:
            yield line
        elif normalized_find in normalize(line):
            # Find actual substring match
            words = find.strip().split()
            if words:
                pattern = r"\s+".join(re.escape(word) for word in words)
                try:
                    match = re.search(pattern, line)
                    if match:
                        yield match.group(0)
                except re.error:
                    pass

    # Multi-line match
    find_lines = find.split("\n")
    if len(find_lines) > 1:
        for i in range(len(lines) - len(find_lines) + 1):
            block = lines[i : i + len(find_lines)]
            if normalize("\n".join(block)) == normalized_find:
                yield "\n".join(block)


def indentation_flexible_replacer(content: str, find: str) -> Generator[str, None, None]:
    """Match with flexible indentation (remove common leading whitespace)"""

    def remove_indentation(text: str) -> str:
        text_lines = text.split("\n")
        non_empty_lines = [line for line in text_lines if line.strip()]
        if not non_empty_lines:
            return text

        min_indent = min(len(line) - len(line.lstrip()) for line in non_empty_lines)
        return "\n".join(line if not line.strip() else line[min_indent:] for line in text_lines)

    normalized_find = remove_indentation(find)
    content_lines = content.split("\n")
    find_lines = find.split("\n")

    for i in range(len(content_lines) - len(find_lines) + 1):
        block = "\n".join(content_lines[i : i + len(find_lines)])
        if remove_indentation(block) == normalized_find:
            yield block


def escape_normalized_replacer(content: str, find: str) -> Generator[str, None, None]:
    """Match with escape sequence normalization"""

    def unescape(text: str) -> str:
        replacements = {
            r"\n": "\n",
            r"\t": "\t",
            r"\r": "\r",
            r"\'": "'",
            r"\"": '"',
            r"\`": "`",
            r"\\": "\\",
            r"\$": "$",
        }
        result = text
        for escaped, unescaped in replacements.items():
            result = result.replace(escaped, unescaped)
        return result

    unescaped_find = unescape(find)

    if unescaped_find in content:
        yield unescaped_find

    lines = content.split("\n")
    find_lines = unescaped_find.split("\n")

    for i in range(len(lines) - len(find_lines) + 1):
        block = "\n".join(lines[i : i + len(find_lines)])
        if unescape(block) == unescaped_find:
            yield block


def trimmed_boundary_replacer(content: str, find: str) -> Generator[str, None, None]:
    """Match with trimmed boundaries"""
    trimmed_find = find.strip()

    if trimmed_find == find:
        return  # Already trimmed

    if trimmed_find in content:
        yield trimmed_find

    lines = content.split("\n")
    find_lines = find.split("\n")

    for i in range(len(lines) - len(find_lines) + 1):
        block = "\n".join(lines[i : i + len(find_lines)])
        if block.strip() == trimmed_find:
            yield block


def context_aware_replacer(content: str, find: str) -> Generator[str, None, None]:
    """Match using context anchors (first and last lines)"""
    find_lines = find.split("\n")
    if len(find_lines) < 3:
        return

    if find_lines and find_lines[-1] == "":
        find_lines.pop()

    content_lines = content.split("\n")
    first_line = find_lines[0].strip()
    last_line = find_lines[-1].strip()

    for i in range(len(content_lines)):
        if content_lines[i].strip() != first_line:
            continue

        for j in range(i + 2, len(content_lines)):
            if content_lines[j].strip() == last_line:
                block_lines = content_lines[i : j + 1]
                block = "\n".join(block_lines)

                if len(block_lines) == len(find_lines):
                    matching_lines = 0
                    total_non_empty = 0

                    for k in range(1, len(block_lines) - 1):
                        block_line = block_lines[k].strip()
                        find_line = find_lines[k].strip()

                        if block_line or find_line:
                            total_non_empty += 1
                            if block_line == find_line:
                                matching_lines += 1

                    if total_non_empty == 0 or matching_lines / total_non_empty >= 0.5:
                        yield block
                        break
                break


def multi_occurrence_replacer(content: str, find: str) -> Generator[str, None, None]:
    """Yield all exact matches for multiple occurrences"""
    start_index = 0
    while True:
        index = content.find(find, start_index)
        if index == -1:
            break
        yield find
        start_index = index + len(find)


# Ordered list of replacers to try
REPLACERS: list[Replacer] = [
    simple_replacer,
    line_trimmed_replacer,
    block_anchor_replacer,
    whitespace_normalized_replacer,
    indentation_flexible_replacer,
    escape_normalized_replacer,
    trimmed_boundary_replacer,
    context_aware_replacer,
    multi_occurrence_replacer,
]


class EditError(Exception):
    """Base exception for edit errors with detailed information"""

    def __init__(self, message: str, error_type: str, suggestion: str = ""):
        super().__init__(message)
        self.error_type = error_type
        self.suggestion = suggestion


class NotFoundError(EditError):
    """Raised when the search string is not found in content"""

    def __init__(self, old_string: str, content_preview: str = ""):
        preview_msg = ""
        if content_preview:
            preview_msg = f"\n\nFirst 500 chars of file:\n{content_preview[:500]}..."

        message = (
            f"SEARCH STRING NOT FOUND in file content.\n"
            f"The exact text you provided does not exist in the file.{preview_msg}"
        )
        suggestion = (
            "Suggestions:\n"
            "1. Use `read_file` to see the actual file content\n"
            "2. Ensure whitespace and indentation match exactly\n"
            "3. Copy the text directly from the file content"
        )
        super().__init__(message, "not_found", suggestion)
        self.old_string = old_string


class MultipleMatchesError(EditError):
    """Raised when the search string matches multiple locations"""

    def __init__(self, old_string: str, match_count: int):
        message = (
            f"MULTIPLE MATCHES FOUND: The search string appears {match_count} times in the file.\n"
            f"Cannot determine which occurrence to replace."
        )
        suggestion = (
            "Suggestions:\n"
            "1. Add 3-5 surrounding lines to make the match unique\n"
            "2. Include distinctive nearby code (comments, function names)\n"
            "3. Use `replace_all=true` if you want to replace ALL occurrences"
        )
        super().__init__(message, "multiple_matches", suggestion)
        self.old_string = old_string
        self.match_count = match_count


def replace_content(
    content: str, old_string: str, new_string: str, replace_all: bool = False
) -> str:
    """
    Replace old_string with new_string in content using multiple strategies.

    Args:
        content: The file content
        old_string: The text to find and replace
        new_string: The replacement text
        replace_all: If True, replace all occurrences

    Returns:
        The modified content

    Raises:
        EditError: If old_string not found or found multiple times without replace_all
    """
    if old_string == new_string:
        raise EditError(
            "oldString and newString must be different",
            "same_content",
            "The text you want to replace is identical to the replacement. Check your edit."
        )

    not_found = True
    match_count = 0

    for replacer in REPLACERS:
        for search in replacer(content, old_string):
            index = content.find(search)
            if index == -1:
                continue

            not_found = False

            if replace_all:
                return content.replace(search, new_string)

            # Check for multiple occurrences
            last_index = content.rfind(search)
            if index != last_index:
                # Count actual occurrences
                match_count = content.count(search)
                continue  # Multiple matches, try more specific replacer

            # Single match found - perform replacement
            return content[:index] + new_string + content[index + len(search) :]

    if not_found:
        # Provide helpful context in error
        raise NotFoundError(old_string, content)

    raise MultipleMatchesError(old_string, match_count if match_count > 0 else 2)


def create_unified_diff(
    file_path: str, old_content: str, new_content: str, context_lines: int = 3
) -> str:
    """Create a unified diff between old and new content"""
    import difflib

    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        n=context_lines,
    )

    return "".join(diff)


class EditTool(BaseTool):
    """Edit files using exact string replacement.

    This tool performs precise edits by replacing exact text matches.
    It's the primary way to modify code without overwriting entire files.
    """

    name = "edit"
    description = """Performs exact string replacements in files.

Usage:
- You must use the `read_file` tool first before editing. This tool will error if you attempt an edit without reading the file.
- When editing text, ensure you preserve the exact indentation (tabs/spaces) as it appears in the file.
- ALWAYS prefer editing existing files over writing new files.
- The edit will FAIL if `oldString` is not found in the file.
- The edit will FAIL if `oldString` is found multiple times. Either provide more surrounding context to make it unique, or use `replaceAll=true`.
- Use `replaceAll` for replacing and renaming strings across the file (e.g., renaming a variable).

Common Errors:
- "NOT FOUND": Your search string doesn't match the file. Use read_file to see actual content.
- "MULTIPLE MATCHES": Your search string is too generic. Add more surrounding lines.
- "MUST READ FIRST": You must read_file before editing. This prevents blind edits."""

    parameters = [
        ToolParameter(
            name="file_path",
            type="string",
            description="The path to the file to modify (relative to project root, or absolute if allowed)",
        ),
        ToolParameter(
            name="old_string",
            type="string",
            description="The exact text to replace (must match exactly, including whitespace)",
        ),
        ToolParameter(
            name="new_string",
            type="string",
            description="The text to replace it with (must be different from old_string)",
        ),
        ToolParameter(
            name="replace_all",
            type="boolean",
            description="Replace all occurrences of old_string (default: false)",
            required=False,
            default=False,
        ),
    ]
    risk_level = "high"

    def __init__(
        self,
        project_root: Path,
        allow_outside_project: bool = False,
        create_backup: bool = False,
        require_read_first: bool = True,
    ) -> None:
        self.project_root = project_root.resolve()
        self.allow_outside_project = allow_outside_project
        self.create_backup = create_backup
        self.require_read_first = require_read_first
        # Track which files have been read in this session (deprecated, use FileReadTracker)
        self._read_files: set[str] = set()

    def mark_file_read(self, path: str) -> None:
        """Mark a file as having been read (uses both old and new tracking)"""
        self._read_files.add(path)
        FileReadTracker.mark_read(path)

    def _resolve_path(self, path: str) -> Path:
        """Resolve path, handling ~ and absolute paths if allowed"""
        if self.allow_outside_project:
            expanded = os.path.expanduser(path)
            if os.path.isabs(expanded):
                return Path(expanded)
        return self.project_root / path

    def _is_safe_path(self, path: Path) -> bool:
        """Check if path is safe to edit"""
        try:
            resolved = path.resolve()

            if self.allow_outside_project:
                return True

            # Must be within project root
            try:
                resolved.relative_to(self.project_root)
                return True
            except ValueError:
                return False

        except Exception:
            return False

    def _check_read_requirement(self, file_path: str, resolved_path: Path) -> ToolResult | None:
        """Check if file was read before edit. Returns error ToolResult if not."""
        if not self.require_read_first:
            return None
        
        # Check both old tracking and new FileReadTracker
        file_was_read = (
            file_path in self._read_files or 
            str(resolved_path) in self._read_files or
            FileReadTracker.was_read_recently(file_path) or
            FileReadTracker.was_read_recently(str(resolved_path))
        )
        
        if not file_was_read:
            return ToolResult(
                success=False,
                output="",
                error=(
                    "MUST READ FILE FIRST: You must use `read_file` on this file before editing.\n"
                    "This prevents blind edits that may corrupt the file.\n\n"
                    f"Run: read_file('{file_path}')\n"
                    "Then retry your edit."
                ),
            )
        return None

    async def execute(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute the edit operation"""
        try:
            # Validate inputs
            if not file_path:
                return ToolResult(success=False, output="", error="file_path is required")

            if old_string == new_string:
                return ToolResult(
                    success=False,
                    output="",
                    error="old_string and new_string must be different",
                )

            if not old_string.strip():
                return ToolResult(
                    success=False,
                    output="",
                    error=(
                        "old_string cannot be empty. "
                        "Provide the exact text to replace (with context) or use a more targeted snippet."
                    ),
                )

            # Check for path restrictions
            if not self.allow_outside_project:
                if file_path.startswith("~") or file_path.startswith("/"):
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Cannot edit absolute path: {file_path}. "
                        f"Use a path relative to the project root.",
                    )
                if ".." in file_path:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Path traversal not allowed: {file_path}",
                    )

            resolved_path = self._resolve_path(file_path)

            # Security check
            if not self._is_safe_path(resolved_path):
                return ToolResult(success=False, output="", error=f"Access denied: {file_path}")

            # Check file exists
            if not resolved_path.exists():
                return ToolResult(success=False, output="", error=f"File not found: {file_path}")

            if not resolved_path.is_file():
                return ToolResult(success=False, output="", error=f"Not a file: {file_path}")

            # Check read requirement (FileTime pattern)
            read_check = self._check_read_requirement(file_path, resolved_path)
            if read_check is not None:
                return read_check

            # Read current content
            try:
                old_content = resolved_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Cannot read file as text: {file_path}",
                )

            # Prevent accidental full-file replacement
            if old_string == old_content or old_string.strip() == old_content.strip():
                return ToolResult(
                    success=False,
                    output="",
                    error=(
                        "Refusing full-file replacement. "
                        "Provide a smaller old_string snippet or break the change into smaller edits."
                    ),
                )

            # Validate indentation
            indent_warnings = validate_indentation(old_string, new_string)
            
            # Handle empty old_string (create new file content)
            if old_string == "":
                new_content = new_string
            else:
                # Perform replacement
                try:
                    new_content = replace_content(old_content, old_string, new_string, replace_all)
                except EditError as e:
                    error_msg = str(e)
                    if e.suggestion:
                        error_msg += f"\n\n{e.suggestion}"
                    return ToolResult(success=False, output="", error=error_msg)

            # Create backup if requested
            if self.create_backup and old_content != new_content:
                backup_path = resolved_path.with_suffix(resolved_path.suffix + ".backup")
                backup_path.write_text(old_content, encoding="utf-8")

            # Write new content
            resolved_path.write_text(new_content, encoding="utf-8")

            # Generate diff for output
            diff = create_unified_diff(file_path, old_content, new_content)

            # Calculate display path
            try:
                display_path = str(resolved_path.relative_to(self.project_root))
            except ValueError:
                display_path = str(resolved_path)

            # Count changes
            old_lines = old_content.count("\n")
            new_lines = new_content.count("\n")
            additions = max(0, new_lines - old_lines)
            deletions = max(0, old_lines - new_lines)

            # Build output message
            output_msg = f"Successfully edited {display_path}\n\n{diff}"
            if indent_warnings:
                output_msg += "\n\n" + "\n".join(indent_warnings)

            return ToolResult(
                success=True,
                output=output_msg,
                metadata={
                    "path": display_path,
                    "diff": diff,
                    "additions": additions,
                    "deletions": deletions,
                    "old_size": len(old_content),
                    "new_size": len(new_content),
                    "final_content": new_content,
                    "indent_warnings": indent_warnings,
                },
            )

        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
