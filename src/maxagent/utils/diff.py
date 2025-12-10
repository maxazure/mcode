"""Diff utilities for patch handling"""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional


def create_backup(file_path: Path, backup_dir: Optional[Path] = None) -> Path:
    """
    Create a backup of a file.

    Args:
        file_path: Path to file to backup
        backup_dir: Optional backup directory (default: .llc-backups in same dir)

    Returns:
        Path to backup file
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Create backup directory
    if backup_dir is None:
        backup_dir = file_path.parent / ".llc-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Create backup filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{file_path.name}.{timestamp}.bak"
    backup_path = backup_dir / backup_name

    # Copy file
    shutil.copy2(file_path, backup_path)

    return backup_path


def apply_patch(patch: str, target_file: Path, create_backup_file: bool = True) -> bool:
    """
    Apply a unified diff patch to a file.

    This is a simplified patch application that handles basic unified diffs.
    For production use, consider using the `patch` command or `unidiff` library.

    Args:
        patch: Unified diff string
        target_file: Target file path
        create_backup_file: Whether to create a backup before applying

    Returns:
        True if successful, False otherwise
    """
    if not target_file.exists():
        # For new files, just extract the content from the patch
        content = extract_new_content(patch)
        if content is not None:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(content, encoding="utf-8")
            return True
        return False

    # Create backup if requested
    if create_backup_file:
        create_backup(target_file)

    # Read current content
    current_content = target_file.read_text(encoding="utf-8")
    current_lines = current_content.splitlines(keepends=True)

    # Parse and apply patch
    try:
        new_lines = apply_unified_diff(current_lines, patch)
        new_content = "".join(new_lines)

        # Ensure file ends with newline
        if new_content and not new_content.endswith("\n"):
            new_content += "\n"

        target_file.write_text(new_content, encoding="utf-8")
        return True
    except Exception:
        return False


def apply_unified_diff(lines: list[str], patch: str) -> list[str]:
    """
    Apply a unified diff to a list of lines.

    Args:
        lines: Original file lines
        patch: Unified diff string

    Returns:
        Modified lines
    """
    result = lines.copy()
    offset = 0  # Track line number offset from previous hunks

    # Parse hunks
    hunk_pattern = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

    patch_lines = patch.splitlines()
    i = 0

    while i < len(patch_lines):
        line = patch_lines[i]

        # Skip header lines
        if line.startswith("---") or line.startswith("+++") or line.startswith("diff"):
            i += 1
            continue

        # Parse hunk header
        match = hunk_pattern.match(line)
        if match:
            old_start = int(match.group(1))
            old_count = int(match.group(2) or 1)
            new_start = int(match.group(3))
            new_count = int(match.group(4) or 1)

            # Collect hunk lines
            i += 1
            hunk_lines: list[str] = []
            while i < len(patch_lines) and not patch_lines[i].startswith("@@"):
                hunk_lines.append(patch_lines[i])
                i += 1

            # Apply hunk
            result, offset = apply_hunk(
                result,
                hunk_lines,
                old_start - 1 + offset,  # Convert to 0-based index
                offset,
            )
        else:
            i += 1

    return result


def apply_hunk(
    lines: list[str],
    hunk_lines: list[str],
    start_idx: int,
    current_offset: int,
) -> tuple[list[str], int]:
    """
    Apply a single hunk to lines.

    Args:
        lines: Current file lines
        hunk_lines: Lines in the hunk
        start_idx: Starting index (0-based)
        current_offset: Current line offset

    Returns:
        Tuple of (modified lines, new offset)
    """
    result = lines[:start_idx]
    idx = start_idx
    new_offset = current_offset

    for hunk_line in hunk_lines:
        if not hunk_line:
            continue

        prefix = hunk_line[0] if hunk_line else " "
        content = hunk_line[1:] if len(hunk_line) > 1 else ""

        # Ensure line ends with newline
        if content and not content.endswith("\n"):
            content += "\n"

        if prefix == " ":
            # Context line - keep original
            if idx < len(lines):
                result.append(lines[idx])
                idx += 1
            else:
                result.append(content)
        elif prefix == "-":
            # Removed line - skip in original
            idx += 1
            new_offset -= 1
        elif prefix == "+":
            # Added line - insert
            result.append(content)
            new_offset += 1
        elif prefix == "\\":
            # "No newline at end of file" marker - ignore
            pass

    # Add remaining lines
    result.extend(lines[idx:])

    return result, new_offset


def extract_new_content(patch: str) -> Optional[str]:
    """
    Extract content for a new file from a patch.

    Args:
        patch: Unified diff patch

    Returns:
        File content or None if not a new file patch
    """
    lines = patch.splitlines()
    content_lines: list[str] = []
    in_content = False

    for line in lines:
        if line.startswith("@@"):
            in_content = True
            continue
        if in_content:
            if line.startswith("+") and not line.startswith("+++"):
                content_lines.append(line[1:])
            elif line.startswith("-") and not line.startswith("---"):
                # This is a modification, not a new file
                return None
            elif line.startswith(" "):
                content_lines.append(line[1:])

    if content_lines:
        return "\n".join(content_lines)
    return None


def extract_patches_from_text(text: str) -> list[tuple[str, str]]:
    """
    Extract patches from text that may contain multiple patches.

    Args:
        text: Text potentially containing patches

    Returns:
        List of (filename, patch) tuples
    """
    patches: list[tuple[str, str]] = []

    # Pattern to match diff blocks in markdown code blocks
    code_block_pattern = re.compile(r"```(?:diff)?\n(.*?)```", re.DOTALL)

    for match in code_block_pattern.finditer(text):
        patch_content = match.group(1).strip()
        if patch_content.startswith("---") or patch_content.startswith("diff"):
            filename = extract_filename_from_patch(patch_content)
            if filename:
                patches.append((filename, patch_content))

    # Also try to find standalone patches
    standalone_pattern = re.compile(
        r"^(---\s+\S+.*?\n\+\+\+\s+\S+.*?\n(?:@@.*?\n(?:[+ -].*?\n)*)+)",
        re.MULTILINE,
    )

    for match in standalone_pattern.finditer(text):
        patch_content = match.group(1).strip()
        filename = extract_filename_from_patch(patch_content)
        if filename and (filename, patch_content) not in patches:
            patches.append((filename, patch_content))

    return patches


def extract_filename_from_patch(patch: str) -> Optional[str]:
    """
    Extract the target filename from a patch.

    Args:
        patch: Unified diff patch

    Returns:
        Filename or None
    """
    lines = patch.splitlines()

    for line in lines:
        if line.startswith("+++ "):
            # Extract filename, removing prefixes like b/
            filename = line[4:].strip()
            if filename.startswith("b/"):
                filename = filename[2:]
            # Remove timestamp if present
            if "\t" in filename:
                filename = filename.split("\t")[0]
            return filename

    return None
