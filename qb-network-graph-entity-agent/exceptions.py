from __future__ import annotations

"""Custom exception hierarchy for the Entity Resolution Agent."""


class AgentError(Exception):
    """Base exception for all agent errors."""

    def __init__(self, message: str, code: str = "AGENT_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class AgentNotInitializedError(AgentError):
    """Agent components not yet initialized."""

    def __init__(self, message: str = "Agent not initialized"):
        super().__init__(message, "AGENT_NOT_INITIALIZED")


class MCPUnavailableError(AgentError):
    """MCP server connection unavailable."""

    def __init__(self, message: str = "MCP server unavailable"):
        super().__init__(message, "MCP_UNAVAILABLE")


class LLMUnavailableError(AgentError):
    """LLM client unavailable."""

    def __init__(self, message: str = "LLM unavailable"):
        super().__init__(message, "LLM_UNAVAILABLE")


class ResolutionError(AgentError):
    """Error during entity resolution."""

    def __init__(self, record_id: str, detail: str = ""):
        msg = f"Resolution failed for {record_id}"
        if detail:
            msg += f": {detail}"
        super().__init__(msg, "RESOLUTION_FAILED")
        self.record_id = record_id


class ReEvaluationError(AgentError):
    """Error during golden record re-evaluation."""

    def __init__(self, golden_record_id: str, detail: str = ""):
        msg = f"Re-evaluation failed for {golden_record_id}"
        if detail:
            msg += f": {detail}"
        super().__init__(msg, "RE_EVALUATION_FAILED")
        self.golden_record_id = golden_record_id
