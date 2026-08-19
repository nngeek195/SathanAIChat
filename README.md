# SathanAIChat

SathanAIChat is a Flask-based AI chat interface with persistent conversation history, file/image attachments, streaming responses, and an optional autonomous agent mode powered by local MCP tool servers.

## Core Capabilities

- Multi-provider chat routing (Gemini-style and OpenAI-compatible endpoints)
- Persistent chat threads and message history (SQLite)
- Thread management (create, rename, pin, search, delete)
- Message editing flow via thread truncation and regenerate
- File/image uploads and pasted-text upload handling
- Optional agent mode with tool-calling through local MCP servers
- Google Workspace OAuth integration (Gmail, Drive, Calendar tool access)

## Architecture Summary

The app is split into four main layers:

1. **Flask Web App (`main.py`)**
   - Serves UI, REST endpoints, and SSE streaming responses.
2. **Database Layer (`DatabaseManager` in `main.py`)**
   - Handles threads, messages, settings, and integration auth state.
3. **MCP Registry Layer (`LocalMCPRegistry` in `main.py`)**
   - Discovers and invokes local tool servers over stdio.
4. **Frontend (`templates/index.html`)**
   - Single-page chat interface that calls backend APIs.

## Repository Structure

```text
SathanAIChat/
├── main.py                       # Primary Flask app, API routes, streaming chat, MCP registry
├── Connection.py                 # Minimal OpenAI client connectivity sample
├── 1.txt                         # Local text file (non-runtime)
├── .gitignore
├── Test/
│   ├── test.py                   # Standalone connection test script
│   └── test_api.py               # Alternate Flask API test/variant file
├── templates/
│   └── index.html                # Full frontend UI and client-side logic
├── static/
│   ├── ico.ico
│   ├── logo.png
│   └── uploads/                  # Runtime upload destination (git-ignored)
└── mcp_servers/
    ├── api_client.py             # HTTP reachability tool
    ├── browser.py                # Webpage fetch and text extraction tool
    ├── filesystem.py             # Local file read/list tools
    ├── google_workspace.py       # Gmail/Drive/Calendar tools via OAuth token from DB
    ├── local_history.py          # Browser history extraction tool
    ├── network.py                # Nmap scan tool
    ├── os_services.py            # Service status/start-stop tools
    ├── postgres_db.py            # PostgreSQL placeholder tool
    ├── system_controller.py      # Infra health and service orchestration tools
    └── terminal.py               # Bash command execution tool
```

## Backend Components

### 1) `main.py`

- Initializes Flask app, OAuth, upload directory, and DB.
- Registers Google OAuth (`/api/auth/google/login`, callback route).
- Implements:
  - settings APIs
  - thread/message CRUD APIs
  - upload APIs
  - integration status/toggle APIs
  - `/api/chat` streaming endpoint
- Supports two chat execution modes:
  - **General AI mode**: direct streaming completion flow
  - **Agent mode**: iterative tool-calling loop with MCP tool servers

### 2) Database (`satan_history.db`)

Tables created/managed by `DatabaseManager`:

- `threads(id, title, updated_at, is_pinned)`
- `messages(id, thread_id, role, content)`
- `settings(id, base_url, model_name, api_key)`
- `integrations(service_id, service_name, is_enabled, auth_token)`

### 3) MCP Tooling

`LocalMCPRegistry` dynamically resolves tool schemas and invokes tools from `mcp_servers/*` using stdio MCP sessions.  
Tool names are exposed to the LLM as `<server_key>___<tool_name>`.

## Frontend (`templates/index.html`)

Single-page interface with:

- Chat composer, markdown/code rendering, and streaming UI updates
- Sidebar chat history with search, pinning, rename, delete
- Attachment flows (file/image/text)
- Integration modal for Agent Mode + Google Workspace toggles
- Settings panel for model/base URL/API key
- Edit/regenerate controls for conversation replay

## API Surface

### Authentication
- `GET /api/auth/google/login`
- `GET /api/auth/google/callback`

### Settings
- `GET /api/settings`
- `POST /api/settings`

### Threads & Messages
- `GET /api/threads`
- `POST /api/threads`
- `DELETE /api/threads/<thread_id>`
- `PATCH /api/threads/<thread_id>/pin`
- `PATCH /api/threads/<thread_id>/rename`
- `GET /api/threads/<thread_id>/messages`
- `DELETE /api/messages/<message_id>`
- `POST /api/threads/<thread_id>/truncate`

### Uploads
- `POST /api/upload`
- `POST /api/upload-text`

### Integrations
- `GET /api/integrations`
- `POST /api/integrations/toggle`

### Chat
- `POST /api/chat` (SSE streaming response)

## Runtime Flow (High Level)

1. Frontend sends user message and context to `/api/chat`.
2. Backend persists user message (if thread exists).
3. Backend injects a system prompt.
4. Backend routes request:
   - Gemini native stream path, or
   - OpenAI-compatible chat/completions stream path.
5. Streamed tokens are forwarded to browser via SSE.
6. Final assistant text is saved in DB.
7. In Agent Mode, tool calls are resolved via local MCP servers and fed back into loop until final answer.

## Setup & Run

### Requirements

- Python 3.10+
- SQLite (bundled with Python)
- Optional system tools for some MCP servers:
  - `nmap` (network scanning tool)
  - `docker`, `systemctl`, `sudo` (system tooling)

Install Python dependencies:

```bash
pip install flask requests python-dotenv authlib openai mcp beautifulsoup4 google-auth google-api-python-client
```

Create `.env` (optional but recommended):

```env
FLASK_SECRET_KEY=replace_me
GOOGLE_CLIENT_ID=your_google_oauth_client_id
GOOGLE_CLIENT_SECRET=your_google_oauth_client_secret
```

Run:

```bash
python main.py
```

Open:

- `http://127.0.0.1:5000`

## Configuration Notes

- Model endpoint settings (`base_url`, `model_name`, `api_key`) are stored in SQLite via `/api/settings`.
- Uploads are stored in `static/uploads`.
- OAuth token data is persisted in `integrations.auth_token`.
- Google Workspace tools only activate when integration is both authenticated and enabled.

## Test/Utility Scripts

- `Test/test.py`: simple API connectivity script.
- `Test/test_api.py`: alternate Flask/API test harness variant.
- `Connection.py`: direct `OpenAI` client connection sample.

## Security & Operational Notes

- Keep API keys and OAuth secrets out of source control.
- `.gitignore` already excludes `.env`, DB file, and uploads.
- Agent mode can execute local MCP tools; review and limit exposed tools before production use.
