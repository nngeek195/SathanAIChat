import sqlite3
import json
import os
from mcp.server.fastmcp import FastMCP
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

mcp = FastMCP("google_workspace")
DB_FILE = "satan_history.db"

def get_user_credentials():
    """Retrieves user's Google OAuth tokens directly from SQLite DB."""
    if not os.path.exists(DB_FILE):
        return None
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT auth_token FROM integrations WHERE service_id = 'google_workspace' AND is_enabled = 1")
    row = cursor.fetchone()
    conn.close()
    
    if row and row[0]:
        token_data = json.loads(row[0])
        return Credentials.from_authorized_user_info(token_data)
    return None

# --- Gmail Tools ---
@mcp.tool()
def read_recent_emails(max_results: int = 5) -> str:
    """Fetches the user's most recent unread or inbox emails from Gmail."""
    creds = get_user_credentials()
    if not creds:
        return "Error: Google Workspace integration is not authenticated or enabled."
    
    try:
        service = build('gmail', 'v1', credentials=creds)
        results = service.users().messages().list(userId='me', maxResults=max_results, q="label:INBOX").execute()
        messages = results.get('messages', [])
        
        output = []
        for msg in messages:
            m = service.users().messages().get(userId='me', id=msg['id'], format='metadata').execute()
            headers = {h['name']: h['value'] for h in m.get('payload', {}).get('headers', [])}
            output.append(f"• From: {headers.get('From', 'Unknown')} | Subject: {headers.get('Subject', 'No Subject')}")
            
        return "\n".join(output) if output else "No recent emails found."
    except Exception as e:
        return f"Gmail API Error: {str(e)}"

# --- Google Drive Tools ---
@mcp.tool()
def search_drive_files(query: str, limit: int = 5) -> str:
    """Searches files in the user's Google Drive by filename or keyword."""
    creds = get_user_credentials()
    if not creds:
        return "Error: Google Workspace integration is not authenticated or enabled."
    
    try:
        service = build('drive', 'v3', credentials=creds)
        results = service.files().list(
            q=f"name contains '{query}'",
            pageSize=limit,
            fields="files(id, name, mimeType, webViewLink)"
        ).execute()
        files = results.get('files', [])
        
        output = [f"• {f['name']} ({f['mimeType']}) - Link: {f.get('webViewLink', 'N/A')}" for f in files]
        return "\n".join(output) if output else f"No files matching '{query}' found."
    except Exception as e:
        return f"Drive API Error: {str(e)}"

# --- Google Calendar Tools ---
@mcp.tool()
def list_upcoming_calendar_events(max_results: int = 5) -> str:
    """Lists the user's upcoming Google Calendar events."""
    creds = get_user_credentials()
    if not creds:
        return "Error: Google Workspace integration is not authenticated or enabled."
    
    try:
        service = build('calendar', 'v3', credentials=creds)
        now = datetime.datetime.utcnow().isoformat() + 'Z'
        events_result = service.events().list(
            calendarId='primary', timeMin=now,
            maxResults=max_results, singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])
        
        output = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            output.append(f"• {event.get('summary', 'Untitled Event')} @ {start}")
            
        return "\n".join(output) if output else "No upcoming events found."
    except Exception as e:
        return f"Calendar API Error: {str(e)}"

if __name__ == "__main__":
    mcp.run()