import requests
from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("browser")

@mcp.tool()
def fetch_webpage(url: str) -> str:
    """Fetches and extracts the readable text content from a given URL."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Strip out scripts and styles to save context tokens
        for script in soup(["script", "style"]):
            script.extract()
            
        text = soup.get_text(separator='\n')
        
        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        clean_text = '\n'.join(chunk for chunk in chunks if chunk)
        
        return clean_text[:8000] # Limit length to save tokens
    except Exception as e:
        return f"Failed to fetch {url}: {e}"

if __name__ == "__main__":
    mcp.run()