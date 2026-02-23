"""
ConversationalAgent — Gemini function calling + MCP tools.

Core flow:
1. User message + conversation history → Gemini
2. Gemini returns function_call → execute MCP tool → stream progress → feed result back
3. Repeat until Gemini returns a text response
4. Parse JSON response → merge with formatter blocks → send to client
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Awaitable

import google.generativeai as genai
from google.generativeai.types import content_types

from clients.mcp_client import MCPToolClient, MCPError
from chat.prompts import SYSTEM_PROMPT, TOOL_DECLARATIONS, TOOL_LABELS, TITLE_PROMPT
from chat.formatter import format_tool_result, merge_blocks
from chat.models import WSResponse, WSToolCall

logger = logging.getLogger(__name__)

# Type for the progress callback: async fn(WSToolCall) -> None
ProgressCallback = Callable[[WSToolCall], Awaitable[None]]


class ConversationalAgent:
    """Gemini-powered conversational agent with MCP tool integration."""

    def __init__(self, mcp: MCPToolClient, llm_model: str, temperature: float = 0.3,
                 max_tool_calls: int = 5):
        self.mcp = mcp
        self.llm_model = llm_model
        self.temperature = temperature
        self.max_tool_calls = max_tool_calls

    async def handle_message(
        self,
        session: dict,
        user_message: str,
        ui_context: dict | None,
        history: list[dict],
        progress_callback: ProgressCallback | None = None,
    ) -> WSResponse:
        """Process a user message through Gemini function calling loop.

        Args:
            session: Chat session dict
            user_message: The user's message text
            ui_context: Optional UI context (selectedEntity, currentPage)
            history: Assembled conversation history for Gemini
            progress_callback: Async callback to stream tool_call events

        Returns:
            WSResponse with all UI blocks
        """
        # Build Gemini tools
        tools = self._build_tools()

        # Build system instruction with optional UI context
        system = SYSTEM_PROMPT
        if ui_context:
            entity = ui_context.get("selectedEntity")
            page = ui_context.get("currentPage")
            if entity:
                entity_name = entity.get("name", entity.get("id", ""))
                system += f"\n\nCurrent UI context: The user is viewing entity '{entity_name}' (ID: {entity.get('id', '')}) on the {page or 'unknown'} page."

        # Create model with tools
        model = genai.GenerativeModel(
            model_name=self.llm_model,
            system_instruction=system,
            tools=tools,
            generation_config=genai.GenerationConfig(
                temperature=self.temperature,
            ),
        )

        # Start chat with history
        chat = model.start_chat(history=history)

        # Send user message and enter function calling loop
        all_formatter_blocks: dict[str, Any] = {}
        tool_call_count = 0

        response = chat.send_message(user_message)

        while tool_call_count < self.max_tool_calls:
            # Check if response has function calls
            part = response.candidates[0].content.parts[0]

            if not hasattr(part, "function_call") or not part.function_call.name:
                # Text response — done with tool calls
                break

            fc = part.function_call
            tool_name = fc.name
            tool_args = dict(fc.args) if fc.args else {}
            tool_call_count += 1

            logger.info(f"Tool call #{tool_call_count}: {tool_name}({tool_args})")

            # Stream progress to client
            if progress_callback:
                label = TOOL_LABELS.get(tool_name, f"Running {tool_name}")
                await progress_callback(WSToolCall(
                    name=tool_name, status="running", label=label,
                ))

            # Execute MCP tool
            try:
                result = await self.mcp.call_tool(tool_name, tool_args)
                result_str = json.dumps(result) if isinstance(result, dict) else str(result)

                # Format result into UI blocks
                if isinstance(result, dict):
                    blocks = format_tool_result(tool_name, result)
                    all_formatter_blocks = merge_blocks(blocks, all_formatter_blocks)

                # Stream tool completion
                if progress_callback:
                    preview = result_str[:200] + "..." if len(result_str) > 200 else result_str
                    await progress_callback(WSToolCall(
                        name=tool_name, status="done", label=TOOL_LABELS.get(tool_name, ""),
                        result_preview=preview,
                    ))

            except MCPError as e:
                logger.warning(f"MCP tool error: {e}")
                result_str = json.dumps({"error": str(e)})
                if progress_callback:
                    await progress_callback(WSToolCall(
                        name=tool_name, status="error",
                        label=f"Error: {str(e)[:100]}",
                    ))

            # Feed tool result back to Gemini
            response = chat.send_message(
                content_types.to_content(
                    genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=tool_name,
                            response={"result": result_str},
                        )
                    )
                )
            )

        # Parse final text response
        final_text = response.text if response.text else ""
        gemini_blocks = self._parse_response(final_text)

        # Merge Gemini blocks with formatter blocks
        merged = merge_blocks(gemini_blocks, all_formatter_blocks)

        # Sanitize table rows — Gemini may return ints/floats instead of strings
        table = merged.get("table")
        if table and isinstance(table, dict):
            table["rows"] = [[str(cell) for cell in row] for row in table.get("rows", [])]
            table["headers"] = [str(h) for h in table.get("headers", [])]

        return WSResponse(
            content=merged.get("content", final_text),
            entities=merged.get("entities"),
            table=table,
            chart=merged.get("chart"),
            scores=merged.get("scores"),
            signals=merged.get("signals"),
            actions=merged.get("actions"),
            followup=merged.get("followup"),
        )

    async def generate_title(self, first_message: str) -> str:
        """Generate a short session title from the first message."""
        try:
            model = genai.GenerativeModel(self.llm_model)
            prompt = TITLE_PROMPT.format(message=first_message)
            response = model.generate_content(prompt)
            title = response.text.strip().strip('"').strip("'")
            # Limit to reasonable length
            if len(title) > 80:
                title = title[:77] + "..."
            return title
        except Exception as e:
            logger.warning(f"Title generation failed: {e}")
            # Fallback: use first 50 chars of message
            return first_message[:50] + ("..." if len(first_message) > 50 else "")

    @staticmethod
    def _build_tools():
        """Build Gemini function declarations from TOOL_DECLARATIONS."""
        return [
            genai.protos.Tool(
                function_declarations=[
                    genai.protos.FunctionDeclaration(
                        name=td["name"],
                        description=td["description"],
                        parameters=genai.protos.Schema(
                            type=genai.protos.Type.OBJECT,
                            properties={
                                k: genai.protos.Schema(
                                    type=_map_type(v["type"]),
                                    description=v.get("description", ""),
                                )
                                for k, v in td["parameters"]["properties"].items()
                            },
                            required=td["parameters"].get("required", []),
                        ),
                    )
                    for td in TOOL_DECLARATIONS
                ]
            )
        ]

    @staticmethod
    def _parse_response(text: str) -> dict:
        """Try to parse Gemini's response as JSON, fall back to plain text."""
        if not text:
            return {"content": ""}

        # Try to extract JSON from the response
        stripped = text.strip()

        # Handle markdown code blocks
        if stripped.startswith("```json"):
            stripped = stripped[7:]
        elif stripped.startswith("```"):
            stripped = stripped[3:]
        if stripped.endswith("```"):
            stripped = stripped[:-3]
        stripped = stripped.strip()

        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict) and "content" in parsed:
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass

        # Plain text response
        return {"content": text}


def _map_type(type_str: str) -> int:
    """Map JSON schema type string to Gemini proto Type enum."""
    mapping = {
        "string": genai.protos.Type.STRING,
        "integer": genai.protos.Type.INTEGER,
        "number": genai.protos.Type.NUMBER,
        "boolean": genai.protos.Type.BOOLEAN,
        "array": genai.protos.Type.ARRAY,
        "object": genai.protos.Type.OBJECT,
    }
    return mapping.get(type_str, genai.protos.Type.STRING)
