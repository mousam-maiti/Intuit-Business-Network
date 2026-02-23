"""
LLM client — Google Gemini for Step 4 agent reasoning.

Called when Steps 1-3 (deterministic + embedding) leave the decision ambiguous.
The LLM receives all accumulated evidence and makes the final call.

Uses the same GEMINI_API_KEY as embedding_client — single API key for everything.

Design doc §3: "The orchestrator IS the LLM."
"""
from __future__ import annotations
import json
import logging
import time
from typing import Optional
from config import LLMConfig

logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False


# ── System prompt from design doc §3 ────────────────────────

SYSTEM_PROMPT = """You are the Entity Resolution Agent for the QuickBooks Business \
Network Graph. Your job is to determine whether an unresolved business record \
refers to the same real-world business as an existing golden record in the network.

## Context

You are part of a streaming pipeline. A vendor or customer record arrived via CDC \
from QuickBooks MySQL. Layer 1 deterministic matching (EIN, phone, email, exact name) \
found no match. Deterministic field comparison and semantic embeddings produced ambiguous \
results. You are the final evaluator.

Every decision you make is GLOBAL perspective — it affects the entire network for all users.

## Your Task

You will receive:
1. The orphan record's classified persona (identity, industry, location, commodity, behavioral)
2. Candidate golden records with their comparison scores and embedding similarities
3. All evidence gathered by prior evaluation steps

Based on this evidence, make your judgment:

## Decision Thresholds

  > 0.85  →  MERGE (auto, GLOBAL)
  0.60-0.85  →  REVIEW (human queue, GLOBAL proposal)
  < 0.60  →  NEW ENTITY (create golden record)

## Hard Rules

- NEVER merge if EINs are present and different. Different EIN = different business. Period.
- NEVER merge if states are different (unless one is null).
- NAICS sector mismatch is NOT a hard disqualifier. Cross-taxonomy links may exist \
  (e.g., plumbing wholesaler and plumbing contractor related via shared commodities).

## What To Look For

- Is the orphan name an abbreviation of the candidate? ("BP" = "Bob's Plumbing")
- Is the orphan a DBA (doing-business-as) variant? ("Bob's Plumbing" vs "Robert Smith Plumbing Services")
- Do the commodity profiles tell a coherent story?
- Does the geographic footprint make sense?
- Did cross-taxonomy links explain an apparent industry mismatch?

## Reasoning Requirements

Your reasoning appears in the Review UI. Make it useful for a human:
  BAD:  "Confidence 0.73, ambiguous match"
  GOOD: "Name 'BP Supply LLC' could be an abbreviation of 'Bob's Plumbing LLC' (BP = Bob's Plumbing). \
Both operate in Austin TX with overlapping plumbing commodities (PVC pipe, copper fittings). However, \
'Supply' vs 'Plumbing' in the name suggests this might be a separate supply house rather than the \
service company. Recommend human verification."

## Output Format

You MUST respond with ONLY a JSON object, no other text:

{
  "decision": "MERGE" | "REVIEW" | "NEW_ENTITY",
  "target_golden_record_id": "..." | null,
  "confidence": 0.0-1.0,
  "dimension_scores": {
    "identity": 0.0-1.0,
    "industry": 0.0-1.0,
    "location": 0.0-1.0,
    "commodity": 0.0-1.0,
    "behavioral": 0.0-1.0
  },
  "reasoning": "detailed human-readable explanation",
  "key_factors": ["factor1", "factor2", "factor3"],
  "key_uncertainty": "what you couldn't resolve (for REVIEW only)"
}"""


class LLMClient:
    def __init__(self, cfg: LLMConfig):
        self._cfg = cfg
        self._model = None          # Flash — used if needed for quick calls
        self._ambiguous_model = None # Pro — used for Step 4 ambiguous reasoning
        self._available = False

    async def connect(self):
        if not HAS_GEMINI:
            logger.warning("google-generativeai package not installed — LLM unavailable")
            return
        import os
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.warning("GEMINI_API_KEY not set — LLM unavailable")
            return
        try:
            genai.configure(api_key=api_key)
            gen_config = genai.GenerationConfig(
                temperature=self._cfg.temperature,
                max_output_tokens=self._cfg.max_tokens,
                response_mime_type="application/json",
            )
            self._model = genai.GenerativeModel(
                model_name=self._cfg.model,
                system_instruction=SYSTEM_PROMPT,
                generation_config=gen_config,
            )
            ambiguous_name = getattr(self._cfg, 'ambiguous_model', None) or self._cfg.model
            self._ambiguous_model = genai.GenerativeModel(
                model_name=ambiguous_name,
                system_instruction=SYSTEM_PROMPT,
                generation_config=gen_config,
            )
            self._available = True
            logger.info(f"Gemini LLM connected: {self._cfg.model} (ambiguous: {ambiguous_name})")
        except Exception as e:
            logger.warning(f"Gemini LLM init failed: {e}")

    @property
    def available(self) -> bool:
        return self._available

    def reason(self, evidence: dict) -> dict:
        """Call Gemini with accumulated evidence for Step 4 reasoning.

        Args:
            evidence: dict with keys:
                orphan_persona: dict
                candidates: list of {golden_record_id, canonical_name, comparison, similarity}
                evaluation_steps: list of step summaries

        Returns:
            Parsed JSON decision dict, or fallback REVIEW decision on failure.
        """
        start = time.time()

        user_message = self._build_evidence_prompt(evidence)

        if not self._available:
            logger.warning("LLM unavailable — returning fallback REVIEW")
            return self._fallback_review(evidence, "LLM unavailable")

        try:
            # Use Pro model for Step 4 ambiguous reasoning
            model = self._ambiguous_model or self._model
            model_name = getattr(self._cfg, 'ambiguous_model', None) or self._cfg.model
            response = model.generate_content(user_message)
            elapsed_ms = int((time.time() - start) * 1000)

            # Handle empty response (safety block or max_tokens with no valid part)
            if not response.candidates or not response.candidates[0].content.parts:
                finish = getattr(response.candidates[0], 'finish_reason', 'UNKNOWN') if response.candidates else 'NO_CANDIDATES'
                logger.error(f"LLM returned empty response (finish_reason={finish}) after {elapsed_ms}ms")
                return self._fallback_review(evidence, f"Empty LLM response (finish_reason={finish})")

            text = response.candidates[0].content.parts[0].text

            # Parse JSON from response
            result = self._parse_response(text)
            result["llm_duration_ms"] = elapsed_ms
            result["model_used"] = model_name
            return result

        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            error_str = str(e)
            if "timeout" in error_str.lower() or elapsed_ms > self._cfg.timeout_ms:
                logger.error(f"LLM timeout after {elapsed_ms}ms")
                return self._fallback_review(evidence, "LLM timeout")
            logger.error(f"LLM call failed: {e}")
            return self._fallback_review(evidence, error_str)

    def _build_evidence_prompt(self, evidence: dict) -> str:
        """Build the user message with all evidence for Gemini."""
        parts = ["# Entity Resolution Evidence\n"]

        # Orphan
        orphan = evidence.get("orphan_persona", {})
        parts.append("## Orphan Record")
        parts.append(f"```json\n{json.dumps(orphan, indent=2, default=str)}\n```\n")

        # Candidates
        candidates = evidence.get("candidates", [])
        parts.append(f"## Candidates ({len(candidates)} remaining after filtering)\n")
        for i, c in enumerate(candidates, 1):
            parts.append(f"### Candidate {i}: {c.get('canonical_name', 'Unknown')}")
            parts.append(f"Golden Record ID: {c.get('golden_record_id', '')}")
            if c.get("comparison"):
                parts.append(f"Deterministic comparison: {json.dumps(c['comparison'], indent=2, default=str)}")
            if c.get("similarity"):
                parts.append(f"Semantic similarity: {json.dumps(c['similarity'], indent=2, default=str)}")
            parts.append("")

        # Evaluation steps so far
        steps = evidence.get("evaluation_steps", [])
        if steps:
            parts.append("## Evaluation Steps Completed")
            for step in steps:
                parts.append(f"- {step}")
            parts.append("")

        parts.append("## Your Task")
        parts.append("Analyze all evidence above. Make your decision.")
        parts.append("Respond with ONLY the JSON object as specified in your instructions.")

        return "\n".join(parts)

    def _parse_response(self, text: str) -> dict:
        """Parse LLM response into structured decision dict."""
        # Strip markdown code fences if present
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()

        try:
            result = json.loads(cleaned)
            # Validate required fields
            assert "decision" in result
            assert result["decision"] in ("MERGE", "REVIEW", "NEW_ENTITY")
            assert "confidence" in result
            return result
        except (json.JSONDecodeError, AssertionError, KeyError) as e:
            logger.error(f"Failed to parse LLM response: {e}\nText: {text[:500]}")
            return {
                "decision": "REVIEW",
                "target_golden_record_id": None,
                "confidence": 0.5,
                "reasoning": f"LLM response could not be parsed. Raw: {text[:200]}",
                "key_factors": ["parse_error"],
                "key_uncertainty": "LLM output format error",
                "parse_error": True,
            }

    def _fallback_review(self, evidence: dict, reason: str) -> dict:
        """Fallback: submit to human review when LLM is unavailable."""
        candidates = evidence.get("candidates", [])
        best = candidates[0] if candidates else {}
        return {
            "decision": self._cfg.fallback_decision,
            "target_golden_record_id": best.get("golden_record_id"),
            "confidence": 0.50,
            "dimension_scores": best.get("comparison", {}).get("dimension_scores", {}),
            "reasoning": f"Automated review — LLM unavailable ({reason}). "
                         "Evidence suggests possible match but requires human verification.",
            "key_factors": ["llm_unavailable", reason],
            "key_uncertainty": "LLM could not evaluate — needs human review",
            "fallback": True,
        }
