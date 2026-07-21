from mcp.server.fastmcp import FastMCP

mcp = FastMCP("postgres_db")

@mcp.tool()
def test_db_connection() -> str:
    """Placeholder tool to verify PostgreSQL routing."""
    return "PostgreSQL server module initialized successfully. Ready for connection logic."

if __name__ == "__main__":
    mcp.run()