# SathanAIChat: In-Depth Technical Dossier & Architecture Reference

SathanAIChat is a full-stack, multimodal conversational AI platform and autonomous agent runtime built with Flask, SQLite, and the Model Context Protocol (MCP). It features persistent conversational thread management, real-time Server-Sent Events (SSE) streaming, multimodal media ingestion, thread truncation/regeneration, and an iterative tool-calling agent loop powered by local FastMCP subprocesses over standard I/O (stdio).

---

## 1. Executive Summary & Architecture

### Core Functionality
- **Dual-Engine Model Gateway:** Dynamic request routing supporting both Google Gemini Native REST APIs (with `systemInstruction` and `inlineData` base64 ingestion) and OpenAI-compatible endpoint standards (OpenAI, NVIDIA NIM, Qwen/Alibaba, OpenRouter/AgentRouter, local vLLM/Ollama).
- **Persistent Conversation Hierarchy:** SQLite-backed thread and message storage with support for search, pinning, renaming, pair-wise deletion, and branch truncation for message editing and regeneration.
- **Multimodal & Attachment Ingestion:** Client-side file/image ingestion with automatic conversion of large clipboard pastes (>2500 chars) into managed text files.
- **Autonomous Agent Mode (MCP):** Multi-turn ReAct reasoning loop that queries local system tools via Model Context Protocol (MCP) child processes communicating over stdio JSON-RPC.
- **Google Workspace Integration:** OAuth 2.0-authenticated access to Gmail (inbox search/read), Google Drive (file search), and Google Calendar (upcoming events).

### Architecture Pattern
**Dual-Engine Layered & Extensible Micro-Kernel Architecture with Subprocess IPC Plugin Bus:**
- **Ingress & Gateway Layer:** Flask WSGI application managing routing, session configurations, and SSE token streaming.
- **Multi-Engine LLM Adapter Layer:** Unified abstraction layer normalizing disparate downstream model payloads into uniform SSE chunks.
- **Persistence & State Repository Layer:** SQLite database encapsulation with thread indexing, cascade deletions, and OAuth token persistence.
- **Agent & Tool Orchestration Layer:** On-demand asynchronous event loop bridging synchronous Flask workers to asynchronous MCP client sessions.
- **Decoupled Tool Plugin Server Fleet:** Isolated, standalone FastMCP micro-servers running as child processes communicating over standard I/O streams.

```text
+-------------------------------------------------------------------------------+
|                      Frontend SPA (templates/index.html)                       |
|   [EventSource/Fetch SSE] [Paste Interceptor] [DOM / Markdown / Highlight.js] |
+---------------------------------------+---------------------------------------+
                                        | HTTP REST & SSE
                                        v
+-------------------------------------------------------------------------------+
|                       Flask Application (main.py)                             |
|  +--------------------+------------------------+---------------------------+  |
|  | Settings & Auth    | Threads & Message CRUD | File / Media Ingestion    |  |
|  | OAuth2 Google Flow | Branch Truncation/Regen| Base64 & Upload Store     |  |
|  +--------------------+------------------------+---------------------------+  |
|                                       |                                       |
|                  +--------------------+--------------------+                  |
|                  |                                         |                  |
|                  v                                         v                  |
|       [General AI Mode Flow]                     [Agent Mode ReAct Loop]      |
|                  |                                         |                  |
|     +------------+------------+                            v                  |
|     |                         |                +-----------------------+      |
|     v                         v                |   LocalMCPRegistry    |      |
| [Gemini Native REST] [OpenAI / NVIDIA NIM]     | (asyncio stdio client)|      |
| (streamGenerateContent) (/chat/completions)    +-----------+-----------+      |
+------------------------------------------------------------|------------------+
                                                             |
              +----------------------------------------------+
              | Subprocess Stdio IPC (JSON-RPC Protocol)
              v
+-------------------------------------------------------------------------------+
|                        Decoupled FastMCP Tool Fleet                           |
|  +------------------+  +------------------+  +------------------+             |
|  |  filesystem.py   |  |   terminal.py    |  |    browser.py    |             |
|  +------------------+  +------------------+  +------------------+             |
|  +------------------+  +------------------+  +------------------+             |
|  | local_history.py |  | google_workspace |  |  os_services.py  |             |
|  +------------------+  +------------------+  +------------------+             |
|  +------------------+  +------------------+  +------------------+             |
|  |    network.py    |  | system_controller|  |  postgres_db.py  |             |
|  +------------------+  +------------------+  +------------------+             |
+-------------------------------------------------------------------------------+
```

### Component Breakdown
1. **Frontend Presentation Layer (`templates/index.html`):** Single-Page Application (SPA) built with vanilla JS (ES6+), Marked.js, and Highlight.js. Implements chunk-by-chunk SSE stream reading via `ReadableStream` and `TextDecoder`, optimistic UI updates, clipboard paste interception, and contextual quote references.
2. **Web Ingress & API Controller (`main.py`):** Flask HTTP server providing REST endpoints, Google OAuth 2.0 flow handling, and streaming endpoints (`/api/chat`). Includes request header spoofing to avoid WAF/bot blocking.
3. **Data Access Repository (`DatabaseManager` in `main.py`):** Encapsulated SQLite data layer handling threads, messages, model settings, and serialized integration credentials.
4. **MCP Registry & Process Orchestrator (`LocalMCPRegistry` in `main.py`):** Dynamically builds subprocess execution arguments, initializes MCP client sessions over stdio, fetches tool schemas, and executes tool calls namespaced as `<server_key>___<tool_name>`.
5. **Decoupled FastMCP Tool Servers (`mcp_servers/`):** Standalone tools implementing filesystem access, bash execution, web scraping, browser history extraction, Google Workspace APIs, system health monitoring, and network scanning.

---

## 2. Deep-Dive Tech Stack & Dependencies

- **Core Languages & Runtimes:**
  - **Python:** 3.10+ (CPython runtime).
  - **JavaScript:** ECMAScript 2022+ (Vanilla, browser runtime).
  - **SQL:** SQLite 3 (Standard library, dialect-specific UPSERTs via `ON CONFLICT DO UPDATE`).
  - **HTML5 & CSS3:** CSS Custom Properties (Design Tokens), Flexbox layout, Keyframe animations.

- **Frameworks & Core Libraries:**
  - **Web Framework:** Flask, Werkzeug (`secure_filename`).
  - **Model Context Protocol (MCP):** `mcp` (`ClientSession`, `StdioServerParameters`, `stdio_client`, `FastMCP`).
  - **Authentication:** `authlib` (Flask OAuth client with OpenID Connect discovery).
  - **HTTP & Scraping:** `requests` (streaming HTTP chunk reading), `BeautifulSoup4` (`bs4`).
  - **Cloud APIs & LLM SDKs:** `google-api-python-client`, `google-auth`, `openai` SDK.
  - **Configuration:** `python-dotenv`.

- **External APIs & Integrations:**
  - **Google Gemini Native REST API:** `streamGenerateContent?alt=sse&key=...` with `inlineData` base64 multimodal inputs.
  - **OpenAI-Compatible AI Gateways:** `/chat/completions` API specifications (NVIDIA NIM, Qwen/Alibaba, AgentRouter, Ollama/vLLM).
  - **Google Workspace Cloud APIs (OAuth 2.0):** Gmail API v1, Google Drive API v3, Google Calendar API v3.
  - **Host System Binaries:** `nmap`, `systemctl`, `powershell`, `docker`, `sudo`.

---

## 3. Object-Oriented Programming (OOP) & Design Patterns

### OOP Principles in Practice
- **Encapsulation:**
  - `DatabaseManager`: Strictly encapsulates database connection state (`check_same_thread=False`), cursor life cycles, schema migrations, and JSON token serialization.
  - `LocalMCPRegistry`: Encapsulates subprocess lifecycle parameters, frozen binary checks (`sys.frozen`), stdio stream channels, and namespacing logic behind `fetch_all_agent_tools` and `run_tool_execution`.
- **Inheritance & Polymorphism:**
  - **FastMCP Declarative Polymorphism:** All tools in `mcp_servers/*.py` conform to the standard MCP schema contract via `@mcp.tool()`, allowing dynamic execution by the agent runner without class coupling.
  - **Cross-Platform SQL & OS Polymorphism:**
    - `mcp_servers/local_history.py`: Polymorphically switches query strategies between Gecko engine schemas (`moz_places`) and Chromium engine schemas (`urls`).
    - `mcp_servers/os_services.py`: Polymorphically executes Linux `systemctl` or Windows PowerShell `Get-Service` based on host OS detection.
- **Abstraction:**
  - **Provider-Agnostic LLM Routing:** Decouples the frontend payload structure from vendor-specific payload formats (Google Gemini `contents`/`parts`/`systemInstruction` vs. OpenAI `messages`/`role: system`).

### Design Patterns Used
- **Adapter / Bridge Pattern:** Implemented in `main.py` (`/api/chat`) to bridge divergent external LLM API schemas into a unified internal SSE protocol delivered to the client.
- **Registry Pattern:** `LocalMCPRegistry` serves as a central service catalog mapping server keys to their executable definitions.
- **Factory / CLI Dispatcher Pattern:** Command-line dispatch `--run-mcp <server_name>` in `main.py` dynamically routes process execution to the appropriate tool module.
- **Repository Pattern:** `DatabaseManager` isolates raw SQL statements and transactional logic from Flask route controllers.
- **Observer / SSE Stream Pattern:** The chat completion endpoint uses Python generators (`yield f"data: ...\n\n"`) to push real-time event updates to the frontend subscriber.
- **ReAct (Reason + Act) Agent Loop:** Implements an iterative reasoning cycle in `run_agent_loop()` (up to `max_loops = 5`) evaluating tool calls and piping results back into the conversation context.

---

## 4. Data Layer, Security & Tenant Isolation

### Database & Storage Schema
- **Database Engine:** SQLite 3 (`satan_history.db`).
- **Table Schemas:**

```sql
CREATE TABLE threads (
    id INTEGER PRIMARY KEY,
    title TEXT,
    updated_at TEXT,
    is_pinned INTEGER DEFAULT 0
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY,
    thread_id INTEGER,
    role TEXT,          -- 'user' | 'ai'
    content TEXT,
    FOREIGN KEY(thread_id) REFERENCES threads(id)
);

CREATE TABLE settings (
    id INTEGER PRIMARY KEY,
    base_url TEXT,
    model_name TEXT,
    api_key TEXT
);

CREATE TABLE integrations (
    service_id TEXT PRIMARY KEY,
    service_name TEXT,
    is_enabled INTEGER DEFAULT 0,
    auth_token TEXT     -- Serialized JSON OAuth token dict
);
```

### Security & Auth Architecture
- **OAuth 2.0 Code Flow:** Authlib manages the authorization grant flow against Google Identity OpenID endpoints. Access and refresh token dictionaries are persisted in SQLite `integrations.auth_token`.
- **Tenant Isolation:** Single-tenant local deployment architecture without multi-tenant partitioning or IDOR protections.
- **Security Considerations & Tool Sandboxing:**
  - `mcp_servers/terminal.py`: Executes commands using `subprocess.run(command, shell=True)`, posing a risk of arbitrary OS command execution (RCE) if exposed to untrusted prompt injections.
  - `mcp_servers/filesystem.py`: Does not enforce path traversal restrictions or `chroot` jails.
  - `mcp_servers/os_services.py` & `system_controller.py`: Use `sudo systemctl`, requiring appropriate host privileges.
- **WAF / Anti-Bot Mitigation:** Injects standard browser `User-Agent` headers into outbound requests to bypass Cloudflare/WAF bot filters.

### Complete Request Lifecycle (Data Flow)
1. **User Ingress:** User submits message and attachments via frontend SPA -> `POST /api/chat`.
2. **User Persistence:** Backend stores user prompt in SQLite `messages` table.
3. **Context Injection:** System prompt is injected, base64 media attached, and conversation history sliced.
4. **Execution Path:**
   - **General AI Mode:** Direct HTTP streaming from provider (Gemini or OpenAI). Chunks are accumulated and pushed to frontend via SSE.
   - **Agent Mode:** Dedicated `asyncio` event loop discovers tools via `LocalMCPRegistry`, calls LLM with function schemas, executes requested MCP tools via stdio child processes, appends results, and repeats until the final response is obtained (max 5 loops).
5. **AI Persistence:** Full generated assistant text is saved to SQLite `messages` table.
6. **Client Stream Consumer:** Browser `ReadableStream` reads SSE chunks, renders markdown via Marked.js, updates token telemetry, and synchronizes state.

---

## 5. Concurrency, Performance & Memory Management

- **Token Budgeting & Context Slicing:**
  - `mcp_servers/browser.py`: Strips `<script>`/`<style>` tags and caps extracted text at 8,000 characters.
  - `templates/index.html`: Client limits outgoing message context to the last 4 messages (`messages.slice(-4)`), minimizing latency and token costs.
- **Database Lock & Resource Leak Mitigation:**
  - `mcp_servers/local_history.py`: Clones locked browser SQLite files into a `tempfile.mkdtemp()` directory before querying, with guaranteed cleanup via `shutil.rmtree()` in a `finally` block.
- **Concurrency Model:**
  - **Synchronous WSGI + SSE Generators:** Flask handles HTTP requests synchronously while yielding chunked tokens via streaming responses (`mimetype='text/event-stream'`).
  - **Sync-to-Async Bridge:** Synchronous Flask workers spin up an on-demand event loop (`asyncio.new_event_loop()`) and execute async MCP sessions via `loop.run_until_complete()`.
  - **Subprocess Isolation:** Each MCP tool server runs in an isolated child process communicating via stdio JSON-RPC.

---

## 6. Edge Cases, Error Handling & Trade-Offs

### Fault Tolerance & Edge Cases
- **Process Timeouts:** Subprocess executions are guarded by explicit timeouts (`15s` for terminal commands, `30s` for network scans, `10s` for HTTP/browser fetches).
- **Branch Truncation & Edit Flow:** Deleting or editing a prior message triggers `DELETE FROM messages WHERE thread_id = ? AND id >= ?`, cleanly truncating the conversation history before re-prompting.
- **Pairwise Message Deletion:** Deleting an AI message removes only that entry; deleting a user message automatically cascade-deletes the subsequent AI response.
- **Agent Loop Safety Cap:** `max_loops = 5` prevents runaway execution cycles and token exhaustion.

### Technical Trade-Offs Matrix
| Architectural Decision | Chosen Implementation | Alternative Approach | Engineering Rationale / Trade-Off Analysis |
| :--- | :--- | :--- | :--- |
| **MCP Process Lifecycle** | Per-call stdio client spawn (`stdio_client(params)`) | Persistent Daemon Process Pool | **Chosen:** Stateless execution, zero memory leaks, and clean subprocess cleanup. <br>**Trade-off:** Adds process initialization overhead to each tool invocation. |
| **Data Persistence** | Embedded SQLite database (`check_same_thread=False`) | Client-Server PostgreSQL / Redis | **Chosen:** Zero external dependencies and instant local setup. <br>**Trade-off:** Lacks horizontal scaling and multi-process concurrency locks. |
| **Concurrency Architecture** | Flask + On-demand `asyncio` event loop | Native Async Framework (FastAPI / Quart) | **Chosen:** Simpler synchronous routing and template rendering. <br>**Trade-off:** Creating and tearing down event loops per agent chat request introduces slight overhead. |
| **Context History Window** | Fixed message slicing (`messages.slice(-4)`) | Dynamic Token Summarization / Vector RAG | **Chosen:** Minimal overhead and predictable token usage. <br>**Trade-off:** Drops conversational context beyond the 4-message boundary. |
| **Tool Execution Security** | Unsandboxed local execution (`shell=True`) | Containerized Docker Sandboxing | **Chosen:** Direct access to host utilities and filesystem. <br>**Trade-off:** Exposes the host system to prompt injection vulnerabilities. |

---

## 7. Repository Structure

```text
SathanAIChat/
├── main.py                       # Primary Flask app, API routes, streaming chat, MCP registry
├── Connection.py                 # Minimal OpenAI client connectivity sample
├── 1.txt                         # Local scratch file (non-runtime)
├── .gitignore
├── Test/
│   ├── test.py                   # Standalone connection test script with browser spoofing
│   └── test_api.py               # Alternate Flask API test harness
├── templates/
│   └── index.html                # Single-page interface, SSE client, and state management
├── static/
│   ├── ico.ico
│   ├── logo.png
│   └── uploads/                  # Runtime upload destination (git-ignored)
└── mcp_servers/
    ├── api_client.py             # HTTP endpoint reachability tool
    ├── browser.py                # Webpage text extraction tool
    ├── filesystem.py             # Local file read and directory listing tools
    ├── google_workspace.py       # Gmail, Drive, Calendar tools via OAuth tokens
    ├── local_history.py          # Browser history extractor (Chrome, Edge, Brave, Firefox)
    ├── network.py                # Nmap network scanning tool
    ├── os_services.py            # OS service status and management tools
    ├── postgres_db.py            # PostgreSQL verification hook
    ├── system_controller.py      # Infrastructure health and service orchestration
    └── terminal.py               # Bash command execution tool
```

---

## 8. API Surface

### Authentication
- `GET /api/auth/google/login`: Initiates Google OAuth 2.0 authorization redirect.
- `GET /api/auth/google/callback`: Handles OAuth callback, exchanges authorization code, and stores token in SQLite.

### Settings
- `GET /api/settings`: Retrieves current base URL, model name, and API key.
- `POST /api/settings`: Updates model configuration in SQLite.

### Threads & Messages
- `GET /api/threads`: Lists all threads (supports `?q=` keyword search).
- `POST /api/threads`: Creates a new conversation thread.
- `DELETE /api/threads/<thread_id>`: Permanently deletes a thread and all associated messages.
- `PATCH /api/threads/<thread_id>/pin`: Toggles thread pinned status.
- `PATCH /api/threads/<thread_id>/rename`: Updates thread title.
- `GET /api/threads/<thread_id>/messages`: Fetches chronological messages for a thread.
- `DELETE /api/messages/<message_id>`: Deletes a message (and subsequent AI message if user message).
- `POST /api/threads/<thread_id>/truncate`: Deletes all messages in a thread starting from a specified message ID.

### Uploads & Media
- `POST /api/upload`: Handles multipart file and image uploads to `static/uploads/`.
- `POST /api/upload-text`: Ingests large text strings and saves them as `.txt` files.

### Integrations
- `GET /api/integrations`: Returns authentication and enabled state for Google Workspace.
- `POST /api/integrations/toggle`: Enables or disables a specific integration service.

### Chat & Streaming
- `POST /api/chat`: Primary endpoint supporting SSE streaming for General AI and Agent modes.

---

## 9. Setup & Run

### Prerequisites
- Python 3.10+
- SQLite 3 (bundled with Python)
- Optional host tools for full MCP capability: `nmap`, `docker`, `systemctl`, `sudo`.

### Installation
```bash
pip install flask requests python-dotenv authlib openai mcp beautifulsoup4 google-auth google-api-python-client
```

### Environment Configuration (`.env`)
```env
FLASK_SECRET_KEY=your_secure_random_key
GOOGLE_CLIENT_ID=your_google_oauth_client_id
GOOGLE_CLIENT_SECRET=your_google_oauth_client_secret
```

### Starting the Application
```bash
python main.py
```
Access the application at `http://127.0.0.1:5000`.
