"""Test excessive edit rejection mechanism.

This tests the mechanism that rejects edit calls when agents make too many
separate edit calls to the same file, enforcing batch edits instead.

The threshold is set to 2, meaning:
- 1st edit: allowed
- 2nd edit: REJECTED (must use batched edits)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
from typing import Any

from maxagent.core.agent import Agent, AgentConfig
from maxagent.config import Config
from maxagent.tools import ToolRegistry, ToolResult


@dataclass
class MockToolCall:
    """Mock tool call for testing."""

    id: str
    function: Any


@dataclass
class MockFunction:
    """Mock function info."""

    name: str
    arguments: str


@pytest.fixture
def mock_config():
    """Create a mock config."""
    config = MagicMock(spec=Config)
    config.model = MagicMock()
    config.model.enable_tool_planner = False
    return config


@pytest.fixture
def mock_llm():
    """Create a mock LLM client."""
    llm = MagicMock()
    llm.config = MagicMock()
    llm.config.model = "test-model"
    return llm


@pytest.fixture
def mock_tools():
    """Create a mock tool registry."""
    return MagicMock(spec=ToolRegistry)


@pytest.fixture
def agent(mock_config, mock_llm, mock_tools):
    """Create an agent instance for testing."""
    agent_config = AgentConfig(
        name="test",
        system_prompt="Test prompt",
        max_iterations=10,
    )
    return Agent(
        config=mock_config,
        agent_config=agent_config,
        llm_client=mock_llm,
        tool_registry=mock_tools,
    )


class TestExcessiveEditTracking:
    """Test edit count tracking per file."""

    def test_initial_edit_count_is_zero(self, agent):
        """Edit count should start at zero."""
        assert agent._edit_count_per_file == {}

    def test_edit_count_increments_on_successful_edit(self, agent):
        """Edit count should increment after successful edit."""
        # Record a successful edit
        args = '{"file_path": "test.py", "old_string": "a", "new_string": "b"}'
        result = ToolResult(success=True, output="OK")
        agent._record_tool_call("edit", args, result)

        assert agent._edit_count_per_file.get("test.py") == 1

    def test_edit_count_accumulates(self, agent):
        """Multiple edits to same file should accumulate."""
        args = '{"file_path": "test.py", "old_string": "a", "new_string": "b"}'
        result = ToolResult(success=True, output="OK")

        for _ in range(5):
            agent._record_tool_call("edit", args, result)

        assert agent._edit_count_per_file.get("test.py") == 5

    def test_edit_count_tracks_different_files_separately(self, agent):
        """Different files should have separate counts."""
        result = ToolResult(success=True, output="OK")

        agent._record_tool_call(
            "edit", '{"file_path": "file1.py", "old_string": "a", "new_string": "b"}', result
        )
        agent._record_tool_call(
            "edit", '{"file_path": "file2.py", "old_string": "a", "new_string": "b"}', result
        )
        agent._record_tool_call(
            "edit", '{"file_path": "file1.py", "old_string": "c", "new_string": "d"}', result
        )

        assert agent._edit_count_per_file.get("file1.py") == 2
        assert agent._edit_count_per_file.get("file2.py") == 1

    def test_failed_edit_does_not_increment_count(self, agent):
        """Failed edits should not increment the count."""
        args = '{"file_path": "test.py", "old_string": "a", "new_string": "b"}'
        result = ToolResult(success=False, output="", error="Failed")

        agent._record_tool_call("edit", args, result)

        assert agent._edit_count_per_file.get("test.py") is None


class TestExcessiveEditWarning:
    """Test excessive edit warning/rejection generation."""

    def test_no_warning_below_threshold(self, agent):
        """No warning should be generated below threshold (threshold=2)."""
        # Threshold is 2, so 1 edit should not trigger warning
        agent._edit_count_per_file["test.py"] = 1
        warning = agent._check_excessive_edits("test.py")
        assert warning is None

    def test_warning_at_threshold(self, agent):
        """Warning should be generated at threshold (threshold=2)."""
        # Threshold is 2, so 2 edits should trigger warning
        agent._edit_count_per_file["test.py"] = 2

        warning = agent._check_excessive_edits("test.py")

        assert warning is not None
        assert "CRITICAL VIOLATION" in warning
        assert "2" in warning
        assert "edits" in warning.lower()

    def test_warning_above_threshold(self, agent):
        """Warning should be generated above threshold."""
        agent._edit_count_per_file["test.py"] = 10

        warning = agent._check_excessive_edits("test.py")

        assert warning is not None
        assert "10" in warning

    def test_warning_suggests_solutions(self, agent):
        """Warning should suggest alternative approaches."""
        agent._edit_count_per_file["test.py"] = 5

        warning = agent._check_excessive_edits("test.py")

        # Should suggest using edits array for batched edits
        assert "edits" in warning.lower()
        # Note: we no longer suggest write_file, only batched edits
        assert "CORRECT PATTERN" in warning


class TestExecuteSingleToolCall:
    """Test that edits are rejected after threshold."""

    @pytest.mark.asyncio
    async def test_edit_rejected_after_threshold(self, agent, mock_tools):
        """Edit should be REJECTED after threshold is reached."""
        # Set up excessive edits (threshold is 2, so 1 edit already done)
        agent._edit_count_per_file["test.py"] = 1

        # Mock tool execution (this shouldn't be called due to rejection)
        original_result = ToolResult(success=True, output="Edit successful")
        mock_tools.execute = AsyncMock(return_value=original_result)
        agent.tools = mock_tools

        # Create mock tool call
        tool_call = MockToolCall(
            id="1",
            function=MockFunction(
                name="edit",
                arguments='{"file_path": "test.py", "old_string": "a", "new_string": "b"}',
            ),
        )

        # Execute - this should be REJECTED (2nd edit)
        name, args, result = await agent._execute_single_tool_call(tool_call)

        # Verify edit was rejected
        assert result.success is False
        assert "EDIT REJECTED" in result.error
        assert "edits" in result.error.lower()

    @pytest.mark.asyncio
    async def test_no_warning_for_other_tools(self, agent, mock_tools):
        """Non-edit tools should not trigger warning."""
        # Mock tool execution
        original_result = ToolResult(success=True, output="File content")
        mock_tools.execute = AsyncMock(return_value=original_result)
        agent.tools = mock_tools

        # Create mock tool call
        tool_call = MockToolCall(
            id="1", function=MockFunction(name="read_file", arguments='{"path": "test.py"}')
        )

        # Execute
        name, args, result = await agent._execute_single_tool_call(tool_call)

        # Verify no warning
        assert "WARNING" not in result.output

    @pytest.mark.asyncio
    async def test_no_warning_for_failed_edit(self, agent, mock_tools):
        """Failed edits should not show excessive edit warning."""
        agent._edit_count_per_file["test.py"] = 10

        # Mock tool execution with failure
        original_result = ToolResult(success=False, output="", error="Not found")
        mock_tools.execute = AsyncMock(return_value=original_result)
        agent.tools = mock_tools

        # Create mock tool call
        tool_call = MockToolCall(
            id="1",
            function=MockFunction(
                name="edit",
                arguments='{"file_path": "test.py", "old_string": "a", "new_string": "b"}',
            ),
        )

        # Execute
        name, args, result = await agent._execute_single_tool_call(tool_call)

        # Verify no warning (since edit failed)
        assert result.output == ""
        assert result.error == "Not found"
