import subprocess
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("network")

@mcp.tool()
def run_nmap_scan(target: str, ports: str = "top-100") -> str:
    """Runs a basic Nmap scan against a target network or IP."""
    try:
        cmd = ["nmap", "-T4", "-F", target] if ports == "top-100" else ["nmap", "-p", ports, target]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.stdout if result.returncode == 0 else result.stderr
    except FileNotFoundError:
        return "Error: nmap is not installed on this system."
    except Exception as e:
        return f"Nmap execution failed: {str(e)}"

if __name__ == "__main__":
    mcp.run()