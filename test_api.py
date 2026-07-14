import json
import requests
import sqlite3
import datetime
from flask import Flask, render_template, request, Response, jsonify

app = Flask(__name__)
DB_FILE = "satan_history.db"

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
        cursor.execute("SELECT COUNT(*) FROM settings")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO settings (id, base_url, model_name, api_key) VALUES (1, 'https://generativelanguage.googleapis.com/v1beta', 'gemini-1.5-flash', '')")
            
        try: cursor.execute("ALTER TABLE threads ADD COLUMN is_pinned INTEGER DEFAULT 0")
        except sqlite3.OperationalError: pass
        self.conn.commit()

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
        threads = [{"id": t[0], "title": t[1], "is_pinned": bool(t[2])} for t in db.get_threads()]
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

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    messages = data.get('messages', [])
    base_url = data.get('base_url', '').strip().rstrip('/')
    model = data.get('model', '').strip().replace("models/", "")
    api_key = data.get('api_key', '').strip()
    thread_id = data.get('thread_id')
    
    if not base_url or not model:
        return jsonify({"error": "Base URL and Model Name are required"}), 400

    if thread_id and len(messages) > 0 and messages[-1]['role'] == 'user':
        db.save_message(thread_id, "user", messages[-1]['content'])

    def generate():
        ai_response_cache = ""
        try:
            if "generativelanguage" in base_url:
                url = f"{base_url}/models/{model}:streamGenerateContent?alt=sse&key={api_key}"
                payload = {"contents": [{"role": "model" if m["role"] == "ai" else "user", "parts": [{"text": m["content"]}]} for m in messages]}
                with requests.post(url, json=payload, headers={'Content-Type': 'application/json'}, stream=True) as r:
                    if r.status_code != 200:
                        yield f"data: {json.dumps({'error': f'API Error {r.status_code}: {r.text}'})}\n\n"
                        return
                    for line in r.iter_lines():
                        if line:
                            decoded = line.decode('utf-8')
                            if decoded.startswith("data: ") and decoded != "data: [DONE]":
                                try:
                                    chunk = json.loads(decoded[6:])['candidates'][0]['content']['parts'][0]['text']
                                    ai_response_cache += chunk
                                    yield f"data: {json.dumps({'text': chunk})}\n\n"
                                except Exception: pass
            else:
                url = f"{base_url}/chat/completions" if not base_url.endswith("/chat/completions") else base_url
                payload = {"model": model, "messages": [{"role": "assistant" if m["role"] == "ai" else "user", "content": m["content"]} for m in messages], "stream": True}
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
                                    chunk = json.loads(decoded[6:])['choices'][0]['delta'].get('content', '')
                                    if chunk:
                                        ai_response_cache += chunk
                                        yield f"data: {json.dumps({'text': chunk})}\n\n"
                                except Exception: pass
                                
            if thread_id and ai_response_cache:
                db.save_message(thread_id, "ai", ai_response_cache)
                
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return Response(generate(), mimetype='text/event-stream')

if __name__ == '__main__':
    app.run(debug=True, port=5000)