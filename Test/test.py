import requests
import json
import sys

# ==========================================
# CONFIGURATION - UPDATE THESE BEFORE RUNNING
# ==========================================
API_KEY = "" 
BASE_URL = "https://agentrouter.org"
MODEL = "claude-opus-4-6"
# ==========================================

def test_connection():
    print(f"Testing connection to {BASE_URL}/chat/completions...")
    print(f"Using Model: {MODEL}")
    
    # Aggressive browser spoofing to bypass proxy firewalls
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Origin': 'https://agentrouter.org',
        'Referer': 'https://agentrouter.org/',
        'Accept': 'text/event-stream',
        'Authorization': f'Bearer {API_KEY}',
        'x-api-key': API_KEY  # Included for Anthropic compatibility
    }

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Hello, this is a quick connection test. Please reply with a single word."}],
        "stream": True,
        "max_tokens": 50
    }

    try:
        response = requests.post(
            f"{BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            stream=True
        )
        
        print(f"\nHTTP Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print("\n❌ API REJECTED THE REQUEST.")
            print("Raw Error Response:")
            print(response.text)
            return
            
        print("\n✅ API ACCEPTED THE REQUEST. Reading stream...\n")
        
        for line in response.iter_lines():
            if line:
                decoded = line.decode('utf-8')
                print(decoded)
                
    except Exception as e:
        print(f"\n❌ Network Exception Occurred: {e}")

if __name__ == "__main__":
    if API_KEY == "YOUR_AGENT_ROUTER_API_KEY_HERE":
        print("⚠️ Please edit this script and insert your actual API Key at the top before running.")
        sys.exit(1)
        
    test_connection()