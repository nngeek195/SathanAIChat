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
        cursor.execute('''CREATE TABLE IF NOT EXISTS threads 
                          (id INTEGER PRIMARY KEY, title TEXT, updated_at TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS messages 
                          (id INTEGER PRIMARY KEY, thread_id INTEGER, role TEXT, content TEXT, 
                           FOREIGN KEY(thread_id) REFERENCES threads(id))''')
        try:
            cursor.execute("ALTER TABLE threads ADD COLUMN is_pinned INTEGER DEFAULT 0")
        except sqlite3.OperationalError: pass
        self.conn.commit()

    def create_thread(self, title="New Chat"):
        cursor = self.conn.cursor()
        now_str = datetime.datetime.now().isoformat() 
        cursor.execute("INSERT INTO threads (title, updated_at, is_pinned) VALUES (?, ?, 0)", (title, now_str))
        self.conn.commit()
        return cursor.lastrowid

    def save_message(self, thread_id, role, content):
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO messages (thread_id, role, content) VALUES (?, ?, ?)", 
                       (thread_id, role, content))
        now_str = datetime.datetime.now().isoformat()
        cursor.execute("UPDATE threads SET updated_at = ? WHERE id = ?", (now_str, thread_id))
        self.conn.commit()

    def get_threads(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, title, is_pinned FROM threads ORDER BY is_pinned DESC, updated_at DESC")
        return cursor.fetchall()

    def get_messages(self, thread_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT role, content FROM messages WHERE thread_id = ? ORDER BY id ASC", (thread_id,))
        return cursor.fetchall()

    def delete_thread(self, thread_id):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM messages WHERE thread_id = ?", (thread_id,))
        cursor.execute("DELETE FROM threads WHERE id = ?", (thread_id,))
        self.conn.commit()

    def toggle_pin(self, thread_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT is_pinned FROM threads WHERE id = ?", (thread_id,))
        current_status = cursor.fetchone()[0]
        new_status = 1 if current_status == 0 else 0
        cursor.execute("UPDATE threads SET is_pinned = ? WHERE id = ?", (new_status, thread_id))
        self.conn.commit()
        return new_status
        
    def rename_thread(self, thread_id, new_title):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE threads SET title = ? WHERE id = ?", (new_title, thread_id))
        self.conn.commit()

db = DatabaseManager()

# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/threads', methods=['GET', 'POST'])
def handle_threads():
    if request.method == 'GET':
        threads = [{"id": t[0], "title": t[1], "is_pinned": bool(t[2])} for t in db.get_threads()]
        return jsonify({"threads": threads})
    elif request.method == 'POST':
        title = request.json.get("title", "New Chat")
        thread_id = db.create_thread(title)
        return jsonify({"thread_id": thread_id})

@app.route('/api/threads/<int:thread_id>', methods=['DELETE'])
def delete_thread(thread_id):
    db.delete_thread(thread_id)
    return jsonify({"success": True})

@app.route('/api/threads/<int:thread_id>/pin', methods=['PATCH'])
def pin_thread(thread_id):
    new_status = db.toggle_pin(thread_id)
    return jsonify({"success": True, "is_pinned": bool(new_status)})

@app.route('/api/threads/<int:thread_id>/rename', methods=['PATCH'])
def rename_thread(thread_id):
    new_title = request.json.get("title")
    if new_title:
        db.rename_thread(thread_id, new_title)
    return jsonify({"success": True})

@app.route('/api/threads/<int:thread_id>/messages', methods=['GET'])
def get_thread_messages(thread_id):
    messages = [{"role": m[0], "content": m[1]} for m in db.get_messages(thread_id)]
    return jsonify({"messages": messages})

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

    last_user_message = messages[-1]['content']
    if thread_id:
        db.save_message(thread_id, "user", last_user_message)

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