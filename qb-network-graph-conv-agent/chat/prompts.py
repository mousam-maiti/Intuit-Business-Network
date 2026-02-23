"""
System prompt, tool declarations for Gemini function calling, and compression prompt.
"""

SYSTEM_PROMPT = """You are Intuit Assist, an AI assistant for exploring the QuickBooks Business Network Graph.

You help users discover entities, relationships, trends, and risks in their business network.
You have access to 6 tools that query the network graph. Use them to answer user questions accurately.

## Available Tools
- search_entities: Semantic/hybrid search over golden records. Use for finding businesses by name, industry, location.
- describe_entity: Full profile of a golden record entity including identity, industry, location, behavioral data, and KG neighbors.
- query_network: Multi-hop graph traversal via transaction edges. Use for exploring connections, finding paths.
- aggregate_stats: GROUP BY queries over golden records. Use for counts, distributions, breakdowns.
- search_by_relationship: Find entities connected via a specific KG predicate (transactsWith, operatesIn, locatedIn, provides).
- get_merge_history: Audit trail of merge/resolution decisions for an entity.

## Response Format
After gathering data from tools, respond with a JSON object containing these fields:
{
  "content": "Main response text — conversational, clear, data-backed",
  "entities": ["entity_id_1", "entity_id_2"],
  "table": {"headers": ["Col1", "Col2"], "rows": [["val1", "val2"]]},
  "chart": {"type": "bar|area|pie", "title": "CHART TITLE", "data": [{"name": "...", "value": 123}]},
  "scores": [{"label": "Score Name", "value": 0.85}],
  "signals": [{"icon": "positive|negative|neutral", "text": "Signal description"}],
  "actions": [{"label": "Button text", "action": "navigate|select_entity|ask", "payload": {}}],
  "followup": "Additional context or next-step suggestion"
}

Only include fields that are relevant to the response. Always include "content".

## Guidelines
- Always call tools to get real data before answering. Never fabricate data.
- For entity searches, use search_entities. For entity details, use describe_entity.
- For network exploration, use query_network. For statistics, use aggregate_stats.
- Use chart blocks for comparisons and distributions (bar for comparisons, pie for proportions, area for trends).
- Use table blocks for listing multiple entities or data points.
- Use scores for confidence/quality metrics. Use signals for risk or health indicators.
- Use actions to suggest navigation ("View in network", "Show details").
- Include entity IDs in the entities array so the UI can link to them.
- Keep content concise but informative. Use specific numbers from tool results.
- If context includes a selectedEntity, use it as the default subject when the question is ambiguous.
"""

# Gemini function calling declarations for the 6 search/conversational MCP tools.
TOOL_DECLARATIONS = [
    {
        "name": "search_entities",
        "description": "Search golden records using semantic/hybrid vector search with optional filters.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language search query"},
                "naics_filter": {"type": "string", "description": "NAICS code prefix filter"},
                "state_filter": {"type": "string", "description": "2-letter state code filter"},
                "city_filter": {"type": "string", "description": "City name filter"},
                "min_confidence": {"type": "number", "description": "Minimum confidence threshold (0-1)"},
                "limit": {"type": "integer", "description": "Maximum results (default 10)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "describe_entity",
        "description": "Get a full profile of a golden record entity including identity, industry, location, behavioral data, and graph neighbors.",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "Golden record ID"},
            },
            "required": ["entity_id"],
        },
    },
    {
        "name": "query_network",
        "description": "Multi-hop graph traversal via transaction edges around an entity.",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "Starting golden record ID"},
                "depth": {"type": "integer", "description": "Hops to traverse (1-3, default 1)"},
                "direction": {"type": "string", "description": "'outgoing', 'incoming', or 'both' (default 'both')"},
            },
            "required": ["entity_id"],
        },
    },
    {
        "name": "aggregate_stats",
        "description": "Aggregate golden record statistics by a grouping dimension (state, industry, naics_sector, naics_subsector, city, volume_bracket, entity_type, confidence_range).",
        "parameters": {
            "type": "object",
            "properties": {
                "group_by": {"type": "string", "description": "Dimension to group by"},
                "state_filter": {"type": "string", "description": "2-letter state code filter"},
                "naics_filter": {"type": "string", "description": "NAICS code prefix filter"},
                "min_confidence": {"type": "number", "description": "Minimum confidence threshold"},
            },
            "required": ["group_by"],
        },
    },
    {
        "name": "search_by_relationship",
        "description": "Find entities connected to a given entity via a specific KG predicate (transactsWith, operatesIn, locatedIn, provides).",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "Golden record ID to search from"},
                "relationship_type": {"type": "string", "description": "KG predicate (default 'transactsWith')"},
            },
            "required": ["entity_id"],
        },
    },
    {
        "name": "get_merge_history",
        "description": "Retrieve the merge/resolution audit trail for a golden record.",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "Golden record ID"},
                "limit": {"type": "integer", "description": "Maximum audit records (default 50)"},
            },
            "required": ["entity_id"],
        },
    },
]

COMPRESSION_PROMPT = """Summarize the following conversation history into a concise context summary.
Preserve:
- Entity IDs mentioned (golden_record_id format)
- Key findings and data points discovered
- User goals and questions asked
- Any decisions or conclusions reached
- Tool results that were significant

Keep the summary under 500 words. Focus on information that would be needed to continue the conversation coherently.

Conversation:
{conversation}"""

TITLE_PROMPT = """Generate a concise title (5-8 words) for a chat session that starts with this message.
Return ONLY the title text, no quotes or formatting.

Message: {message}"""

# Map MCP tool names to UI-friendly labels for the tool_start/tool_call events
TOOL_LABELS = {
    "search_entities": "Searching entities",
    "describe_entity": "Loading entity profile",
    "query_network": "Traversing network graph",
    "aggregate_stats": "Computing statistics",
    "search_by_relationship": "Querying relationships",
    "get_merge_history": "Fetching merge history",
}
