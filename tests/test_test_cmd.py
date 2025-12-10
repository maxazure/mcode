"""Tests for test command and framework detection"""

import pytest
from pathlib import Path

from maxagent.cli.test_cmd import (
    TestFramework,
    TestFrameworkInfo,
    detect_test_framework,
    _find_test_dir,
    _find_config_file,
)


class TestTestFramework:
    """Test TestFramework enum"""

    def test_framework_values(self):
        """Test framework enum has correct values"""
        assert TestFramework.PYTEST.value == "pytest"
        assert TestFramework.UNITTEST.value == "unittest"
        assert TestFramework.JEST.value == "jest"
        assert TestFramework.VITEST.value == "vitest"
        assert TestFramework.MOCHA.value == "mocha"
        assert TestFramework.GO_TEST.value == "go_test"
        assert TestFramework.CARGO_TEST.value == "cargo_test"
        assert TestFramework.UNKNOWN.value == "unknown"


class TestHelperFunctions:
    """Test helper functions"""

    def test_find_test_dir(self, temp_dir):
        """Test finding test directory"""
        # No test dir exists
        result = _find_test_dir(temp_dir, ["tests", "test"])
        assert result is None

        # Create tests dir
        tests_dir = temp_dir / "tests"
        tests_dir.mkdir()
        result = _find_test_dir(temp_dir, ["tests", "test"])
        assert result == tests_dir

        # test dir (lower priority)
        test_dir = temp_dir / "test"
        test_dir.mkdir()
        result = _find_test_dir(temp_dir, ["tests", "test"])
        assert result == tests_dir  # still tests (higher priority)

    def test_find_config_file(self, temp_dir):
        """Test finding config file"""
        # No config exists
        result = _find_config_file(temp_dir, ["config.json", "config.yaml"])
        assert result is None

        # Create config file
        config_file = temp_dir / "config.yaml"
        config_file.write_text("key: value")
        result = _find_config_file(temp_dir, ["config.json", "config.yaml"])
        assert result == config_file


class TestDetectTestFramework:
    """Test detect_test_framework function"""

    def test_detect_pytest_ini(self, temp_dir):
        """Test detecting pytest via pytest.ini"""
        pytest_ini = temp_dir / "pytest.ini"
        pytest_ini.write_text("[pytest]\ntestpaths = tests")

        (temp_dir / "tests").mkdir()

        info = detect_test_framework(temp_dir)
        assert info.framework == TestFramework.PYTEST
        assert info.config_file == pytest_ini
        assert "pytest" in info.description

    def test_detect_pytest_pyproject(self, temp_dir):
        """Test detecting pytest via pyproject.toml"""
        pyproject = temp_dir / "pyproject.toml"
        pyproject.write_text(
            """
[project]
name = "test"

[tool.pytest.ini_options]
testpaths = ["tests"]
"""
        )

        (temp_dir / "tests").mkdir()

        info = detect_test_framework(temp_dir)
        assert info.framework == TestFramework.PYTEST
        assert info.config_file == pyproject
        assert "pyproject.toml" in info.description

    def test_detect_pytest_setup_cfg(self, temp_dir):
        """Test detecting pytest via setup.cfg"""
        setup_cfg = temp_dir / "setup.cfg"
        setup_cfg.write_text(
            """
[tool:pytest]
testpaths = tests
"""
        )

        (temp_dir / "tests").mkdir()

        info = detect_test_framework(temp_dir)
        assert info.framework == TestFramework.PYTEST
        assert info.config_file == setup_cfg
        assert "setup.cfg" in info.description

    def test_detect_unittest(self, temp_dir):
        """Test detecting unittest"""
        tests_dir = temp_dir / "tests"
        tests_dir.mkdir()

        test_file = tests_dir / "test_example.py"
        test_file.write_text(
            """
import unittest

class TestExample(unittest.TestCase):
    def test_something(self):
        pass
"""
        )

        info = detect_test_framework(temp_dir)
        assert info.framework == TestFramework.UNITTEST
        assert "unittest" in info.description

    def test_detect_jest(self, temp_dir):
        """Test detecting Jest"""
        package_json = temp_dir / "package.json"
        package_json.write_text(
            '{"devDependencies": {"jest": "^29.0.0"}, "scripts": {"test": "jest"}}'
        )

        (temp_dir / "tests").mkdir()

        info = detect_test_framework(temp_dir)
        assert info.framework == TestFramework.JEST
        assert "Jest" in info.description

    def test_detect_vitest(self, temp_dir):
        """Test detecting Vitest"""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"devDependencies": {"vitest": "^1.0.0"}}')

        (temp_dir / "tests").mkdir()

        info = detect_test_framework(temp_dir)
        assert info.framework == TestFramework.VITEST
        assert "Vitest" in info.description

    def test_detect_mocha(self, temp_dir):
        """Test detecting Mocha"""
        package_json = temp_dir / "package.json"
        package_json.write_text(
            '{"devDependencies": {"mocha": "^10.0.0"}, "scripts": {"test": "mocha"}}'
        )

        (temp_dir / "tests").mkdir()

        info = detect_test_framework(temp_dir)
        assert info.framework == TestFramework.MOCHA
        assert "Mocha" in info.description

    def test_detect_go_test(self, temp_dir):
        """Test detecting Go test"""
        go_mod = temp_dir / "go.mod"
        go_mod.write_text("module example.com/project\n\ngo 1.21")

        # Create a test file
        test_file = temp_dir / "main_test.go"
        test_file.write_text(
            """
package main

import "testing"

func TestSomething(t *testing.T) {}
"""
        )

        info = detect_test_framework(temp_dir)
        assert info.framework == TestFramework.GO_TEST
        assert "Go" in info.description

    def test_detect_cargo_test(self, temp_dir):
        """Test detecting Cargo test"""
        cargo_toml = temp_dir / "Cargo.toml"
        cargo_toml.write_text(
            """
[package]
name = "test"
version = "0.1.0"
"""
        )

        info = detect_test_framework(temp_dir)
        assert info.framework == TestFramework.CARGO_TEST
        assert "Rust" in info.description

    def test_detect_unknown(self, temp_dir):
        """Test detecting unknown framework"""
        # Empty directory with no recognizable files
        info = detect_test_framework(temp_dir)
        assert info.framework == TestFramework.UNKNOWN
        assert "No testing framework" in info.description


class TestTestFrameworkInfo:
    """Test TestFrameworkInfo dataclass"""

    def test_default_values(self):
        """Test default values"""
        info = TestFrameworkInfo(framework=TestFramework.PYTEST)
        assert info.config_file is None
        assert info.test_dir is None
        assert info.run_command == ""
        assert info.description == ""

    def test_with_values(self, temp_dir):
        """Test with all values"""
        tests_dir = temp_dir / "tests"
        tests_dir.mkdir()

        config_file = temp_dir / "pytest.ini"
        config_file.write_text("[pytest]")

        info = TestFrameworkInfo(
            framework=TestFramework.PYTEST,
            config_file=config_file,
            test_dir=tests_dir,
            run_command="pytest",
            description="pytest testing framework",
        )

        assert info.framework == TestFramework.PYTEST
        assert info.config_file == config_file
        assert info.test_dir == tests_dir
        assert info.run_command == "pytest"
        assert info.description == "pytest testing framework"
