import json
import requests
import sqlite3
import datetime
import os
import base64
import asyncio
from flask import Flask, render_template, request, Response, jsonify
from werkzeug.utils import secure_filename
import subprocess
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials

app = Flask(__name__)
DB_FILE = "satan_history.db"
UPLOAD_FOLDER = os.path.join('static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


if len(sys.argv) > 2 and sys.argv[1] == "--run-mcp":
    target_server = sys.argv[2]
    
    if target_server == "browser":
        import mcp_servers.browser as server_module
    elif target_server == "filesystem":
        import mcp_servers.filesystem as server_module
    elif target_server == "history":
        import mcp_servers.local_history as server_module
    elif target_server == "system_controller":
        import mcp_servers.system_controller as server_module
    elif target_server == "network":
        import mcp_servers.network as server_module
    elif target_server == "postgres_db":
        import mcp_servers.postgres_db as server_module
    elif target_server == "api_client":
        import mcp_servers.api_client as server_module
    elif target_server == "terminal":
        import mcp_servers.terminal as server_module
        
    server_module.mcp.run()
    sys.exit(0)

class LocalMCPRegistry:
    def __init__(self):
        is_compiled = getattr(sys, 'frozen', False)
        base_cmd = sys.executable
        
        def get_args(server_name):
            if is_compiled:
                return ["--run-mcp", server_name]
            return [f"mcp_servers/{server_name}.py"]

        self.configs = {
            "browser": StdioServerParameters(command=base_cmd, args=get_args("browser")),
            "filesystem": StdioServerParameters(command=base_cmd, args=get_args("filesystem")),
            "history": StdioServerParameters(command=base_cmd, args=get_args("history")),
            "google_workspace": StdioServerParameters(command=base_cmd, args=get_args("google_workspace")), # Google MCP
            "system_controller": StdioServerParameters(command=base_cmd, args=get_args("system_controller")),
            "network": StdioServerParameters(command=base_cmd, args=get_args("network")),
            "postgres_db": StdioServerParameters(command=base_cmd, args=get_args("postgres_db")),
            "api_client": StdioServerParameters(command=base_cmd, args=get_args("api_client")),
            "terminal": StdioServerParameters(command=base_cmd, args=get_args("terminal"))
        }

    async def fetch_all_agent_tools(self, active_services=None):
        """Fetches tools only for services that are active/authenticated by the user."""
        llm_tools = []
        for server_key, params in self.configs.items():
            # If server is Google Workspace, check if user authenticated & enabled it
            if server_key == "google_workspace" and (not active_services or "google_workspace" not in active_services):
                continue

            try:
                async with stdio_client(params) as (read_stream, write_stream):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        tools_res = await session.list_tools()
                        
                        for t in tools_res.tools:
                            llm_tools.append({
                                "type": "function",
                                "function": {
                                    "name": f"{server_key}___{t.name}",
                                    "description": t.description,
                                    "parameters": t.inputSchema
                                }
                            })
            except Exception as e:
                print(f"Skipping server '{server_key}': {e}")
        return llm_tools

    async def run_tool_execution(self, server_key: str, tool_name: str, tool_arguments: dict):
        """Connects via stdio to execute requested parameters locally."""
        params = self.configs.get(server_key)
        if not params:
            return f"Error: Server target description mapping for key '{server_key}' not resolved."
            
        try:
            async with stdio_client(params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    response = await session.call_tool(tool_name, arguments=tool_arguments)
                    result_text = "\n".join([c.text for c in response.content if hasattr(c, 'text')])
                    return result_text
        except Exception as e:
            return f"Error executing inner server scope handler {tool_name}: {str(e)}"

mcp_registry = LocalMCPRegistry()

# --------------------------------------------------------------------------
# Database Manager Layer
# --------------------------------------------------------------------------
class DatabaseManager:
    def __init__(self, db_name=DB_FILE):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS threads (id INTEGER PRIMARY KEY, title TEXT, updated_at TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, thread_id INTEGER, role TEXT, content TEXT, FOREIGN KEY(thread_id) REFERENCES threads(id))''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, base_url TEXT, model_name TEXT, api_key TEXT)''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS integrations (
            service_id TEXT PRIMARY KEY,
            service_name TEXT,
            is_enabled INTEGER DEFAULT 0,
            auth_token TEXT
        )''')
        
        cursor.execute("SELECT COUNT(*) FROM settings")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO settings (id, base_url, model_name, api_key) VALUES (1, 'https://generativelanguage.googleapis.com/v1beta', 'gemini-1.5-flash', '')")
            
        try: cursor.execute("ALTER TABLE threads ADD COLUMN is_pinned INTEGER DEFAULT 0")
        except sqlite3.OperationalError: pass
        self.conn.commit()

    def get_integration(self, service_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT service_id, service_name, is_enabled, auth_token FROM integrations WHERE service_id = ?", (service_id,))
        row = cursor.fetchone()
        if row:
            return {"service_id": row[0], "service_name": row[1], "is_enabled": bool(row[2]), "auth_token": json.loads(row[3]) if row[3] else None}
        return {"service_id": service_id, "service_name": service_id, "is_enabled": False, "auth_token": None}

    def save_integration(self, service_id, service_name, is_enabled, auth_token_dict):
        cursor = self.conn.cursor()
        token_str = json.dumps(auth_token_dict) if auth_token_dict else None
        cursor.execute('''INSERT INTO integrations (service_id, service_name, is_enabled, auth_token) 
                          VALUES (?, ?, ?, ?)
                          ON CONFLICT(service_id) DO UPDATE SET 
                          is_enabled=excluded.is_enabled, auth_token=COALESCE(excluded.auth_token, integrations.auth_token)''',
                       (service_id, service_name, 1 if is_enabled else 0, token_str))
        self.conn.commit()

    def get_all_active_integrations(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT service_id FROM integrations WHERE is_enabled = 1 AND auth_token IS NOT NULL")
        return [row[0] for row in cursor.fetchall()]

    def get_settings(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT base_url, model_name, api_key FROM settings WHERE id = 1")
        row = cursor.fetchone()
        return {"base_url": row[0], "model_name": row[1], "api_key": row[2]} if row else {}

    def save_settings(self, base_url, model_name, api_key):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE settings SET base_url = ?, model_name = ?, api_key = ? WHERE id = 1", (base_url, model_name, api_key))
        self.conn.commit()

    def create_thread(self, title="New Chat"):
        cursor = self.conn.cursor()
        now_str = datetime.datetime.now().isoformat() 
        cursor.execute("INSERT INTO threads (title, updated_at, is_pinned) VALUES (?, ?, 0)", (title, now_str))
        self.conn.commit()
        return cursor.lastrowid

    def get_threads(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, title, is_pinned FROM threads ORDER BY is_pinned DESC, updated_at DESC")
        return cursor.fetchall()
    
    def search_threads(self, query):
        cursor = self.conn.cursor()
        search_term = f"%{query}%"
        cursor.execute('''
            SELECT DISTINCT t.id, t.title, t.is_pinned 
            FROM threads t
            LEFT JOIN messages m ON t.id = m.thread_id
            WHERE t.title LIKE ? OR m.content LIKE ?
            ORDER BY t.is_pinned DESC, t.updated_at DESC
        ''', (search_term, search_term))
        return cursor.fetchall()
    
    def rename_thread(self, thread_id, new_title):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE threads SET title = ? WHERE id = ?", (new_title, thread_id))
        self.conn.commit()

    def delete_thread(self, thread_id):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM messages WHERE thread_id = ?", (thread_id,))
        cursor.execute("DELETE FROM threads WHERE id = ?", (thread_id,))
        self.conn.commit()

    def toggle_pin(self, thread_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT is_pinned FROM threads WHERE id = ?", (thread_id,))
        new_status = 1 if cursor.fetchone()[0] == 0 else 0
        cursor.execute("UPDATE threads SET is_pinned = ? WHERE id = ?", (new_status, thread_id))
        self.conn.commit()
        return new_status

    def save_message(self, thread_id, role, content):
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO messages (thread_id, role, content) VALUES (?, ?, ?)", (thread_id, role, content))
        msg_id = cursor.lastrowid
        now_str = datetime.datetime.now().isoformat()
        cursor.execute("UPDATE threads SET updated_at = ? WHERE id = ?", (now_str, thread_id))
        self.conn.commit()
        return msg_id

    def get_messages(self, thread_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, role, content FROM messages WHERE thread_id = ? ORDER BY id ASC", (thread_id,))
        return cursor.fetchall()

    def delete_message(self, message_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT thread_id, role, id FROM messages WHERE id = ?", (message_id,))
        row = cursor.fetchone()
        if not row: return
        t_id, role, m_id = row
        
        if role == 'ai':
            cursor.execute("DELETE FROM messages WHERE id = ?", (m_id,))
        else:
            cursor.execute("DELETE FROM messages WHERE id = ?", (m_id,))
            cursor.execute("SELECT id, role FROM messages WHERE thread_id = ? AND id > ? ORDER BY id ASC LIMIT 1", (t_id, m_id))
            next_msg = cursor.fetchone()
            if next_msg and next_msg[1] == 'ai':
                cursor.execute("DELETE FROM messages WHERE id = ?", (next_msg[0],))
        self.conn.commit()

    def truncate_thread(self, thread_id, from_message_id):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM messages WHERE thread_id = ? AND id >= ?", (thread_id, from_message_id))
        self.conn.commit()

db = DatabaseManager()

# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    if request.method == 'GET': return jsonify(db.get_settings())
    else:
        data = request.json
        db.save_settings(data.get('base_url', ''), data.get('model_name', ''), data.get('api_key', ''))
        return jsonify({"success": True})

@app.route('/api/threads', methods=['GET', 'POST'])
def handle_threads():
    if request.method == 'GET':
        query = request.args.get('q', '').strip()
        if query:
            threads_data = db.search_threads(query)
        else:
            threads_data = db.get_threads()
        threads = [{"id": t[0], "title": t[1], "is_pinned": bool(t[2])} for t in threads_data]
        return jsonify({"threads": threads})
    elif request.method == 'POST':
        title = request.json.get("title", "New Chat")
        return jsonify({"thread_id": db.create_thread(title)})

@app.route('/api/threads/<int:thread_id>', methods=['DELETE'])
def delete_thread(thread_id):
    db.delete_thread(thread_id)
    return jsonify({"success": True})

@app.route('/api/threads/<int:thread_id>/pin', methods=['PATCH'])
def pin_thread(thread_id):
    return jsonify({"success": True, "is_pinned": bool(db.toggle_pin(thread_id))})

@app.route('/api/threads/<int:thread_id>/rename', methods=['PATCH'])
def rename_thread(thread_id):
    if title := request.json.get("title"): db.rename_thread(thread_id, title)
    return jsonify({"success": True})

@app.route('/api/threads/<int:thread_id>/messages', methods=['GET'])
def get_thread_messages(thread_id):
    messages = [{"id": m[0], "role": m[1], "content": m[2]} for m in db.get_messages(thread_id)]
    return jsonify({"messages": messages})

@app.route('/api/messages/<int:message_id>', methods=['DELETE'])
def delete_message(message_id):
    db.delete_message(message_id)
    return jsonify({"success": True})

@app.route('/api/threads/<int:thread_id>/truncate', methods=['POST'])
def truncate_thread(thread_id):
    db.truncate_thread(thread_id, request.json.get("message_id"))
    return jsonify({"success": True})

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file chunk found"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Empty filename submitted"}), 400
        
    filename = secure_filename(f"{int(datetime.datetime.now().timestamp())}_{file.filename}")
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    return jsonify({
        "success": True, 
        "filename": file.filename, 
        "url": f"/static/uploads/{filename}"
    })

@app.route('/api/upload-text', methods=['POST'])
def upload_large_text():
    data = request.json
    text_content = data.get('text', '')
    if not text_content:
        return jsonify({"error": "No text content"}), 400
        
    filename = secure_filename(f"pasted_text_{int(datetime.datetime.now().timestamp())}.txt")
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(text_content)
        
    return jsonify({
        "success": True,
        "filename": filename,
        "url": f"/static/uploads/{filename}"
    })

@app.route('/api/integrations', methods=['GET'])
def get_integrations_status():
    google_data = db.get_integration("google_workspace")
    return jsonify({
        "google_workspace": {
            "authenticated": google_data["auth_token"] is not None,
            "enabled": google_data["is_enabled"]
        }
    })

@app.route('/api/integrations/toggle', methods=['POST'])
def toggle_integration():
    data = request.json
    service_id = data.get("service_id")
    enabled = data.get("enabled", False)
    
    current = db.get_integration(service_id)
    db.save_integration(service_id, current["service_name"], enabled, current["auth_token"])
    return jsonify({"success": True})

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    is_agent_active = data.get('agent_mode', False)
    messages = data.get('messages', [])
    base_url = data.get('base_url', '').strip().rstrip('/')
    model = data.get('model', '').strip().replace("models/", "")
    api_key = data.get('api_key', '').strip()
    thread_id = data.get('thread_id')
    active_image = data.get('active_image')
    
    if not base_url or not model:
        return jsonify({"error": "Base URL and Model Name are required"}), 400

    if thread_id and len(messages) > 0 and messages[-1]['role'] == 'user':
        db.save_message(thread_id, "user", messages[-1]['content'])

    SYSTEM_PROMPT = {
        "role": "system", 
        "content": "You are currently running inside the SatanAI interface, an advanced custom application developed by Niranga Kumara. If you are asked about the developer, the creator of this interface, or Niranga, you must provide his LinkedIn profile (https://lk.linkedin.com/in/niranga-nayanajith) and express gratitude to him for building this platform."
    }

    if is_agent_active:
        def run_agent_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                active_services = db.get_all_active_integrations()

                # Fetch tools synchronously for this request lifecycle thread
                tools = loop.run_until_complete(
                    mcp_registry.fetch_all_agent_tools(active_services=active_services)
                )

                agent_messages = [SYSTEM_PROMPT]
                for m in messages:
                    agent_messages.append({
                        "role": "assistant" if m["role"] == "ai" else "user", 
                        "content": m["content"]
                    })
                    
                url = f"{base_url}/chat/completions" if not base_url.endswith("/chat/completions") else base_url
                headers = {'Content-Type': 'application/json'}
                if api_key: headers['Authorization'] = f'Bearer {api_key}'

                max_loops = 5
                for _ in range(max_loops):
                    payload = {
                        "model": model,
                        "messages": agent_messages,
                        "tools": tools,
                        "stream": False  # Critical: Must be absolute text payload structure
                    }
                    
                    res = requests.post(url, json=payload, headers=headers)
                    if res.status_code != 200:
                        return {"error": f"API Endpoint Integration Error: {res.text}"}
                    
                    res_json = res.json()
                    if 'choices' not in res_json or len(res_json['choices']) == 0:
                        return {"error": "Invalid response content signature received from downstream target provider."}
                        
                    ai_message = res_json['choices'][0]['message']
                    
                    # Exit evaluation trace if tool invocation demands are absent
                    if not ai_message.get('tool_calls'):
                        final_text = ai_message.get('content', '')
                        if thread_id and final_text: 
                            db.save_message(thread_id, "ai", final_text)
                        return {"text": final_text}
                    
                    # Append active contextual memory state references
                    agent_messages.append(ai_message)
                    
                    for tool_call in ai_message['tool_calls']:
                        full_name = tool_call['function']['name']
                        args_str = tool_call['function']['arguments']
                        
                        try:
                            args = json.loads(args_str) if isinstance(args_str, str) else args_str
                            server_key, actual_tool_name = full_name.split('___', 1)
                            
                            tool_result = loop.run_until_complete(
                                mcp_registry.run_tool_execution(server_key, actual_tool_name, args)
                            )
                        except Exception as e:
                            tool_result = f"Local platform agent runtime routing failure: {str(e)}"
                            
                        agent_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call['id'],
                            "content": str(tool_result)
                        })
                return {"error": "Autonomous execution system trace halted: Context limit metrics hit maximum loop allocation depths."}
            finally:
                loop.close()

        try:
            return jsonify(run_agent_loop())
        except Exception as e:
            return jsonify({"error": str(e)})

    # Else fallback loop: Standard streaming setup
    def generate():
        ai_response_cache = ""
        try:
            if "generativelanguage" in base_url:
                url = f"{base_url}/models/{model}:streamGenerateContent?alt=sse&key={api_key}"
                contents = []
                system_instruction = {"parts": [{"text": SYSTEM_PROMPT["content"]}]}
                
                for m in messages:
                    contents.append({"role": "model" if m["role"] == "ai" else "user", "parts": [{"text": m["content"]}]})
                
                if active_image and len(contents) > 0 and contents[-1]["role"] == "user":
                    contents[-1]["parts"].append({
                        "inlineData": {
                            "mimeType": active_image["mime_type"],
                            "data": active_image["base64"]
                        }
                    })

                payload = {
                    "systemInstruction": system_instruction,
                    "contents": contents
                }
                
                with requests.post(url, json=payload, headers={'Content-Type': 'application/json'}, stream=True) as r:
                    if r.status_code != 200:
                        yield f"data: {json.dumps({'error': f'API Error {r.status_code}: {r.text}'})}\n\n"
                        return
                    for line in r.iter_lines():
                        if line:
                            decoded = line.decode('utf-8')
                            if decoded.startswith("data: ") and decoded != "data: [DONE]":
                                try:
                                    json_data = json.loads(decoded[6:])
                                    if 'candidates' in json_data and len(json_data['candidates']) > 0:
                                        chunk = json_data['candidates'][0]['content']['parts'][0]['text']
                                        ai_response_cache += chunk
                                        yield f"data: {json.dumps({'text': chunk})}\n\n"
                                        
                                    if 'usageMetadata' in json_data:
                                        usage = {
                                            "prompt_tokens": json_data['usageMetadata'].get('promptTokenCount', 0),
                                            "completion_tokens": json_data['usageMetadata'].get('candidatesTokenCount', 0),
                                            "total_tokens": json_data['usageMetadata'].get('totalTokenCount', 0)
                                        }
                                        yield f"data: {json.dumps({'usage': usage})}\n\n"
                                except Exception: pass
            else:
                url = f"{base_url}/chat/completions" if not base_url.endswith("/chat/completions") else base_url
                formatted_messages = [SYSTEM_PROMPT]
                
                for m in messages:
                    formatted_messages.append({"role": "assistant" if m["role"] == "ai" else "user", "content": m["content"]})
                
                if active_image and len(formatted_messages) > 0 and formatted_messages[-1]["role"] == "user":
                    text_prompt = formatted_messages[-1]["content"]
                    formatted_messages[-1]["content"] = [
                        {"type": "text", "text": text_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{active_image['mime_type']};base64,{active_image['base64']}"}}
                    ]

                payload = {
                    "model": model, 
                    "messages": formatted_messages, 
                    "stream": True,
                    "stream_options": {"include_usage": True}
                }
                
                headers = {'Content-Type': 'application/json'}
                if api_key: headers['Authorization'] = f'Bearer {api_key}'
                
                with requests.post(url, json=payload, headers=headers, stream=True) as r:
                    if r.status_code != 200:
                        yield f"data: {json.dumps({'error': f'API Error {r.status_code}: {r.text}'})}\n\n"
                        return
                    for line in r.iter_lines():
                        if line:
                            decoded = line.decode('utf-8')
                            if decoded.startswith("data: ") and decoded != "data: [DONE]":
                                try:
                                    json_data = json.loads(decoded[6:])
                                    if 'choices' in json_data and len(json_data['choices']) > 0:
                                        chunk = json_data['choices'][0]['delta'].get('content', '')
                                        if chunk:
                                            ai_response_cache += chunk
                                            yield f"data: {json.dumps({'text': chunk})}\n\n"
                                            
                                    if 'usage' in json_data and json_data['usage']:
                                        yield f"data: {json.dumps({'usage': json_data['usage']})}\n\n"
                                except Exception: pass
                                
            if thread_id and ai_response_cache:
                db.save_message(thread_id, "ai", ai_response_cache)
                
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return Response(generate(), mimetype='text/event-stream')

    # Else fallback loop: Standard streaming setup
    def generate():
        ai_response_cache = ""
        try:
            if "generativelanguage" in base_url:
                url = f"{base_url}/models/{model}:streamGenerateContent?alt=sse&key={api_key}"
                contents = []
                system_instruction = {"parts": [{"text": SYSTEM_PROMPT["content"]}]}
                
                for m in messages:
                    contents.append({"role": "model" if m["role"] == "ai" else "user", "parts": [{"text": m["content"]}]})
                
                if active_image and len(contents) > 0 and contents[-1]["role"] == "user":
                    contents[-1]["parts"].append({
                        "inlineData": {
                            "mimeType": active_image["mime_type"],
                            "data": active_image["base64"]
                        }
                    })

                payload = {
                    "systemInstruction": system_instruction,
                    "contents": contents
                }
                
                with requests.post(url, json=payload, headers={'Content-Type': 'application/json'}, stream=True) as r:
                    if r.status_code != 200:
                        yield f"data: {json.dumps({'error': f'API Error {r.status_code}: {r.text}'})}\n\n"
                        return
                    for line in r.iter_lines():
                        if line:
                            decoded = line.decode('utf-8')
                            if decoded.startswith("data: ") and decoded != "data: [DONE]":
                                try:
                                    json_data = json.loads(decoded[6:])
                                    if 'candidates' in json_data and len(json_data['candidates']) > 0:
                                        chunk = json_data['candidates'][0]['content']['parts'][0]['text']
                                        ai_response_cache += chunk
                                        yield f"data: {json.dumps({'text': chunk})}\n\n"
                                        
                                    if 'usageMetadata' in json_data:
                                        usage = {
                                            "prompt_tokens": json_data['usageMetadata'].get('promptTokenCount', 0),
                                            "completion_tokens": json_data['usageMetadata'].get('candidatesTokenCount', 0),
                                            "total_tokens": json_data['usageMetadata'].get('totalTokenCount', 0)
                                        }
                                        yield f"data: {json.dumps({'usage': usage})}\n\n"
                                except Exception: pass
            else:
                url = f"{base_url}/chat/completions" if not base_url.endswith("/chat/completions") else base_url
                formatted_messages = [SYSTEM_PROMPT]
                
                for m in messages:
                    formatted_messages.append({"role": "assistant" if m["role"] == "ai" else "user", "content": m["content"]})
                
                if active_image and len(formatted_messages) > 0 and formatted_messages[-1]["role"] == "user":
                    text_prompt = formatted_messages[-1]["content"]
                    formatted_messages[-1]["content"] = [
                        {"type": "text", "text": text_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{active_image['mime_type']};base64,{active_image['base64']}"}}
                    ]

                payload = {
                    "model": model, 
                    "messages": formatted_messages, 
                    "stream": True,
                    "stream_options": {"include_usage": True}
                }
                
                headers = {'Content-Type': 'application/json'}
                if api_key: headers['Authorization'] = f'Bearer {api_key}'
                
                with requests.post(url, json=payload, headers=headers, stream=True) as r:
                    if r.status_code != 200:
                        yield f"data: {json.dumps({'error': f'API Error {r.status_code}: {r.text}'})}\n\n"
                        return
                    for line in r.iter_lines():
                        if line:
                            decoded = line.decode('utf-8')
                            if decoded.startswith("data: ") and decoded != "data: [DONE]":
                                try:
                                    json_data = json.loads(decoded[6:])
                                    if 'choices' in json_data and len(json_data['choices']) > 0:
                                        chunk = json_data['choices'][0]['delta'].get('content', '')
                                        if chunk:
                                            ai_response_cache += chunk
                                            yield f"data: {json.dumps({'text': chunk})}\n\n"
                                            
                                    if 'usage' in json_data and json_data['usage']:
                                        yield f"data: {json.dumps({'usage': json_data['usage']})}\n\n"
                                except Exception: pass
                                
            if thread_id and ai_response_cache:
                db.save_message(thread_id, "ai", ai_response_cache)
                
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return Response(generate(), mimetype='text/event-stream')

if __name__ == '__main__':
    app.run(debug=True, port=5000)