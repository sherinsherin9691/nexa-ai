import sqlite3
import json
import uuid
from datetime import datetime

class LocalCollection:
    def __init__(self, table_name, db_path):
        self.table_name = table_name
        self.db_path = db_path
        
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def find_one(self, query):
        conn = self._connect()
        cursor = conn.cursor()
        if self.table_name == "users":
            email = query.get("email")
            cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
            row = cursor.fetchone()
            conn.close()
            if row:
                return {"email": row["email"], "password_hash": row["password_hash"]}
        elif self.table_name == "chats":
            chat_id = query.get("_id")
            if chat_id:
                cursor.execute("SELECT * FROM chats WHERE id = ?", (str(chat_id),))
                row = cursor.fetchone()
                conn.close()
                if row:
                    return {
                        "_id": row["id"],
                        "user_email": row["user_email"],
                        "title": row["title"],
                        "created_at": datetime.fromisoformat(row["created_at"]),
                        "messages": json.loads(row["messages"])
                    }
        return None

    def insert_one(self, doc):
        conn = self._connect()
        cursor = conn.cursor()
        if self.table_name == "users":
            cursor.execute("INSERT OR REPLACE INTO users (email, password_hash) VALUES (?, ?)", 
                           (doc["email"], doc["password_hash"]))
        elif self.table_name == "chats":
            doc_id = str(doc.get("_id", uuid.uuid4()))
            messages_json = json.loads(json.dumps(doc.get("messages", []), default=str))
            cursor.execute("INSERT INTO chats (id, user_email, title, created_at, messages) VALUES (?, ?, ?, ?, ?)",
                           (doc_id, doc["user_email"], doc["title"], doc["created_at"].isoformat(), json.dumps(messages_json)))
            doc["_id"] = doc_id
        elif self.table_name == "projects":
            doc_id = str(doc.get("_id", uuid.uuid4()))
            tasks_json = json.loads(json.dumps(doc.get("tasks", []), default=str))
            cursor.execute("INSERT INTO projects (id, user_email, name, tasks, created_at) VALUES (?, ?, ?, ?, ?)",
                           (doc_id, doc["user_email"], doc["name"], json.dumps(tasks_json), doc["created_at"].isoformat()))
            doc["_id"] = doc_id
        conn.commit()
        conn.close()
        
        class InsertResult:
            def __init__(self, inserted_id):
                self.inserted_id = inserted_id
        return InsertResult(doc.get("_id"))

    def find(self, query, projection=None):
        conn = self._connect()
        cursor = conn.cursor()
        results = []
        if self.table_name == "chats":
            email = query.get("user_email")
            cursor.execute("SELECT * FROM chats WHERE user_email = ? ORDER BY created_at DESC", (email,))
            rows = cursor.fetchall()
            for row in rows:
                results.append({
                    "_id": row["id"],
                    "user_email": row["user_email"],
                    "title": row["title"],
                    "created_at": datetime.fromisoformat(row["created_at"]),
                    "messages": json.loads(row["messages"])
                })
        elif self.table_name == "projects":
            email = query.get("user_email")
            cursor.execute("SELECT * FROM projects WHERE user_email = ? ORDER BY created_at DESC", (email,))
            rows = cursor.fetchall()
            for row in rows:
                results.append({
                    "_id": row["id"],
                    "user_email": row["user_email"],
                    "name": row["name"],
                    "tasks": json.loads(row["tasks"]),
                    "created_at": datetime.fromisoformat(row["created_at"])
                })
        conn.close()
        
        class CursorWrapper(list):
            def sort(self, key, direction=-1):
                # We sort directly in SELECT, so sort is a no-op that returns self
                return self
        return CursorWrapper(results)

    def update_one(self, filter_query, update_query):
        conn = self._connect()
        cursor = conn.cursor()
        doc_id = str(filter_query.get("_id"))
        
        if self.table_name == "chats":
            cursor.execute("SELECT * FROM chats WHERE id = ?", (doc_id,))
            row = cursor.fetchone()
            if row:
                messages = json.loads(row["messages"])
                push_data = update_query.get("$push", {})
                if "messages" in push_data:
                    messages_to_add = push_data["messages"]
                    if isinstance(messages_to_add, dict) and "$each" in messages_to_add:
                        for m in messages_to_add["$each"]:
                            m_copy = m.copy()
                            if "timestamp" in m_copy and isinstance(m_copy["timestamp"], datetime):
                                m_copy["timestamp"] = m_copy["timestamp"].isoformat()
                            messages.append(m_copy)
                    else:
                        m_copy = messages_to_add.copy()
                        if "timestamp" in m_copy and isinstance(m_copy["timestamp"], datetime):
                            m_copy["timestamp"] = m_copy["timestamp"].isoformat()
                        messages.append(m_copy)
                    
                    cursor.execute("UPDATE chats SET messages = ? WHERE id = ?", (json.dumps(messages), doc_id))
        elif self.table_name == "projects":
            push_data = update_query.get("$push", {})
            set_data = update_query.get("$set", {})
            cursor.execute("SELECT * FROM projects WHERE id = ?", (doc_id,))
            row = cursor.fetchone()
            if row:
                tasks = json.loads(row["tasks"])
                if "tasks" in push_data:
                    tasks.append(push_data["tasks"])
                elif set_data:
                    task_id = filter_query.get("tasks.id")
                    for k, val in set_data.items():
                        if "completed" in k:
                            for t in tasks:
                                if t["id"] == task_id:
                                    t["completed"] = val
                cursor.execute("UPDATE projects SET tasks = ? WHERE id = ?", (json.dumps(tasks), doc_id))
        conn.commit()
        conn.close()
        
        class UpdateResult:
            def __init__(self):
                self.modified_count = 1
        return UpdateResult()

    def delete_one(self, query):
        conn = self._connect()
        cursor = conn.cursor()
        doc_id = str(query.get("_id"))
        cursor.execute(f"DELETE FROM {self.table_name} WHERE id = ?", (doc_id,))
        conn.commit()
        conn.close()
        
        class DeleteResult:
            def __init__(self):
                self.deleted_count = 1
        return DeleteResult()

class LocalDatabase:
    def __init__(self, db_path="nexa_local.db"):
        self.db_path = db_path
        self._init_db()
        self.users = LocalCollection("users", db_path)
        self.chats = LocalCollection("chats", db_path)
        self.projects = LocalCollection("projects", db_path)

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                password_hash TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                user_email TEXT,
                title TEXT,
                created_at TEXT,
                messages TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                user_email TEXT,
                name TEXT,
                tasks TEXT,
                created_at TEXT
            )
        """)
        conn.commit()
        conn.close()
