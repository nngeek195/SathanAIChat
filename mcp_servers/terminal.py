import subprocess
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("terminal")

@mcp.tool()
def execute_bash_command(command: str) -> str:
    """Executes a standard terminal command and returns the output."""
    try:
        # shell=True is used for native bash syntax (pipes, redirects)
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            return result.stdout.strip() if result.stdout else "Command executed successfully with no output."
        return f"Error ({result.returncode}): {result.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return "Error: Command execution timed out after 15 seconds."
    except Exception as e:
        return f"Terminal execution failed: {str(e)}"

if __name__ == "__main__":
    mcp.run()