"""
MCP Server entry point.

Imports all tool modules to register @mcp.tool() decorators,
then runs the FastMCP server with Streamable HTTP transport.

Usage:
    python server.py                        # Run server on configured port
    mcp dev server.py                       # MCP Inspector (development)
"""
import logging
import sys

# Configure logging before any imports that use it
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# Import the FastMCP instance (no tools registered yet)
from app import mcp

# Import all tool modules — this triggers @mcp.tool() registration
import tools.candidate_tools       # noqa: F401 — find_candidates, compare_fields, semantic_similarity
import tools.knowledge_graph_tools # noqa: F401 — query_ontology, check_shared_context, write_entity_triples, write_merge_redirect
import tools.entity_writer_tools   # noqa: F401 — merge_into_golden_record, create_golden_record, submit_for_review, merge_golden_records, log_decision
import tools.search_tools          # noqa: F401 — search_entities, describe_entity, query_network, aggregate_stats, search_by_relationship, get_merge_history

from config import load_config

logger.info("All 18 tools registered")


def main():
    config = load_config()

    logger.info(f"Starting MCP Server: {config.server.name}")
    logger.info(f"Transport: Streamable HTTP on {config.server.host}:{config.server.port}")
    logger.info("MCP Server READY")

    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
