"""Utility functions"""

from .console import (
    console,
    print_code,
    print_diff,
    print_dim,
    print_error,
    print_info,
    print_message,
    print_success,
    print_warning,
)
from .diff import (
    apply_patch,
    create_backup,
    extract_filename_from_patch,
    extract_patches_from_text,
)
from .tokens import (
    TokenTracker,
    TokenStats,
    get_token_tracker,
    reset_token_tracker,
    MODEL_PRICING,
)

__all__ = [
    "console",
    "print_code",
    "print_diff",
    "print_dim",
    "print_error",
    "print_info",
    "print_message",
    "print_success",
    "print_warning",
    "apply_patch",
    "create_backup",
    "extract_filename_from_patch",
    "extract_patches_from_text",
    # Token tracking
    "TokenTracker",
    "TokenStats",
    "get_token_tracker",
    "reset_token_tracker",
    "MODEL_PRICING",
]
