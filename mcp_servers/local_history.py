import os
import shutil
import sqlite3
import tempfile
import platform
from mcp.server.fastmcp import FastMCP

# Initialize the FastMCP server for browser history
mcp = FastMCP("local_history")

def get_browser_paths(browser_name: str) -> str:
    """Returns the OS-specific path to the browser's history database."""
    system = platform.system()
    home = os.path.expanduser("~")
    
    # Windows environment variables
    local_app_data = os.environ.get("LOCALAPPDATA", os.path.join(home, "AppData", "Local"))
    roaming_app_data = os.environ.get("APPDATA", os.path.join(home, "AppData", "Roaming"))

    paths = {
        "Windows": {
            "chrome": os.path.join(local_app_data, "Google", "Chrome", "User Data", "Default", "History"),
            "edge": os.path.join(local_app_data, "Microsoft", "Edge", "User Data", "Default", "History"),
            "brave": os.path.join(local_app_data, "BraveSoftware", "Brave-Browser", "User Data", "Default", "History"),
            "opera": os.path.join(roaming_app_data, "Opera Software", "Opera Stable", "History"),
            "opera_gx": os.path.join(roaming_app_data, "Opera Software", "Opera GX Stable", "History"),
            "firefox": os.path.join(roaming_app_data, "Mozilla", "Firefox", "Profiles") # Requires searching for places.sqlite
        },
        "Linux": {
            "chrome": os.path.join(home, ".config", "google-chrome", "Default", "History"),
            "edge": os.path.join(home, ".config", "microsoft-edge", "Default", "History"),
            "brave": os.path.join(home, ".config", "BraveSoftware", "Brave-Browser", "Default", "History"),
            "opera": os.path.join(home, ".config", "opera", "History"),
            "opera_gx": os.path.join(home, ".config", "opera", "History"), # Linux Opera GX shares the standard Opera path
            "firefox": os.path.join(home, ".mozilla", "firefox") # Requires searching for places.sqlite
        }
    }
    
    # Default to Linux structure if OS is not strictly 'Windows'
    os_category = "Windows" if system == "Windows" else "Linux"
    return paths.get(os_category, {}).get(browser_name.lower())

def find_firefox_db(profile_dir: str) -> str:
    """Finds the active places.sqlite database inside the Firefox profiles directory."""
    if not os.path.exists(profile_dir):
        return None
    for folder in os.listdir(profile_dir):
        if folder.endswith(".default-release") or folder.endswith(".default"):
            db_path = os.path.join(profile_dir, folder, "places.sqlite")
            if os.path.exists(db_path):
                return db_path
    return None

@mcp.tool()
def get_recent_history(browser: str, limit: int = 50) -> str:
    """
    Fetches the most recent browsing history from a local web browser.
    Supported browsers: 'chrome', 'edge', 'brave', 'opera', 'opera_gx', 'firefox'.
    """
    browser = browser.lower()
    db_path = get_browser_paths(browser)
    
    if browser == "firefox" and db_path:
        db_path = find_firefox_db(db_path)

    if not db_path or not os.path.exists(db_path):
        return f"Error: Could not locate the history database for {browser} on this system. Path checked: {db_path}"

    # Create a temporary directory to clone the DB and bypass file locks
    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "temp_history.sqlite")
    
    try:
        shutil.copy2(db_path, temp_db_path)
        
        # Connect to the cloned database
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        
        # Determine the correct SQL schema based on the browser engine
        if browser == "firefox":
            # Gecko Engine Schema
            query = "SELECT title, url FROM moz_places WHERE title IS NOT NULL ORDER BY last_visit_date DESC LIMIT ?"
        else:
            # Chromium Engine Schema
            query = "SELECT title, url FROM urls WHERE title IS NOT NULL ORDER BY last_visit_time DESC LIMIT ?"
            
        cursor.execute(query, (limit,))
        rows = cursor.fetchall()
        
        conn.close()
        
        if not rows:
            return f"No recent history found for {browser}."
            
        # Format the output into a clean, token-efficient list for the LLM
        formatted_history = f"--- Recent {browser.capitalize()} History ---\n"
        for title, url in rows:
            # Clean up the text for the LLM context
            clean_title = str(title).replace('\n', '').strip()
            formatted_history += f"* {clean_title} - ({url})\n"
            
        return formatted_history
        
    except Exception as e:
        return f"Database extraction failed for {browser}: {str(e)}"
    finally:
        # Ensure the temporary clone is always deleted to prevent storage leaks
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    mcp.run()