import sqlite3
import json
import os
import datetime
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import google.auth.transport.requests

# Resolve absolute path to the root directory database to prevent relative path mismatch bugs
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(BASE_DIR, "satan_history.db")

# Load environment variables (for GOOGLE_CLIENT_ID / SECRET)
load_dotenv(os.path.join(BASE_DIR, ".env"))

mcp = FastMCP("google_workspace")

def get_user_credentials():
    """Retrieves user's Google OAuth tokens directly from the absolute SQLite DB path and auto-refreshes if needed."""
    if not os.path.exists(DB_FILE):
        return None
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT auth_token FROM integrations WHERE service_id = 'google_workspace' AND is_enabled = 1")
        row = cursor.fetchone()
        conn.close()
        
        if not (row and row[0]):
            return None

        token_data = json.loads(row[0])
        client_id = token_data.get('client_id') or os.getenv('GOOGLE_CLIENT_ID')
        client_secret = token_data.get('client_secret') or os.getenv('GOOGLE_CLIENT_SECRET')
        token_uri = token_data.get('token_uri') or "https://oauth2.googleapis.com/token"
        raw_scopes = token_data.get('scope', '')
        scopes = raw_scopes.split() if isinstance(raw_scopes, str) else raw_scopes
        
        expiry = None
        if token_data.get('expires_at'):
            expiry = datetime.datetime.fromtimestamp(token_data['expires_at'], datetime.timezone.utc).replace(tzinfo=None)

        creds = Credentials(
            token=token_data.get('access_token'),
            refresh_token=token_data.get('refresh_token'),
            token_uri=token_uri,
            client_id=client_id,
            client_secret=client_secret,
            scopes=scopes,
            expiry=expiry
        )

        # If token is expired (or near expiry) and refresh_token exists, refresh it automatically
        if (not creds.valid or creds.expired) and creds.refresh_token:
            try:
                request = google.auth.transport.requests.Request()
                creds.refresh(request)
                
                # Update SQLite with refreshed token info
                token_data['access_token'] = creds.token
                if creds.expiry:
                    token_data['expires_at'] = int(creds.expiry.timestamp())
                    
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE integrations SET auth_token = ? WHERE service_id = 'google_workspace'",
                    (json.dumps(token_data),)
                )
                conn.commit()
                conn.close()
                print("🔄 Google Workspace access token successfully refreshed.")
            except Exception as ref_err:
                print(f"Token refresh failed: {ref_err}")
                return None

        if not creds.valid:
            return None

        return creds
    except Exception as e:
        print(f"Token resolution error: {e}")
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
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
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

# --- Google Contacts Tools ---
@mcp.tool()
def list_contacts(limit: int = 10) -> str:
    """Lists the user's Google Contacts with their names, emails, and phone numbers."""
    creds = get_user_credentials()
    if not creds:
        return "Error: Google Workspace integration is not authenticated or enabled."
    
    try:
        service = build('people', 'v1', credentials=creds)
        results = service.people().connections().list(
            resourceName='people/me',
            pageSize=limit,
            personFields='names,emailAddresses,phoneNumbers'
        ).execute()
        connections = results.get('connections', [])
        
        output = []
        for person in connections:
            names = person.get('names', [])
            display_name = names[0].get('displayName') if names else 'Unknown Name'
            emails = [e.get('value') for e in person.get('emailAddresses', []) if e.get('value')]
            phones = [p.get('value') for p in person.get('phoneNumbers', []) if p.get('value')]
            email_str = f" | Email: {', '.join(emails)}" if emails else ""
            phone_str = f" | Phone: {', '.join(phones)}" if phones else ""
            output.append(f"• {display_name}{email_str}{phone_str}")
            
        return "\n".join(output) if output else "No contacts found."
    except Exception as e:
        return f"Contacts API Error: {str(e)}"

@mcp.tool()
def search_contacts(query: str, limit: int = 10) -> str:
    """Searches user's Google Contacts by name or keyword."""
    creds = get_user_credentials()
    if not creds:
        return "Error: Google Workspace integration is not authenticated or enabled."
    
    try:
        service = build('people', 'v1', credentials=creds)
        results = service.people().searchContacts(
            query=query,
            readMask='names,emailAddresses,phoneNumbers',
            pageSize=limit
        ).execute()
        results_list = results.get('results', [])
        
        output = []
        for item in results_list:
            person = item.get('person', {})
            names = person.get('names', [])
            display_name = names[0].get('displayName') if names else 'Unknown Name'
            emails = [e.get('value') for e in person.get('emailAddresses', []) if e.get('value')]
            phones = [p.get('value') for p in person.get('phoneNumbers', []) if p.get('value')]
            email_str = f" | Email: {', '.join(emails)}" if emails else ""
            phone_str = f" | Phone: {', '.join(phones)}" if phones else ""
            output.append(f"• {display_name}{email_str}{phone_str}")
            
        return "\n".join(output) if output else f"No contacts found matching '{query}'."
    except Exception as e:
        return f"Contacts API Error: {str(e)}"

if __name__ == "__main__":
    mcp.run()