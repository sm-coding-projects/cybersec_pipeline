"""Tests for pipeline utility functions — retry logic, output validation, timeouts."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import ToolExecutionError
from app.pipeline.utils import (
    ToolTimeout,
    _is_transient_error,
    exec_with_timeout,
    retry_tool_exec,
    validate_tool_output,
)


# ── _is_transient_error tests ──────────────────────────────────────


class TestIsTransientError:
    """Tests for transient error detection."""

    def test_connection_refused_is_transient(self):
        err = ToolExecutionError(tool="test", message="Connection refused by host")
        assert _is_transient_error(err) is True

    def test_timeout_is_transient(self):
        err = ToolExecutionError(tool="test", message="Request timed out")
        assert _is_transient_error(err) is True

    def test_container_not_running_is_transient(self):
        err = ToolExecutionError(tool="test", message="container not running or paused")
        assert _is_transient_error(err) is True

    def test_not_found_is_running_is_transient(self):
        err = ToolExecutionError(tool="test", message="Container 'nmap' not found. Is it running?")
        assert _is_transient_error(err) is True

    def test_oom_exit_code_is_transient(self):
        err = ToolExecutionError(tool="test", message="killed", exit_code=137)
        assert _is_transient_error(err) is True

    def test_sigterm_exit_code_is_transient(self):
        err = ToolExecutionError(tool="test", message="terminated", exit_code=143)
        assert _is_transient_error(err) is True

    def test_container_startup_failure_is_transient(self):
        err = ToolExecutionError(tool="test", message="failed to start", exit_code=125)
        assert _is_transient_error(err) is True

    def test_normal_error_is_not_transient(self):
        err = ToolExecutionError(tool="test", message="invalid argument: --bad-flag", exit_code=2)
        assert _is_transient_error(err) is False

    def test_generic_exception_not_transient(self):
        err = ValueError("something went wrong")
        assert _is_transient_error(err) is False

    def test_generic_exception_with_timeout_keyword_is_transient(self):
        err = Exception("Operation timed out waiting for response")
        assert _is_transient_error(err) is True

    def test_docker_api_error_is_transient(self):
        err = Exception("Docker API error during execution")
        assert _is_transient_error(err) is True


# ── retry_tool_exec tests ──────────────────────────────────────────


class TestRetryToolExec:
    """Tests for the retry_tool_exec utility."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self):
        """Should return immediately when the command succeeds."""
        docker = AsyncMock()
        docker.exec_in_container = AsyncMock(return_value=(0, "success output"))

        exit_code, output = await retry_tool_exec(
            docker=docker,
            container="test-container",
            command="echo hello",
            max_retries=2,
            delay=0.01,
        )

        assert exit_code == 0
        assert output == "success output"
        assert docker.exec_in_container.call_count == 1

    @pytest.mark.asyncio
    async def test_success_after_transient_failure(self):
        """Should retry on transient errors and succeed."""
        docker = AsyncMock()
        docker.exec_in_container = AsyncMock(
            side_effect=[
                ToolExecutionError(tool="test", message="Connection refused", exit_code=-1),
                (0, "success on retry"),
            ]
        )

        exit_code, output = await retry_tool_exec(
            docker=docker,
            container="test-container",
            command="nmap -sV target",
            max_retries=2,
            delay=0.01,
        )

        assert exit_code == 0
        assert output == "success on retry"
        assert docker.exec_in_container.call_count == 2

    @pytest.mark.asyncio
    async def test_non_transient_error_raises_immediately(self):
        """Non-transient ToolExecutionError should not be retried."""
        docker = AsyncMock()
        docker.exec_in_container = AsyncMock(
            side_effect=ToolExecutionError(tool="test", message="Invalid argument --xyz", exit_code=2),
        )

        with pytest.raises(ToolExecutionError, match="Invalid argument"):
            await retry_tool_exec(
                docker=docker,
                container="test-container",
                command="bad command",
                max_retries=2,
                delay=0.01,
            )

        # Should have been called only once — no retry
        assert docker.exec_in_container.call_count == 1

    @pytest.mark.asyncio
    async def test_all_retries_exhausted(self):
        """Should raise the last error after all retries are exhausted."""
        docker = AsyncMock()
        docker.exec_in_container = AsyncMock(
            side_effect=ToolExecutionError(tool="test", message="Connection refused", exit_code=-1),
        )

        with pytest.raises(ToolExecutionError, match="Connection refused"):
            await retry_tool_exec(
                docker=docker,
                container="test-container",
                command="failing command",
                max_retries=2,
                delay=0.01,
            )

        # 1 initial + 2 retries = 3 total calls
        assert docker.exec_in_container.call_count == 3

    @pytest.mark.asyncio
    async def test_non_zero_exit_non_transient_returns_result(self):
        """Non-zero exit code with non-transient error should return the result."""
        docker = AsyncMock()
        docker.exec_in_container = AsyncMock(return_value=(2, "usage error: bad flag"))

        exit_code, output = await retry_tool_exec(
            docker=docker,
            container="test-container",
            command="tool --bad-flag",
            max_retries=2,
            delay=0.01,
        )

        assert exit_code == 2
        assert "bad flag" in output
        assert docker.exec_in_container.call_count == 1

    @pytest.mark.asyncio
    async def test_non_zero_exit_transient_retries(self):
        """Non-zero exit code with transient error pattern should retry."""
        docker = AsyncMock()
        docker.exec_in_container = AsyncMock(
            side_effect=[
                (137, "container killed by OOM"),
                (0, "success"),
            ]
        )

        exit_code, output = await retry_tool_exec(
            docker=docker,
            container="test-container",
            command="heavy tool",
            max_retries=2,
            delay=0.01,
        )

        assert exit_code == 0
        assert output == "success"
        assert docker.exec_in_container.call_count == 2

    @pytest.mark.asyncio
    async def test_timeout_parameter_passed_through(self):
        """The timeout parameter should be passed to exec_in_container."""
        docker = AsyncMock()
        docker.exec_in_container = AsyncMock(return_value=(0, "ok"))

        await retry_tool_exec(
            docker=docker,
            container="test",
            command="cmd",
            timeout=999,
            delay=0.01,
        )

        call_kwargs = docker.exec_in_container.call_args
        assert call_kwargs.kwargs.get("timeout") == 999 or call_kwargs[1].get("timeout") == 999


# ── validate_tool_output tests ─────────────────────────────────────


class TestValidateToolOutput:
    """Tests for output file validation."""

    @pytest.mark.asyncio
    async def test_file_exists_and_nonempty(self):
        """Should return True when the file exists and is non-empty."""
        docker = AsyncMock()
        docker.exec_in_container = AsyncMock(return_value=(0, "EXISTS"))

        result = await validate_tool_output(
            docker=docker,
            container="nuclei",
            output_file="/results/scan/nuclei.jsonl",
            tool_name="nuclei",
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_file_missing_returns_false(self):
        """Should return False when the file is missing (non-required)."""
        docker = AsyncMock()
        docker.exec_in_container = AsyncMock(return_value=(0, "MISSING"))

        result = await validate_tool_output(
            docker=docker,
            container="nuclei",
            output_file="/results/scan/nuclei.jsonl",
            tool_name="nuclei",
            required=False,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_file_missing_required_raises(self):
        """Should raise ToolExecutionError when required file is missing."""
        docker = AsyncMock()
        docker.exec_in_container = AsyncMock(return_value=(0, "MISSING"))

        with pytest.raises(ToolExecutionError, match="missing or empty"):
            await validate_tool_output(
                docker=docker,
                container="nuclei",
                output_file="/results/scan/nuclei.jsonl",
                tool_name="nuclei",
                required=True,
            )

    @pytest.mark.asyncio
    async def test_exec_failure_returns_false(self):
        """Should return False on exec failure when not required."""
        docker = AsyncMock()
        docker.exec_in_container = AsyncMock(
            side_effect=ToolExecutionError(tool="nuclei", message="container gone"),
        )

        result = await validate_tool_output(
            docker=docker,
            container="nuclei",
            output_file="/results/scan/nuclei.jsonl",
            tool_name="nuclei",
            required=False,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_exec_failure_required_raises(self):
        """Should raise on exec failure when required."""
        docker = AsyncMock()
        docker.exec_in_container = AsyncMock(
            side_effect=ToolExecutionError(tool="nuclei", message="container gone"),
        )

        with pytest.raises(ToolExecutionError):
            await validate_tool_output(
                docker=docker,
                container="nuclei",
                output_file="/results/scan/nuclei.jsonl",
                tool_name="nuclei",
                required=True,
            )


# ── exec_with_timeout tests ───────────────────────────────────────


class TestExecWithTimeout:
    """Tests for the timeout wrapper."""

    @pytest.mark.asyncio
    async def test_success_within_timeout(self):
        """Should return normally when command completes within timeout."""
        docker = AsyncMock()
        docker.exec_in_container = AsyncMock(return_value=(0, "done"))

        exit_code, output = await exec_with_timeout(
            docker=docker,
            container="test",
            command="fast command",
            timeout=10,
        )

        assert exit_code == 0
        assert output == "done"

    @pytest.mark.asyncio
    async def test_timeout_raises_tool_timeout(self):
        """Should raise ToolTimeout when command exceeds timeout."""
        docker = AsyncMock()

        async def slow_exec(*args, **kwargs):
            await asyncio.sleep(100)
            return (0, "too late")

        docker.exec_in_container = slow_exec

        with pytest.raises(ToolTimeout) as exc_info:
            await exec_with_timeout(
                docker=docker,
                container="slow-tool",
                command="very slow scan",
                timeout=0,  # Immediate timeout (0 + 30 buffer = 30s wait_for, but asyncio will cancel quickly)
            )

        assert exc_info.value.tool == "slow-tool"

    @pytest.mark.asyncio
    async def test_timeout_exception_attributes(self):
        """ToolTimeout should have tool and timeout_seconds attributes."""
        exc = ToolTimeout(tool="nuclei", timeout_seconds=1800)
        assert exc.tool == "nuclei"
        assert exc.timeout_seconds == 1800
        assert "nuclei" in str(exc)
        assert "1800" in str(exc)
