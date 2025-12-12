"""Tests for Edit tool functionality"""

import pytest
from pathlib import Path
import tempfile
import os

from maxagent.tools.edit import (
    EditTool,
    EditError,
    NotFoundError,
    MultipleMatchesError,
    FileReadTracker,
    replace_content,
    simple_replacer,
    line_trimmed_replacer,
    block_anchor_replacer,
    whitespace_normalized_replacer,
    indentation_flexible_replacer,
    escape_normalized_replacer,
    trimmed_boundary_replacer,
    context_aware_replacer,
    multi_occurrence_replacer,
    levenshtein,
    create_unified_diff,
    validate_indentation,
)


# =============================================================================
# Levenshtein Distance Tests
# =============================================================================


class TestLevenshtein:
    """Tests for Levenshtein distance calculation"""

    def test_identical_strings(self):
        """Identical strings should have distance 0"""
        assert levenshtein("hello", "hello") == 0

    def test_empty_strings(self):
        """Empty strings should have distance equal to other string length"""
        assert levenshtein("", "hello") == 5
        assert levenshtein("hello", "") == 5
        assert levenshtein("", "") == 0

    def test_single_character_difference(self):
        """Single character operations"""
        assert levenshtein("hello", "hallo") == 1  # substitution
        assert levenshtein("hello", "hell") == 1  # deletion
        assert levenshtein("hell", "hello") == 1  # insertion

    def test_multiple_differences(self):
        """Multiple character differences"""
        assert levenshtein("kitten", "sitting") == 3
        assert levenshtein("saturday", "sunday") == 3


# =============================================================================
# Simple Replacer Tests
# =============================================================================


class TestSimpleReplacer:
    """Tests for exact string matching"""

    def test_exact_match(self):
        """Should yield exact matches"""
        content = "hello world"
        matches = list(simple_replacer(content, "hello"))
        assert matches == ["hello"]

    def test_no_match(self):
        """Should yield nothing if no match"""
        content = "hello world"
        matches = list(simple_replacer(content, "goodbye"))
        assert matches == []

    def test_multiple_occurrences(self):
        """Should yield single match (exact match only)"""
        content = "hello hello hello"
        matches = list(simple_replacer(content, "hello"))
        assert matches == ["hello"]


# =============================================================================
# Line Trimmed Replacer Tests
# =============================================================================


class TestLineTrimmedReplacer:
    """Tests for line-trimmed matching"""

    def test_trimmed_match(self):
        """Should match lines after trimming whitespace"""
        content = "    hello world    \nnext line"
        matches = list(line_trimmed_replacer(content, "hello world"))
        assert len(matches) == 1
        assert "hello world" in matches[0]

    def test_multiline_match(self):
        """Should match multiple lines"""
        content = "  line1  \n  line2  \n  line3  "
        matches = list(line_trimmed_replacer(content, "line1\nline2"))
        assert len(matches) == 1

    def test_no_match(self):
        """Should not match if lines don't match when trimmed"""
        content = "hello world"
        matches = list(line_trimmed_replacer(content, "goodbye world"))
        assert matches == []


# =============================================================================
# Block Anchor Replacer Tests
# =============================================================================


class TestBlockAnchorReplacer:
    """Tests for block anchor matching"""

    def test_anchor_match(self):
        """Should match blocks using first/last line anchors"""
        content = """def foo():
    pass

def bar():
    x = 1
    y = 2
    return x + y

def baz():
    pass"""

        search = """def bar():
    something else
    return x + y"""

        matches = list(block_anchor_replacer(content, search))
        assert len(matches) == 1
        assert "def bar():" in matches[0]
        assert "return x + y" in matches[0]

    def test_too_short_search(self):
        """Should not match if search has fewer than 3 lines"""
        content = "line1\nline2\nline3"
        matches = list(block_anchor_replacer(content, "line1\nline2"))
        assert matches == []


# =============================================================================
# Whitespace Normalized Replacer Tests
# =============================================================================


class TestWhitespaceNormalizedReplacer:
    """Tests for whitespace normalized matching"""

    def test_multiple_spaces(self):
        """Should normalize multiple spaces to single"""
        content = "hello    world"
        matches = list(whitespace_normalized_replacer(content, "hello world"))
        assert len(matches) == 1

    def test_tabs_and_spaces(self):
        """Should normalize tabs and spaces"""
        content = "hello\t  world"
        matches = list(whitespace_normalized_replacer(content, "hello world"))
        assert len(matches) == 1


# =============================================================================
# Indentation Flexible Replacer Tests
# =============================================================================


class TestIndentationFlexibleReplacer:
    """Tests for indentation flexible matching"""

    def test_different_indentation(self):
        """Should match content regardless of indentation level"""
        content = """    def foo():
        return 1"""

        search = """def foo():
    return 1"""

        matches = list(indentation_flexible_replacer(content, search))
        assert len(matches) == 1


# =============================================================================
# Escape Normalized Replacer Tests
# =============================================================================


class TestEscapeNormalizedReplacer:
    """Tests for escape sequence handling"""

    def test_escaped_newline(self):
        """Should handle escaped newlines"""
        content = "hello\nworld"
        matches = list(escape_normalized_replacer(content, r"hello\nworld"))
        assert len(matches) >= 1  # May yield multiple matches due to different strategies

    def test_escaped_tab(self):
        """Should handle escaped tabs"""
        content = "hello\tworld"
        matches = list(escape_normalized_replacer(content, r"hello\tworld"))
        assert len(matches) >= 1  # May yield multiple matches due to different strategies


# =============================================================================
# Replace Content Tests
# =============================================================================


class TestReplaceContent:
    """Tests for the main replace_content function"""

    def test_simple_replacement(self):
        """Should perform simple string replacement"""
        content = "hello world"
        result = replace_content(content, "hello", "goodbye")
        assert result == "goodbye world"

    def test_replacement_same_strings_error(self):
        """Should raise error if old and new strings are the same"""
        with pytest.raises(EditError, match="must be different"):
            replace_content("hello", "hello", "hello")

    def test_replacement_not_found_error(self):
        """Should raise error if old string not found"""
        with pytest.raises(NotFoundError):
            replace_content("hello world", "goodbye", "hi")

    def test_replace_all(self):
        """Should replace all occurrences when replace_all=True"""
        content = "hello hello hello"
        result = replace_content(content, "hello", "hi", replace_all=True)
        assert result == "hi hi hi"

    def test_multiple_matches_error(self):
        """Should raise error if multiple matches and replace_all=False"""
        content = "hello hello"
        with pytest.raises(MultipleMatchesError):
            replace_content(content, "hello", "hi", replace_all=False)

    def test_multiline_replacement(self):
        """Should handle multiline replacements"""
        content = """def foo():
    return 1

def bar():
    return 2"""

        result = replace_content(content, "def foo():\n    return 1", "def foo():\n    return 42")
        assert "return 42" in result
        assert "def bar():" in result

    def test_preserves_surrounding_content(self):
        """Should preserve content before and after replacement"""
        content = "# header\n\ndef foo():\n    pass\n\n# footer"
        result = replace_content(content, "def foo():\n    pass", "def foo():\n    return 1")
        assert "# header" in result
        assert "# footer" in result
        assert "return 1" in result


# =============================================================================
# Create Unified Diff Tests
# =============================================================================


class TestCreateUnifiedDiff:
    """Tests for unified diff creation"""

    def test_simple_diff(self):
        """Should create valid unified diff"""
        old = "line1\nline2\nline3"
        new = "line1\nmodified\nline3"
        diff = create_unified_diff("test.py", old, new)

        assert "---" in diff
        assert "+++" in diff
        assert "-line2" in diff
        assert "+modified" in diff

    def test_empty_old_content(self):
        """Should handle empty old content"""
        diff = create_unified_diff("test.py", "", "new content")
        assert "+new content" in diff

    def test_empty_new_content(self):
        """Should handle empty new content"""
        diff = create_unified_diff("test.py", "old content", "")
        assert "-old content" in diff


# =============================================================================
# EditTool Tests
# =============================================================================


class TestEditTool:
    """Tests for EditTool class"""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def edit_tool(self, temp_dir):
        """Create EditTool instance with read requirement disabled for testing"""
        return EditTool(project_root=temp_dir, require_read_first=False)

    @pytest.fixture
    def edit_tool_with_read_check(self, temp_dir):
        """Create EditTool instance with read requirement enabled"""
        return EditTool(project_root=temp_dir, require_read_first=True)

    @pytest.fixture
    def test_file(self, temp_dir):
        """Create a test file"""
        file_path = temp_dir / "test.py"
        file_path.write_text(
            """def hello():
    print("hello")

def world():
    print("world")
"""
        )
        return file_path

    @pytest.mark.asyncio
    async def test_simple_edit(self, edit_tool, test_file, temp_dir):
        """Should perform simple edit"""
        result = await edit_tool.execute(
            file_path="test.py",
            old_string='print("hello")',
            new_string='print("hi")',
        )

        assert result.success
        content = test_file.read_text()
        assert 'print("hi")' in content
        assert 'print("world")' in content  # other code preserved

    @pytest.mark.asyncio
    async def test_edit_preserves_other_code(self, edit_tool, test_file, temp_dir):
        """Should preserve code not being edited"""
        original = test_file.read_text()

        result = await edit_tool.execute(
            file_path="test.py",
            old_string="def hello():",
            new_string="def greet():",
        )

        assert result.success
        content = test_file.read_text()
        assert "def greet():" in content
        assert "def world():" in content  # preserved
        assert 'print("world")' in content  # preserved

    @pytest.mark.asyncio
    async def test_edit_multiline(self, edit_tool, test_file, temp_dir):
        """Should handle multiline edits"""
        result = await edit_tool.execute(
            file_path="test.py",
            old_string='def hello():\n    print("hello")',
            new_string='def hello():\n    """Say hello."""\n    print("hello")',
        )

        assert result.success
        content = test_file.read_text()
        assert '"""Say hello."""' in content

    @pytest.mark.asyncio
    async def test_edit_file_not_found(self, edit_tool, temp_dir):
        """Should return error for non-existent file"""
        result = await edit_tool.execute(
            file_path="nonexistent.py",
            old_string="foo",
            new_string="bar",
        )

        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_edit_string_not_found(self, edit_tool, test_file):
        """Should return error if old_string not found"""
        result = await edit_tool.execute(
            file_path="test.py",
            old_string="nonexistent code",
            new_string="new code",
        )

        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_edit_same_strings(self, edit_tool, test_file):
        """Should return error if old and new strings are the same"""
        result = await edit_tool.execute(
            file_path="test.py",
            old_string="hello",
            new_string="hello",
        )

        assert not result.success
        assert "different" in result.error.lower()

    @pytest.mark.asyncio
    async def test_edit_replace_all(self, temp_dir):
        """Should replace all occurrences with replace_all=True"""
        # Create file with repeated content
        test_file = temp_dir / "repeat.py"
        test_file.write_text("foo foo foo")

        edit_tool = EditTool(project_root=temp_dir, require_read_first=False)
        result = await edit_tool.execute(
            file_path="repeat.py",
            old_string="foo",
            new_string="bar",
            replace_all=True,
        )

        assert result.success
        content = test_file.read_text()
        assert content == "bar bar bar"

    @pytest.mark.asyncio
    async def test_edit_metadata(self, edit_tool, test_file):
        """Should return useful metadata"""
        result = await edit_tool.execute(
            file_path="test.py",
            old_string='print("hello")',
            new_string='print("hi")',
        )

        assert result.success
        assert "path" in result.metadata
        assert "diff" in result.metadata

    @pytest.mark.asyncio
    async def test_edit_outside_project_denied(self, edit_tool, temp_dir):
        """Should deny edits outside project root"""
        result = await edit_tool.execute(
            file_path="/tmp/outside.py",
            old_string="foo",
            new_string="bar",
        )

        assert not result.success
        assert "absolute" in result.error.lower() or "denied" in result.error.lower()

    @pytest.mark.asyncio
    async def test_edit_path_traversal_denied(self, edit_tool):
        """Should deny path traversal"""
        result = await edit_tool.execute(
            file_path="../outside.py",
            old_string="foo",
            new_string="bar",
        )

        assert not result.success
        assert "traversal" in result.error.lower()


# =============================================================================
# Integration Tests
# =============================================================================


class TestEditToolIntegration:
    """Integration tests for real-world scenarios"""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.mark.asyncio
    async def test_add_docstring_to_function(self, temp_dir):
        """Real scenario: Add docstring to existing function"""
        test_file = temp_dir / "module.py"
        test_file.write_text(
            """def calculate_total(items):
    total = 0
    for item in items:
        total += item.price
    return total


def format_price(price):
    return f"${price:.2f}"
"""
        )

        edit_tool = EditTool(project_root=temp_dir, require_read_first=False)
        result = await edit_tool.execute(
            file_path="module.py",
            old_string="def calculate_total(items):\n    total = 0",
            new_string='def calculate_total(items):\n    """Calculate the total price of items."""\n    total = 0',
        )

        assert result.success
        content = test_file.read_text()
        assert '"""Calculate the total price of items."""' in content
        assert "def format_price(price):" in content  # other function preserved
        assert 'return f"${price:.2f}"' in content  # other code preserved

    @pytest.mark.asyncio
    async def test_rename_variable(self, temp_dir):
        """Real scenario: Rename variable across file"""
        test_file = temp_dir / "app.py"
        test_file.write_text(
            """user_name = input("Enter name: ")
print(f"Hello, {user_name}!")
save_user(user_name)
"""
        )

        edit_tool = EditTool(project_root=temp_dir, require_read_first=False)
        result = await edit_tool.execute(
            file_path="app.py",
            old_string="user_name",
            new_string="username",
            replace_all=True,
        )

        assert result.success
        content = test_file.read_text()
        assert "user_name" not in content
        assert content.count("username") == 3

    @pytest.mark.asyncio
    async def test_add_import_statement(self, temp_dir):
        """Real scenario: Add import at top of file"""
        test_file = temp_dir / "service.py"
        test_file.write_text(
            """import os

def get_path():
    return os.getcwd()
"""
        )

        edit_tool = EditTool(project_root=temp_dir, require_read_first=False)
        result = await edit_tool.execute(
            file_path="service.py",
            old_string="import os",
            new_string="import os\nimport json",
        )

        assert result.success
        content = test_file.read_text()
        assert "import os\nimport json" in content
        assert "def get_path():" in content

    @pytest.mark.asyncio
    async def test_modify_function_body(self, temp_dir):
        """Real scenario: Modify function implementation"""
        test_file = temp_dir / "calculator.py"
        test_file.write_text(
            """def add(a, b):
    return a + b


def subtract(a, b):
    return a - b
"""
        )

        edit_tool = EditTool(project_root=temp_dir, require_read_first=False)

        # Add multiply function after add
        result = await edit_tool.execute(
            file_path="calculator.py",
            old_string="def add(a, b):\n    return a + b",
            new_string="def add(a, b):\n    return a + b\n\n\ndef multiply(a, b):\n    return a * b",
        )

        assert result.success
        content = test_file.read_text()
        assert "def add(a, b):" in content
        assert "def multiply(a, b):" in content
        assert "def subtract(a, b):" in content  # preserved!


# =============================================================================
# FileReadTracker Tests
# =============================================================================


class TestFileReadTracker:
    """Tests for the FileReadTracker class"""

    def setup_method(self):
        """Clear tracker before each test"""
        FileReadTracker.clear()

    def test_mark_and_check_read(self):
        """Should track read files correctly"""
        assert not FileReadTracker.was_read_recently("test.py")
        FileReadTracker.mark_read("test.py")
        assert FileReadTracker.was_read_recently("test.py")

    def test_clear_specific_file(self):
        """Should clear tracking for specific file"""
        FileReadTracker.mark_read("file1.py")
        FileReadTracker.mark_read("file2.py")
        FileReadTracker.clear("file1.py")
        assert not FileReadTracker.was_read_recently("file1.py")
        assert FileReadTracker.was_read_recently("file2.py")

    def test_clear_all(self):
        """Should clear all tracking"""
        FileReadTracker.mark_read("file1.py")
        FileReadTracker.mark_read("file2.py")
        FileReadTracker.clear()
        assert not FileReadTracker.was_read_recently("file1.py")
        assert not FileReadTracker.was_read_recently("file2.py")

    def test_get_all_read_files(self):
        """Should return list of read files"""
        FileReadTracker.mark_read("file1.py")
        FileReadTracker.mark_read("file2.py")
        files = FileReadTracker.get_all_read_files()
        assert "file1.py" in files
        assert "file2.py" in files


# =============================================================================
# Indentation Validation Tests
# =============================================================================


class TestIndentationValidation:
    """Tests for the validate_indentation function"""

    def test_no_warnings_for_matching_indentation(self):
        """Should return no warnings when indentation matches"""
        old_string = "    def foo():\n        pass"
        new_string = "    def foo():\n        return 1"
        warnings = validate_indentation(old_string, new_string)
        assert len(warnings) == 0

    def test_warn_on_mixed_tabs_spaces(self):
        """Should warn when new_string has mixed tabs and spaces"""
        old_string = "    def foo():\n        pass"
        new_string = "\tdef foo():\n    pass"
        warnings = validate_indentation(old_string, new_string)
        assert any("mixed" in w.lower() for w in warnings)

    def test_warn_on_style_mismatch(self):
        """Should warn when indentation style differs"""
        old_string = "\tdef foo():\n\t\tpass"
        new_string = "    def foo():\n        pass"
        warnings = validate_indentation(old_string, new_string)
        assert any("mismatch" in w.lower() for w in warnings)

    def test_warn_on_missing_indentation(self):
        """Should warn when first line loses expected indentation"""
        old_string = "    def foo():\n        pass"
        new_string = "def foo():\n    pass"
        warnings = validate_indentation(old_string, new_string)
        assert any("no indentation" in w.lower() for w in warnings)


# =============================================================================
# EditTool Read Requirement Tests
# =============================================================================


class TestEditToolReadRequirement:
    """Tests for the read-before-edit requirement"""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def test_file(self, temp_dir):
        """Create a test file"""
        file_path = temp_dir / "test.py"
        file_path.write_text("hello world")
        return file_path

    def setup_method(self):
        """Clear FileReadTracker before each test"""
        FileReadTracker.clear()

    @pytest.mark.asyncio
    async def test_edit_fails_without_read(self, temp_dir, test_file):
        """Should fail if file hasn't been read first"""
        edit_tool = EditTool(project_root=temp_dir, require_read_first=True)
        result = await edit_tool.execute(
            file_path="test.py",
            old_string="hello",
            new_string="goodbye",
        )
        assert not result.success
        assert "read" in result.error.lower()

    @pytest.mark.asyncio
    async def test_edit_succeeds_after_read(self, temp_dir, test_file):
        """Should succeed if file has been read first"""
        edit_tool = EditTool(project_root=temp_dir, require_read_first=True)
        
        # Simulate reading the file
        FileReadTracker.mark_read("test.py")
        
        result = await edit_tool.execute(
            file_path="test.py",
            old_string="hello",
            new_string="goodbye",
        )
        assert result.success

    @pytest.mark.asyncio
    async def test_edit_succeeds_with_disabled_check(self, temp_dir, test_file):
        """Should succeed when read check is disabled"""
        edit_tool = EditTool(project_root=temp_dir, require_read_first=False)
        result = await edit_tool.execute(
            file_path="test.py",
            old_string="hello",
            new_string="goodbye",
        )
        assert result.success

    @pytest.mark.asyncio
    async def test_mark_file_read_method(self, temp_dir, test_file):
        """Should be able to mark file read via tool method"""
        edit_tool = EditTool(project_root=temp_dir, require_read_first=True)
        
        # Use tool method to mark file read
        edit_tool.mark_file_read("test.py")
        
        result = await edit_tool.execute(
            file_path="test.py",
            old_string="hello",
            new_string="goodbye",
        )
        assert result.success
