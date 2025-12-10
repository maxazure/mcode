"""Tests for tool base classes and registry"""

import json
import pytest
from typing import Any

from maxagent.tools.base import BaseTool, ToolParameter, ToolResult


class MockTool(BaseTool):
    """Mock tool for testing"""

    name = "mock_tool"
    description = "A mock tool for testing"
    parameters = [
        ToolParameter(
            name="required_param",
            type="string",
            description="A required parameter",
            required=True,
        ),
        ToolParameter(
            name="optional_param",
            type="integer",
            description="An optional parameter",
            required=False,
            default=10,
        ),
        ToolParameter(
            name="enum_param",
            type="string",
            description="An enum parameter",
            required=False,
            enum=["option1", "option2", "option3"],
        ),
    ]
    risk_level = "low"

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the mock tool"""
        return ToolResult(
            success=True,
            output=f"Executed with: {kwargs}",
            metadata={"params": kwargs},
        )


class TestToolParameter:
    """Test ToolParameter dataclass"""

    def test_default_values(self):
        """Test default parameter values"""
        param = ToolParameter(
            name="test",
            type="string",
            description="A test parameter",
        )
        assert param.required is True
        assert param.enum is None
        assert param.default is None

    def test_all_values(self):
        """Test parameter with all values set"""
        param = ToolParameter(
            name="test",
            type="string",
            description="A test parameter",
            required=False,
            enum=["a", "b"],
            default="a",
        )
        assert param.name == "test"
        assert param.type == "string"
        assert param.description == "A test parameter"
        assert param.required is False
        assert param.enum == ["a", "b"]
        assert param.default == "a"


class TestToolResult:
    """Test ToolResult dataclass"""

    def test_success_result(self):
        """Test successful result"""
        result = ToolResult(success=True, output="test output")
        assert result.success is True
        assert result.output == "test output"
        assert result.error is None
        assert result.metadata == {}

    def test_error_result(self):
        """Test error result"""
        result = ToolResult(
            success=False,
            output="",
            error="Something went wrong",
            metadata={"code": 500},
        )
        assert result.success is False
        assert result.output == ""
        assert result.error == "Something went wrong"
        assert result.metadata == {"code": 500}


class TestBaseTool:
    """Test BaseTool class"""

    def test_tool_attributes(self):
        """Test tool attributes"""
        tool = MockTool()
        assert tool.name == "mock_tool"
        assert tool.description == "A mock tool for testing"
        assert len(tool.parameters) == 3
        assert tool.risk_level == "low"

    @pytest.mark.asyncio
    async def test_execute(self):
        """Test tool execution"""
        tool = MockTool()
        result = await tool.execute(required_param="test", optional_param=20)

        assert result.success is True
        assert "required_param" in result.output
        assert result.metadata["params"]["required_param"] == "test"
        assert result.metadata["params"]["optional_param"] == 20

    def test_to_openai_schema(self):
        """Test conversion to OpenAI schema"""
        tool = MockTool()
        schema = tool.to_openai_schema()

        assert schema["type"] == "function"
        assert schema["function"]["name"] == "mock_tool"
        assert schema["function"]["description"] == "A mock tool for testing"

        params = schema["function"]["parameters"]
        assert params["type"] == "object"

        # Check properties
        properties = params["properties"]
        assert "required_param" in properties
        assert properties["required_param"]["type"] == "string"
        assert properties["required_param"]["description"] == "A required parameter"

        assert "optional_param" in properties
        assert properties["optional_param"]["type"] == "integer"
        assert properties["optional_param"]["default"] == 10

        assert "enum_param" in properties
        assert properties["enum_param"]["enum"] == ["option1", "option2", "option3"]

        # Check required list
        assert params["required"] == ["required_param"]


class TestToolSchemaFormat:
    """Test OpenAI tool schema format compliance"""

    def test_schema_structure(self):
        """Test schema has correct structure"""
        tool = MockTool()
        schema = tool.to_openai_schema()

        # Top level keys
        assert set(schema.keys()) == {"type", "function"}

        # Function keys
        func = schema["function"]
        assert set(func.keys()) == {"name", "description", "parameters"}

        # Parameters keys
        params = func["parameters"]
        assert set(params.keys()) == {"type", "properties", "required"}

    def test_schema_is_json_serializable(self):
        """Test schema can be serialized to JSON"""
        tool = MockTool()
        schema = tool.to_openai_schema()

        # Should not raise
        json_str = json.dumps(schema)
        assert isinstance(json_str, str)

        # Should roundtrip correctly
        parsed = json.loads(json_str)
        assert parsed == schema
