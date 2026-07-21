import subprocess
import platform
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("os_services")

def run_command(cmd_list: list) -> str:
    """Helper to execute shell commands securely."""
    try:
        result = subprocess.run(cmd_list, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"Error executing command: {e.stderr.strip()}"

@mcp.tool()
def get_service_status(service_name: str) -> str:
    """Checks the status of a specific OS service."""
    current_os = platform.system()
    
    if current_os == "Linux":
        # Ubuntu / systemd logic
        return run_command(["systemctl", "is-active", service_name])
        
    elif current_os == "Windows":
        # Windows / PowerShell logic
        cmd = ["powershell", "-Command", f"(Get-Service -Name '{service_name}').Status"]
        return run_command(cmd)
        
    return f"Unsupported operating system: {current_os}"

@mcp.tool()
def manage_service(service_name: str, action: str) -> str:
    """
    Starts, stops, or restarts a service. 
    Actions: 'start', 'stop', 'restart'.
    Note: Usually requires administrator/root privileges.
    """
    current_os = platform.system()
    valid_actions = ["start", "stop", "restart"]
    
    if action not in valid_actions:
        return f"Invalid action. Choose from: {', '.join(valid_actions)}"
        
    if current_os == "Linux":
        # Using sudo for state changes
        return run_command(["sudo", "systemctl", action, service_name])
        
    elif current_os == "Windows":
        cmd = ["powershell", "-Command", f"{action.capitalize()}-Service -Name '{service_name}'"]
        return run_command(cmd)

if __name__ == "__main__":
    mcp.run()