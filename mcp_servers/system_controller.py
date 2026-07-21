import subprocess
import socket
from mcp.server.fastmcp import FastMCP

# Initialize the Controller Server
mcp = FastMCP("system_controller")

@mcp.tool()
def check_infrastructure_health() -> str:
    """Checks the status of critical underlying services for SatanAI (PostgreSQL, Docker, Network)."""
    report = ["--- SatanAI Infrastructure Health ---"]
    
    # Check PostgreSQL (Default Port 5432)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', 5432))
    if result == 0:
        report.append("✅ PostgreSQL Database: ONLINE (Port 5432)")
    else:
        report.append("❌ PostgreSQL Database: OFFLINE")
    sock.close()

    # Check Internet Connectivity for API Client
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=2)
        report.append("✅ External Network: ONLINE")
    except OSError:
        report.append("❌ External Network: OFFLINE")

    # Check Docker Daemon (Useful for terminal/container execution)
    try:
        subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        report.append("✅ Docker Daemon: ONLINE")
    except (subprocess.CalledProcessError, FileNotFoundError):
        report.append("❌ Docker Daemon: OFFLINE or Not Installed")

    return "\n".join(report)

@mcp.tool()
def orchestrate_local_service(service_name: str, action: str) -> str:
    """
    Starts or stops underlying system services (e.g., 'postgresql', 'docker').
    Requires sudo privileges on Ubuntu.
    """
    valid_actions = ["start", "stop", "restart"]
    if action not in valid_actions:
        return f"Invalid action. Choose from: {', '.join(valid_actions)}"
    
    try:
        # Executes standard Ubuntu systemctl commands
        result = subprocess.run(["sudo", "systemctl", action, service_name], capture_output=True, text=True, check=True)
        return f"Successfully executed '{action}' on '{service_name}'.\n{result.stdout.strip()}"
    except subprocess.CalledProcessError as e:
        return f"Failed to {action} {service_name}. Error: {e.stderr.strip()}"

if __name__ == "__main__":
    mcp.run()