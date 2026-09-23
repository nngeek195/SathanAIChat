import os
import requests
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv
import sqlite3

load_dotenv()

mcp = FastMCP("tavily")

def get_tavily_api_key():
    try:
        conn = sqlite3.connect("satan_history.db")
        cursor = conn.cursor()
        cursor.execute("SELECT tavily_api_key FROM settings WHERE id = 1")
        row = cursor.fetchone()
        conn.close()

        if row and row[0]:
            return row[0].strip()

    except Exception as e:
        print(e)
    return os.getenv("TAVILY_API_KEY", "")

@mcp.tool()
def search_web(query: str, max_results: int = 5) -> str:

    api_key = get_tavily_api_key

    if not api_key:
        return "Error: TAVILY API key was not found"
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "include_answer": True
    }

    try:
        response = requests.post(url, json=payload, header={"Content-Type": "application/json"})
        response.raise_for_status()
        data = response.json()
        results_text = []

        if data.get("anwser"):
            results_text.append(f"### AI Summary Answer\n{data['answer']}\n")

        results_text.append("###Souce Results")
        for idx, result in enumerate(data.get("results", []),1):
            results_text.append(f"{idx}.**{result.get('title')}**")
            results_text.append(f" URL:{result.get('url')}")
            results_text.append(f" Snippet: {result.get('content')}\n") 

        if not results_text:
            return "No result found"
        return "\n".join(results_text)

    except requests.exceptions.RequestException as e:
        return f"Error with API: {str(e)}"
    except Exception as e:
        return f"Unxpected error: {str(e)}"
    
        
