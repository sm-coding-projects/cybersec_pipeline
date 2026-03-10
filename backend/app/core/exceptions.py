class ToolExecutionError(Exception):
    """A security tool failed to execute."""

    def __init__(self, tool: str, message: str, exit_code: int = -1) -> None:
        self.tool = tool
        self.exit_code = exit_code
        super().__init__(f"{tool} failed (exit {exit_code}): {message}")


class ScanNotFoundError(Exception):
    """Requested scan does not exist."""

    def __init__(self, scan_id: int) -> None:
        self.scan_id = scan_id
        super().__init__(f"Scan {scan_id} not found")


class AuthenticationError(Exception):
    """Authentication or authorization failure."""

    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(message)
