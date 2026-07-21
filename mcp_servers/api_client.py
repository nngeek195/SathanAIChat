import requests
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("api_client")

@mcp.tool()
def test_api_endpoint(url: str) -> str:
    """Executes a basic GET request to test API reachability."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return f"Status {response.status_code}: {response.text[:1000]}"
    except Exception as e:
        return f"API Request failed for {url}: {str(e)}"

if __name__ == "__main__":
    mcp.run()