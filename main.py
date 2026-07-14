import sys
import os
import json
import threading
import re
import sqlite3
import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QTextEdit, QLineEdit, QPushButton, QLabel, QFrame, QGraphicsOpacityEffect,
    QDialog, QFormLayout, QDialogButtonBox, QListWidget, QListWidgetItem, QAbstractItemView,
    QStackedWidget  # <--- Add this
)
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, pyqtSignal, QObject, QPoint, QTimer # <--- Add QTimer
from PyQt6.QtGui import QColor, QFont
import requests

# --------------------------------------------------------------------------
# Design Tokens & Theming
# --------------------------------------------------------------------------
THEME_LIGHT = {
    "bg": "#FCF8F8",
    "sidebar_bg": "#F4ECEC",
    "fg": "#2D1515",
    "accent": "#C85050",
    "muted": "#8A5050",
    "border": "#E8D8D8",
    "input_bg": "#FFFFFF",
    "ghost_hover": "#FFF0F0",
    "list_hover": "#E8D8D8",
    "list_selected": "#E0C8C8"
}

THEME_DARK = {
    "bg": "#1A1010",
    "sidebar_bg": "#140B0B",
    "fg": "#F5EBEB",
    "accent": "#E56B6B",
    "muted": "#B38282",
    "border": "#2D1A1A",
    "input_bg": "#251818",
    "ghost_hover": "#331F1F",
    "list_hover": "#2D1A1A",
    "list_selected": "#3D2525"
}

CONFIG_FILE = "satan_config.json"
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
        self.conn.commit()

    def create_thread(self, title="New Chat"):
        cursor = self.conn.cursor()
        # Convert datetime to string explicitly for Python 3.12+
        now_str = datetime.datetime.now().isoformat() 
        cursor.execute("INSERT INTO threads (title, updated_at) VALUES (?, ?)", (title, now_str))
        self.conn.commit()
        return cursor.lastrowid

    def update_thread_title(self, thread_id, title):
        cursor = self.conn.cursor()
        now_str = datetime.datetime.now().isoformat()
        cursor.execute("UPDATE threads SET title = ?, updated_at = ? WHERE id = ?", 
                       (title, now_str, thread_id))
        self.conn.commit()

    def save_message(self, thread_id, role, content):
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO messages (thread_id, role, content) VALUES (?, ?, ?)", 
                       (thread_id, role, content))
        
        now_str = datetime.datetime.now().isoformat()
        cursor.execute("UPDATE threads SET updated_at = ? WHERE id = ?", 
                       (now_str, thread_id))
        self.conn.commit()

    def get_threads(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, title FROM threads ORDER BY updated_at DESC")
        return cursor.fetchall()

    def get_messages(self, thread_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT role, content FROM messages WHERE thread_id = ? ORDER BY id ASC", (thread_id,))
        return cursor.fetchall()
# --------------------------------------------------------------------------
# API Layer
# --------------------------------------------------------------------------
class WorkerSignals(QObject):
    chunk_received = pyqtSignal(str)
    stream_done = pyqtSignal()

class PyQtAPIClient:
    def __init__(self, config):
        self.update_config(config)
        self.signals = WorkerSignals()

    def update_config(self, config):
        self.base_url = config.get("base_url", "").strip().rstrip('/')
        self.model = config.get("model", "").strip().replace("models/", "")
        self.key = config.get("key", "").strip()

    def stream(self, messages):
        def run():
            try:
                if "generativelanguage" in self.base_url:
                    url = f"{self.base_url}/models/{self.model}:streamGenerateContent?alt=sse&key={self.key}"
                    payload = {"contents": [{"role": "model" if m["role"] == "ai" else "user", "parts": [{"text": m["content"]}]} for m in messages]}
                    
                    with requests.post(url, json=payload, headers={'Content-Type': 'application/json'}, stream=True) as r:
                        r.raise_for_status()
                        for line in r.iter_lines():
                            if line:
                                decoded = line.decode('utf-8')
                                if decoded.startswith("data: ") and decoded != "data: [DONE]":
                                    try:
                                        chunk = json.loads(decoded[6:])['candidates'][0]['content']['parts'][0]['text']
                                        self.signals.chunk_received.emit(chunk)
                                    except: pass
                else:
                    url = f"{self.base_url}/chat/completions" if not self.base_url.endswith("/chat/completions") else self.base_url
                    payload = {"model": self.model, "messages": [{"role": "assistant" if m["role"] == "ai" else "user", "content": m["content"]} for m in messages], "stream": True}
                    
                    with requests.post(url, json=payload, headers={'Authorization': f'Bearer {self.key}'}, stream=True) as r:
                        r.raise_for_status()
                        for line in r.iter_lines():
                            if line:
                                decoded = line.decode('utf-8')
                                if decoded.startswith("data: ") and decoded != "data: [DONE]":
                                    try:
                                        chunk = json.loads(decoded[6:])['choices'][0]['delta'].get('content', '')
                                        if chunk: self.signals.chunk_received.emit(chunk)
                                    except: pass
            except Exception as e:
                self.signals.chunk_received.emit(f"\n[Error: {str(e)}]")
            finally:
                self.signals.stream_done.emit()

        threading.Thread(target=run, daemon=True).start()

# --------------------------------------------------------------------------
# Settings Modal Dialog
# --------------------------------------------------------------------------
class SettingsDialog(QDialog):
    def __init__(self, current_config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SatanAI Configuration")
        self.setFixedWidth(450)
        
        layout = QFormLayout(self)
        layout.setSpacing(15)
        
        self.url_ent = QLineEdit(current_config.get("base_url", ""))
        self.url_ent.setPlaceholderText("e.g., http://localhost:11434/v1")
        self.mod_ent = QLineEdit(current_config.get("model", ""))
        self.mod_ent.setPlaceholderText("e.g., llama3")
        self.key_ent = QLineEdit(current_config.get("key", ""))
        self.key_ent.setEchoMode(QLineEdit.EchoMode.Password)
        
        layout.addRow("Base URL:", self.url_ent)
        layout.addRow("Model Name:", self.mod_ent)
        layout.addRow("API Key:", self.key_ent)
        
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def get_data(self):
        return {
            "base_url": self.url_ent.text(),
            "model": self.mod_ent.text(),
            "key": self.key_ent.text()
        }
# --------------------------------------------------------------------------
# Custom Animated Label
# --------------------------------------------------------------------------
class AnimatedTitleLabel(QLabel):
    def __init__(self, text):
        super().__init__(text)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.step = 0
        self.direction = 1
        
        # Start a 30ms timer for a smooth 30fps color shift
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate_color)
        self.timer.start(30)
        
    def animate_color(self):
        # Ping-pong between 0 and 100 for color interpolation
        self.step += self.direction
        if self.step >= 100 or self.step <= 0:
            self.direction *= -1
            
        # Interpolate between SatanAI Red (#C85050) and a darker crimson
        r = int(200 - (self.step * 0.8))
        g = int(80 - (self.step * 0.4))
        b = int(80 - (self.step * 0.4))
        
        self.setStyleSheet(f"font-family: 'Georgia'; font-size: 48px; font-weight: bold; color: rgb({r}, {g}, {b});")
# --------------------------------------------------------------------------
# Main UI Application
# --------------------------------------------------------------------------
class MinimalSatanAI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SatanAI")
        self.resize(900, 700)
        self.is_dark = False
        
        # State Management
        self.messages = []
        self.current_thread_id = None
        self.db = DatabaseManager()
        
        # Load Config
        self.config = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                self.config = json.load(f)
        self.api = PyQtAPIClient(self.config)

        # Core Layout Setup
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.core_layout = QHBoxLayout(self.central_widget)
        self.core_layout.setContentsMargins(0, 0, 0, 0)
        self.core_layout.setSpacing(0)

        self.build_sidebar()
        self.build_chat_ui()
        self.apply_theme()
        
        # If no config, pop settings immediately
        if not self.config.get("base_url"):
            self.open_settings()

    def apply_theme(self):
        t = THEME_DARK if self.is_dark else THEME_LIGHT
        
        self.setStyleSheet(f"""
            QMainWindow {{ background-color: {t['bg']}; }}
            QWidget {{ color: {t['fg']}; font-family: 'Helvetica'; font-size: 14px; }}
            
            /* Sidebar */
            QFrame#sidebar {{ background-color: {t['sidebar_bg']}; border-right: 1px solid {t['border']}; }}
            
            /* List Widget (History) */
            QListWidget {{
                background-color: transparent; border: none; outline: none;
            }}
            QListWidget::item {{ padding: 10px; border-radius: 6px; margin: 2px 10px; }}
            QListWidget::item:hover {{ background-color: {t['list_hover']}; }}
            QListWidget::item:selected {{ background-color: {t['list_selected']}; font-weight: bold; color: {t['accent']}; }}
            
            /* Inputs */
            QLineEdit {{
                background-color: {t['input_bg']}; border: 1px solid {t['border']};
                border-radius: 8px; padding: 10px; color: {t['fg']};
            }}
            QLineEdit:focus {{ border: 1px solid {t['accent']}; }}
            
            /* Chat Area Custom Scrollbar */
            QTextEdit {{ background-color: transparent; border: none; color: {t['fg']}; }}
            QScrollBar:vertical {{ border: none; background: transparent; width: 6px; margin: 0px; }}
            QScrollBar::handle:vertical {{ background: {t['border']}; border-radius: 3px; min-height: 20px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ border: none; background: transparent; }}
            
            /* Buttons */
            QPushButton#primary_cta {{
                background-color: {t['accent']}; color: #FFFFFF; border-radius: 8px; font-weight: bold; padding: 10px;
            }}
            QPushButton#primary_cta:hover {{ background-color: {t['muted']}; }}
            
            QPushButton#ghost_btn {{
                background-color: transparent; border: 1px solid {t['border']}; color: {t['muted']};
                border-radius: 6px; padding: 5px 12px;
            }}
            QPushButton#ghost_btn:hover {{
                background-color: {t['ghost_hover']}; border: 1px solid {t['accent']}; color: {t['accent']};
            }}
        """)

    def build_sidebar(self):
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(260)
        layout = QVBoxLayout(self.sidebar)
        layout.setContentsMargins(10, 20, 10, 20)

        # New Chat Button
        self.new_chat_btn = QPushButton("+ New Chat")
        self.new_chat_btn.setObjectName("primary_cta")
        self.new_chat_btn.clicked.connect(self.start_new_thread)
        layout.addWidget(self.new_chat_btn)

        # History List
        self.history_list = QListWidget()
        self.history_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.history_list.itemClicked.connect(self.on_thread_selected)
        layout.addWidget(self.history_list)
        self.refresh_history_list()

        # Bottom Utilities
        layout.addStretch()
        
        self.theme_btn = QPushButton("🌙 Dark Mode")
        self.theme_btn.setObjectName("ghost_btn")
        self.theme_btn.clicked.connect(self.toggle_theme)
        layout.addWidget(self.theme_btn)

        self.settings_btn = QPushButton("⚙️ Settings")
        self.settings_btn.setObjectName("ghost_btn")
        self.settings_btn.clicked.connect(self.open_settings)
        layout.addWidget(self.settings_btn)

        self.core_layout.addWidget(self.sidebar)

    def build_chat_ui(self):
        self.chat_container = QWidget()
        layout = QVBoxLayout(self.chat_container)
        layout.setContentsMargins(30, 30, 30, 30)

        # Create a Stacked Widget to manage "Empty State" vs "Active Chat"
        self.chat_stack = QStackedWidget()

        # --- PAGE 0: Empty State (Centered Gradient Name) ---
        self.empty_page = QWidget()
        empty_layout = QVBoxLayout(self.empty_page)
        self.animated_title = AnimatedTitleLabel("How can I help you today?")
        empty_layout.addWidget(self.animated_title, alignment=Qt.AlignmentFlag.AlignCenter)
        self.chat_stack.addWidget(self.empty_page)

        # --- PAGE 1: Active Chat Area ---
        self.active_page = QWidget()
        active_layout = QVBoxLayout(self.active_page)
        active_layout.setContentsMargins(0, 0, 0, 0)
        
        self.header_title = QLabel("New Chat")
        self.header_title.setStyleSheet("font-family: 'Georgia'; font-size: 22px; font-weight: bold; color: #C85050;")
        active_layout.addWidget(self.header_title)

        self.chat_box = QTextEdit()
        self.chat_box.setReadOnly(True)
        active_layout.addWidget(self.chat_box)
        self.chat_stack.addWidget(self.active_page)

        # Add the stack to the main layout
        layout.addWidget(self.chat_stack)

        # --- Bottom Input Area (Visible on both pages) ---
        input_frame = QHBoxLayout()
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Message SatanAI...")
        self.entry.setFixedHeight(45)
        self.entry.returnPressed.connect(self.send_message)
        input_frame.addWidget(self.entry)

        self.send_btn = QPushButton("↑")
        self.send_btn.setObjectName("primary_cta")
        self.send_btn.setFixedSize(45, 45)
        self.send_btn.clicked.connect(self.send_message)
        input_frame.addWidget(self.send_btn)

        layout.addLayout(input_frame)
        self.core_layout.addWidget(self.chat_container)
        
        self.start_new_thread()
        self.animate_fade_in(self.chat_container)

    def open_settings(self):
        dialog = SettingsDialog(self.config, self)
        if dialog.exec():
            self.config = dialog.get_data()
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.config, f)
            self.api.update_config(self.config)

    def toggle_theme(self):
        self.is_dark = not self.is_dark
        self.theme_btn.setText("☀️ Light Mode" if self.is_dark else "🌙 Dark Mode")
        self.apply_theme()
        self.redraw_chat_history()

    def refresh_history_list(self):
        self.history_list.clear()
        threads = self.db.get_threads()
        for t_id, title in threads:
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, t_id)
            self.history_list.addItem(item)

    def start_new_thread(self):
        self.current_thread_id = None
        self.messages.clear()
        self.chat_box.clear()
        self.header_title.setText("New Chat")
        self.history_list.clearSelection()
        
        # Switch to the centered animated greeting
        self.chat_stack.setCurrentIndex(0) 

    def on_thread_selected(self, item):
        thread_id = item.data(Qt.ItemDataRole.UserRole)
        self.current_thread_id = thread_id
        self.header_title.setText(item.text())
        
        # Switch to the active chat box
        self.chat_stack.setCurrentIndex(1)
        
        self.messages = []
        self.chat_box.clear()
        db_messages = self.db.get_messages(thread_id)
        
        for role, content in db_messages:
            self.messages.append({"role": role, "content": content})
            is_ai = (role == "ai")
            label = "SATANAI" if is_ai else "YOU"
            self.append_formatted(label, content, is_ai)
            
        self.animate_fade_in(self.chat_container)

    def redraw_chat_history(self):
        # Used strictly when theme changes to safely remap HTML colors
        old_messages = self.messages.copy()
        self.chat_box.clear()
        self.messages.clear()
        for msg in old_messages:
            self.messages.append(msg)
            self.append_formatted("YOU" if msg["role"] == "user" else "SATANAI", msg["content"], msg["role"] == "ai")

    def send_message(self):
        text = self.entry.text().strip()
        if not text: return
        self.entry.clear()
        
        # Ensure we are looking at the chat box, not the empty state
        self.chat_stack.setCurrentIndex(1)
        
        if self.current_thread_id is None:
            title = text[:25] + "..." if len(text) > 25 else text
            self.current_thread_id = self.db.create_thread(title)
            self.header_title.setText(title)
            self.refresh_history_list()
        
        self.messages.append({"role": "user", "content": text})
        self.db.save_message(self.current_thread_id, "user", text)
        
        self.append_formatted("YOU", text, is_ai=False)
        self.append_formatted("SATANAI", "", is_ai=True)

        # LOCK THE UI AND SHOW THINKING
        self.send_btn.setEnabled(False)
        self.entry.setEnabled(False)
        self.entry.setPlaceholderText("SatanAI is thinking...")
        
        self.current_ai_text = ""
        self.api.signals.chunk_received.connect(self.handle_chunk)
        self.api.signals.stream_done.connect(self.handle_done)
        self.api.stream(self.messages)

    def handle_done(self):
        self.api.signals.chunk_received.disconnect(self.handle_chunk)
        self.api.signals.stream_done.disconnect(self.handle_done)
        
        self.messages.append({"role": "ai", "content": self.current_ai_text})
        self.db.save_message(self.current_thread_id, "ai", self.current_ai_text)
        
        # UNLOCK THE UI
        self.send_btn.setEnabled(True)
        self.entry.setEnabled(True)
        self.entry.setPlaceholderText("Message SatanAI...")
        self.entry.setFocus()

    def handle_chunk(self, chunk):
        self.current_ai_text += chunk
        cursor = self.chat_box.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.chat_box.setTextCursor(cursor)
        
        self.chat_box.undo() 
        t = THEME_DARK if self.is_dark else THEME_LIGHT
        
        formatted_body = self.current_ai_text.replace("\n", "<br>")
        formatted_body = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", formatted_body)
        formatted_body = re.sub(r"`(.*?)`", f"<span style='font-family:Consolas; color:{t['accent']};'>\\1</span>", formatted_body)

        html = f"""
        <div style='margin-bottom: 10px;'>
            <span style='font-size: 11px; font-weight: bold; color: {t['muted']};'>SATANAI</span><br>
            <span style='color: {t['fg']};'>{formatted_body}</span>
        </div>
        """
        self.chat_box.insertHtml(html)

    def append_formatted(self, label, content, is_ai=False):
        t = THEME_DARK if self.is_dark else THEME_LIGHT
        color_label = t['muted'] if is_ai else t['accent']
        
        formatted_body = content.replace("\n", "<br>")
        formatted_body = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", formatted_body)
        formatted_body = re.sub(r"`(.*?)`", f"<span style='font-family:Consolas; color:{t['accent']};'>\\1</span>", formatted_body)
        
        html = f"""
        <div style='margin-bottom: 10px;'>
            <span style='font-size: 11px; font-weight: bold; color: {color_label};'>{label}</span><br>
            <span style='color: {t['fg']};'>{formatted_body}</span>
        </div>
        """
        self.chat_box.insertHtml(html)
        self.chat_box.append("")
        
    def animate_fade_in(self, target_widget):
        opacity_effect = QGraphicsOpacityEffect(target_widget)
        target_widget.setGraphicsEffect(opacity_effect)
        
        self.fade_anim = QPropertyAnimation(opacity_effect, b"opacity")
        self.fade_anim.setDuration(350)
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        self.pos_anim = QPropertyAnimation(target_widget, b"pos")
        self.pos_anim.setDuration(350)
        current_pos = target_widget.pos()
        self.pos_anim.setStartValue(current_pos + QPoint(0, 15))
        self.pos_anim.setEndValue(current_pos)
        self.pos_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        self.fade_anim.start()
        self.pos_anim.start()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MinimalSatanAI()
    window.show()
    sys.exit(app.exec())