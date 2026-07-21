import os
from mcp.server.fastmcp import FastMCP

# Initialize the server
mcp = FastMCP("filesystem")

@mcp.tool()
def read_file(filepath: str) -> str:
    """Reads the text content of a file at the specified local path."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {e}"

@mcp.tool()
def list_directory(directory_path: str) -> str:
    """Lists all files and folders in a specified directory."""
    try:
        return str(os.listdir(directory_path))
    except Exception as e:
        return f"Error listing directory: {e}"

if __name__ == "__main__":
    # Start the standard I/O server
    mcp.run()