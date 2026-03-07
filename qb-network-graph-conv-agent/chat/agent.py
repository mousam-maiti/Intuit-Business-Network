"""
ConversationalAgent — ReAct (Reasoning + Acting) loop with MCP tools.

Core flow:
1. User message + conversation history → LLM (text generation, no function calling)
2. LLM returns Thought + Action → parse tool call → execute MCP tool → stream progress
3. Feed Observation back → repeat until LLM returns Answer
4. Parse JSON response → merge with formatter blocks → send to client
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Awaitable, Union

from json_repair import repair_json

from clients.mcp_client import MCPToolClient, MCPError
from chat.prompts import REACT_SYSTEM_PROMPT, TOOL_NAMES, TOOL_LABELS, TITLE_PROMPT
from chat.formatter import format_tool_result, merge_blocks
from chat.models import WSResponse, WSToolCall, WSThought

logger = logging.getLogger(__name__)

# Type for the progress callback: async fn(WSToolCall | WSThought) -> None
ProgressCallback = Callable[[Union[WSToolCall, WSThought]], Awaitable[None]]

# ── Regex patterns for parsing ReAct output ───────────────────
RE_THOUGHT = re.compile(r"^Thought:\s*(.+?)(?=\n(?:Action:|Answer:)|$)", re.DOTALL | re.MULTILINE)
RE_ACTION  = re.compile(r"^Action:\s*(\w+)\((.+)\)\s*$", re.MULTILINE)
RE_ANSWER  = re.compile(r"^Answer:\s*(.+)$", re.DOTALL | re.MULTILINE)

# Maximum chars for Observation text fed back to the model
_MAX_OBSERVATION_LEN = 4000


class ConversationalAgent:
    """ReAct-powered conversational agent with MCP tool integration."""

    def __init__(self, mcp: MCPToolClient, llm, max_iterations: int = 8):
        self.mcp = mcp
        self.llm = llm  # LLMProvider instance
        self.max_iterations = max_iterations

    async def handle_message(
        self,
        session: dict,
        user_message: str,
        ui_context: dict | None,
        history: list[dict],
        progress_callback: ProgressCallback | None = None,
    ) -> WSResponse:
        """Process a user message through the ReAct loop.

        Args:
            session: Chat session dict
            user_message: The user's message text
            ui_context: Optional UI context (selectedEntity, currentPage)
            history: Assembled conversation history for Gemini
            progress_callback: Async callback to stream tool_call / thought events

        Returns:
            WSResponse with all UI blocks
        """
        # Build system instruction with optional UI context
        system = REACT_SYSTEM_PROMPT
        logger.info(f"ui_context received: {ui_context}")
        if ui_context:
            entity = ui_context.get("selectedEntity")
            page = ui_context.get("currentPage")
            if entity:
                company_id = entity.get("id", "")
                entity_name = entity.get("name", entity.get("id", ""))
                system += f"\n\nCurrent UI context: company_id='{company_id}', company_name='{entity_name}', page='{page or 'unknown'}'."
                system += f"\nWhen the user asks about 'my vendors', 'my customers', or 'my network', use company_id='{company_id}' with the get_company_connections tool."

        # ── ReAct loop ────────────────────────────────────────
        all_formatter_blocks: dict[str, Any] = {}
        current_prompt = user_message
        iteration = 0
        # Maintain growing chat history for multi-turn
        chat_history = list(history)

        for iteration in range(1, self.max_iterations + 1):
            try:
                text = self.llm.chat(chat_history, current_prompt, system=system)
            except Exception as e:
                err_str = str(e)
                logger.warning(f"ReAct iter {iteration}: chat error: {err_str}")
                if "MALFORMED_FUNCTION_CALL" in err_str.upper() or "content {" in err_str:
                    current_prompt = (
                        "You must NOT use function calling. Instead, use the ReAct text format:\n"
                        "Thought: <reasoning>\n"
                        "Action: tool_name({\"arg\": \"value\"})\n\n"
                        "Please try again with the correct format."
                    )
                    continue
                raise

            # Append the exchange to chat history for next iteration
            chat_history.append({"role": "user", "parts": [current_prompt]})
            chat_history.append({"role": "assistant", "parts": [text]})

            if not text.strip():
                logger.warning(f"ReAct iter {iteration}: empty response from model, nudging")
                current_prompt = "Observation: (empty response) — please continue with a Thought and Action, or provide your final Answer."
                continue

            logger.info(f"ReAct iter {iteration} raw:\n{text[:800]}")

            # Check for final Answer (use LAST match — model sometimes drafts multiple)
            answer_matches = list(RE_ANSWER.finditer(text))
            if answer_matches:
                answer_match = answer_matches[-1]
                # Stream any final thought before the answer
                thought_match = RE_THOUGHT.search(text)
                if thought_match and progress_callback:
                    await progress_callback(WSThought(
                        text=thought_match.group(1).strip(), step=iteration,
                    ))

                final_text = answer_match.group(1).strip()
                gemini_blocks = self._parse_response(final_text)
                break

            # Extract Thought
            thought_match = RE_THOUGHT.search(text)
            if thought_match and progress_callback:
                await progress_callback(WSThought(
                    text=thought_match.group(1).strip(), step=iteration,
                ))

            # Extract Action
            action_match = RE_ACTION.search(text)
            if not action_match:
                # No valid Action or Answer — model is rambling without ReAct format.
                # Give it one chance to produce a proper Answer, otherwise force-extract on next miss.
                if iteration >= self.max_iterations - 1:
                    # Last iteration — force as final answer, stripping obvious reasoning
                    logger.warning(f"ReAct iter {iteration}: no Action/Answer on final iter, forcing")
                    gemini_blocks = self._parse_response(text)
                    break
                logger.warning(f"ReAct iter {iteration}: no Action or Answer found, nudging model")
                current_prompt = (
                    "You did not follow the ReAct format. You MUST respond with either:\n"
                    "1. Thought: <reasoning>\\nAction: tool_name({\"arg\": \"value\"})\n"
                    "2. Thought: <summary>\\nAnswer: {\"content\": \"your response\", ...}\n\n"
                    "If you have enough information, provide your final Answer now as a JSON object."
                )
                continue

            tool_name = action_match.group(1)
            raw_args = action_match.group(2)

            # Validate tool name
            if tool_name not in TOOL_NAMES:
                logger.warning(f"Unknown tool: {tool_name}")
                current_prompt = f"Observation: Error — unknown tool '{tool_name}'. Available tools: {', '.join(sorted(TOOL_NAMES))}"
                continue

            tool_args = self._parse_action_args(raw_args)
            logger.info(f"ReAct iter {iteration}: {tool_name}({tool_args})")

            # Stream tool running
            if progress_callback:
                label = TOOL_LABELS.get(tool_name, f"Running {tool_name}")
                await progress_callback(WSToolCall(
                    name=tool_name, status="running", label=label,
                ))

            # Execute MCP tool
            try:
                result = await self.mcp.call_tool(tool_name, tool_args)
                result_str = json.dumps(result) if isinstance(result, dict) else str(result)
                logger.info(f"MCP result ({tool_name}): {result_str[:300]}")

                # Format result into UI blocks
                if isinstance(result, dict):
                    blocks = format_tool_result(tool_name, result)
                    all_formatter_blocks = merge_blocks(blocks, all_formatter_blocks)

                # Stream tool done
                if progress_callback:
                    preview = result_str[:200] + "..." if len(result_str) > 200 else result_str
                    await progress_callback(WSToolCall(
                        name=tool_name, status="done",
                        label=TOOL_LABELS.get(tool_name, ""),
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

            # Truncate observation if needed
            if len(result_str) > _MAX_OBSERVATION_LEN:
                result_str = result_str[:_MAX_OBSERVATION_LEN] + "... (truncated)"

            current_prompt = f"Observation: {result_str}"

        else:
            # Max iterations exhausted — force a final answer
            logger.warning(f"ReAct loop exhausted {self.max_iterations} iterations, forcing answer")
            force_prompt = (
                "You have reached the maximum number of iterations. "
                "Based on all the information gathered so far, provide your final Answer now.\n\n"
                "Answer:"
            )
            final_text = self.llm.chat(chat_history, force_prompt, system=system)
            # Strip leading "Answer:" if model echoes it
            if final_text.strip().startswith("Answer:"):
                final_text = final_text.strip()[7:].strip()
            gemini_blocks = self._parse_response(final_text)

        # Merge Gemini blocks with formatter blocks
        merged = merge_blocks(gemini_blocks, all_formatter_blocks)

        # Sanitize table rows — Gemini may return ints/floats instead of strings
        table = merged.get("table")
        if table and isinstance(table, dict):
            table["rows"] = [[str(cell) for cell in row] for row in table.get("rows", [])]
            table["headers"] = [str(h) for h in table.get("headers", [])]

        # Sanitize chart — LLM sometimes returns graph-shaped data instead of [{name, value}]
        chart = merged.get("chart")
        if chart and isinstance(chart, dict):
            if not isinstance(chart.get("data"), list):
                chart = None

        return WSResponse(
            content=merged.get("content", ""),
            entities=merged.get("entities"),
            table=table,
            chart=chart,
            scores=merged.get("scores"),
            signals=merged.get("signals"),
            actions=merged.get("actions"),
            followup=merged.get("followup"),
            thought_steps=iteration,
        )

    async def generate_title(self, first_message: str) -> str:
        """Generate a short session title from the first message."""
        try:
            prompt = TITLE_PROMPT.format(message=first_message)
            title = self.llm.generate(prompt).strip().strip('"').strip("'")
            if len(title) > 80:
                title = title[:77] + "..."
            return title
        except Exception as e:
            logger.warning(f"Title generation failed: {e}")
            return first_message[:50] + ("..." if len(first_message) > 50 else "")

    @staticmethod
    def _parse_action_args(raw: str) -> dict:
        """Parse Action arguments with 3-tier fallback: json.loads → json-repair → {}."""
        raw = raw.strip()
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            pass

        try:
            repaired = repair_json(raw, return_objects=True)
            if isinstance(repaired, dict):
                return repaired
        except Exception:
            pass

        logger.warning(f"Could not parse action args: {raw[:200]}")
        return {}

    @staticmethod
    def _parse_response(text: str) -> dict:
        """Parse Gemini's response as JSON with 3-tier fallback: json.loads → json-repair → plain text."""
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

        # Tier 1: direct parse
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict) and "content" in parsed:
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass

        # Tier 2: json-repair
        try:
            repaired = repair_json(stripped, return_objects=True)
            if isinstance(repaired, dict) and "content" in repaired:
                return repaired
        except Exception:
            pass

        # Tier 3: plain text fallback
        return {"content": text}
