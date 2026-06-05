import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import groq
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "nexa_super_secret_session_key_129837")

# Secure credentials configuration
ALLOWED_EMAIL = os.environ.get("ALLOWED_EMAIL", "nexa@chatbot.com").strip().lower()
ALLOWED_PASSWORD = os.environ.get("ALLOWED_PASSWORD", "nexa123").strip()

# Connect to MongoDB
db = None
try:
    mongo_uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
    mongo_client = MongoClient(mongo_uri, tlsAllowInvalidCertificates=True, serverSelectionTimeoutMS=1500, socketTimeoutMS=1500, connectTimeoutMS=1500)
    mongo_client.server_info()  # Force connection test
    db = mongo_client["nexa_db"]
    print("Successfully connected to MongoDB server.")
except Exception as e:
    print(f"MongoDB connection failed: {e}. Falling back to local SQLite database.")
    from local_db import LocalDatabase
    db = LocalDatabase()

# Initialize Groq client
groq_api_key = os.environ.get("GROQ_API_KEY", "")
# Allow dummy key for testing without immediate API call failures
groq_client = None
if groq_api_key and groq_api_key != "your_groq_api_key_here":
    try:
        groq_client = groq.Groq(api_key=groq_api_key)
    except Exception as e:
        print(f"Error initializing Groq client: {e}")

# Helper to handle MongoDB ObjectId conversion safely (supporting SQLite UUID string fallback)
def safe_object_id(val):
    try:
        return ObjectId(val)
    except Exception:
        return val

# Decorator to secure routes
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_email" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# LOGIN PAGE & AUTHENTICATION
@app.route("/", methods=["GET"])
def login_redirect():
    session.clear()  # Enforce logging in every time the link is opened
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def login():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "No data provided."}), 400
        
        email = (data.get("email") or "").strip().lower()
        password = (data.get("password") or "").strip()

        if not email or not password:
            return jsonify({"success": False, "message": "Email and password are required."}), 400

        try:
            user = db.users.find_one({"email": email}) if db is not None else None
            if not user:
                # Sign-up by Login: automatically register the user if they don't exist
                password_hash = generate_password_hash(password)
                if db is not None:
                    try:
                        db.users.insert_one({"email": email, "password_hash": password_hash})
                    except Exception as db_err:
                        print(f"Database error during automatic registration: {db_err}")
                session["user_email"] = email
                return jsonify({"success": True, "message": "Welcome! Account created successfully."})
            else:
                # Login check
                if check_password_hash(user["password_hash"], password):
                    session["user_email"] = email
                    return jsonify({"success": True})
                else:
                    return jsonify({"success": False, "message": "Incorrect password."})
        except Exception as db_err:
            print(f"Database error during login, falling back to mock authentication: {db_err}")
            session["user_email"] = email
            return jsonify({"success": True, "message": "Logged in successfully (offline fallback mode)."}), 200
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500

# LOGOUT
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_redirect"))

# MAIN PAGE
@app.route("/main")
@login_required
def main():
    return render_template("main.html")

# CHAT PAGE
@app.route("/chat")
@login_required
def chat():
    return render_template("chat.html")

# RECENT PAGE
@app.route("/recent")
@login_required
def recent():
    return render_template("recent.html")

# API: GET RECENT CHATS FOR SIDEBAR / RECENT LIST
@app.route("/api/recent_chats", methods=["GET"])
@login_required
def api_recent_chats():
    try:
        email = session["user_email"]
        chats = []
        try:
            chats_cursor = db.chats.find({"user_email": email}, {"messages": 0}).sort("created_at", -1)
            for c in chats_cursor:
                chats.append({
                    "id": str(c["_id"]),
                    "title": c.get("title", "Untitled Chat"),
                    "created_at": c["created_at"].strftime("%b %d, %Y %I:%M %p")
                })
        except Exception as db_err:
            print(f"Database error during api_recent_chats: {db_err}")
            chats = [
                {
                    "id": "mock_chat_1",
                    "title": "Welcome to NeXa 🤖",
                    "created_at": datetime.now().strftime("%b %d, %Y %I:%M %p")
                }
            ]
        return jsonify({"success": True, "chats": chats})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# API: GET SINGLE CHAT HISTORY
@app.route("/api/chat/<session_id>", methods=["GET"])
@login_required
def api_chat_detail(session_id):
    try:
        email = session["user_email"]
        messages = []
        title = "Chat"
        try:
            if session_id.startswith("mock_"):
                raise ValueError("Mock session requested")
            chat_doc = db.chats.find_one({"_id": safe_object_id(session_id), "user_email": email})
            if chat_doc:
                title = chat_doc.get("title", "Chat")
                for msg in chat_doc.get("messages", []):
                    # handle both string timestamps and datetime timestamps
                    ts = msg.get("timestamp")
                    if isinstance(ts, datetime):
                        time_str = ts.strftime("%I:%M %p")
                    elif isinstance(ts, str):
                        try:
                            # Try parsing string isoformat if needed, or use as is
                            time_str = datetime.fromisoformat(ts).strftime("%I:%M %p")
                        except Exception:
                            time_str = ts
                    else:
                        time_str = ""
                    messages.append({
                        "role": msg["role"],
                        "content": msg["content"],
                        "timestamp": time_str
                    })
        except Exception as db_err:
            print(f"Database error during api_chat_detail: {db_err}")
            title = "Welcome to NeXa 🤖"
            messages = [
                {
                    "role": "assistant",
                    "content": "Hello! I am Nexa, your responsive study companion. How can I help you today?",
                    "timestamp": datetime.now().strftime("%I:%M %p")
                }
            ]
        return jsonify({
            "success": True, 
            "title": title,
            "messages": messages
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# API: CHAT SEND MESSAGE (GET RESPONSE FROM GROQ)
@app.route("/get", methods=["POST"])
@login_required
def get_bot_response():
    try:
        email = session["user_email"]
        data = request.get_json() or {}
        user_message = (data.get("message") or "").strip()
        session_id = (data.get("session_id") or "").strip()

        if not user_message:
            return jsonify({"success": False, "message": "Empty message."}), 400

        # Retrieve or create chat session
        chat_doc = None
        if session_id and not session_id.startswith("mock_"):
            try:
                chat_doc = db.chats.find_one({"_id": safe_object_id(session_id), "user_email": email})
            except Exception:
                pass

        if not chat_doc:
            # Create new chat session
            title = user_message[:40] + ("..." if len(user_message) > 40 else "")
            chat_doc = {
                "_id": ObjectId(),
                "user_email": email,
                "title": title,
                "created_at": datetime.now(),
                "messages": []
            }
            try:
                db.chats.insert_one(chat_doc)
                session_id = str(chat_doc["_id"])
            except Exception as db_err:
                print(f"Database offline, using local mock session: {db_err}")
                session_id = "mock_" + str(chat_doc["_id"])

        # Check for instant local greetings
        clean_msg = "".join(c for c in user_message.lower() if c.isalnum() or c.isspace()).strip()
        greetings = {
            "hi", "hello", "hey", "hola", "yo", "are you fine", "how are you", 
            "good morning", "good afternoon", "good evening", "good night", "buddy", "hey buddy"
        }
        
        is_greeting = clean_msg in greetings or (len(clean_msg.split()) <= 3 and any(clean_msg.startswith(w) for w in ["hi ", "hello ", "hey ", "yo "]))
        is_image_request = any(kw in clean_msg for kw in ["generate image", "create image", "draw image", "make image", "generate an image", "create an image"])
        
        if is_greeting:
            if "fine" in clean_msg or "how are you" in clean_msg:
                bot_response = "I am doing great, thank you! I'm ready to help you with your studies. What subject are we working on today?"
            elif "morning" in clean_msg:
                bot_response = "Good morning! 🌸 I hope you have a wonderful and productive day ahead. How can I help you with your studies today?"
            elif "afternoon" in clean_msg:
                bot_response = "Good afternoon! ☀️ Hope your day is going well. What are we studying next?"
            elif "evening" in clean_msg:
                bot_response = "Good evening! 🌇 Ready for some end-of-day study review? Ask me anything!"
            elif "night" in clean_msg:
                bot_response = "Good night! 🌙 Make sure to get some rest. But if you have last-minute questions, I'm here to answer!"
            else:
                bot_response = "Hello! I am Nexa, your responsive companion. How can I help you today?"
        elif is_image_request:
            # Generate mock SVG image representation
            subject = user_message.replace("generate image of", "").replace("create image of", "").replace("generate image", "").replace("create image", "").strip()
            if not subject:
                subject = "Abstract Art"
            else:
                subject = subject.title()
                
            subject_lower = subject.lower()
            if any(k in subject_lower for k in ["space", "galaxy", "star", "night", "sky", "moon", "universe"]):
                grad_start = "#0f172a"
                grad_end = "#312e81"
                decorations = """
                <circle cx="70" cy="50" r="2" fill="#fff" opacity="0.8"/>
                <circle cx="220" cy="120" r="1.5" fill="#fff" opacity="0.6"/>
                <circle cx="150" cy="40" r="1" fill="#fff" opacity="0.9"/>
                <circle cx="90" cy="140" r="3" fill="#fff" opacity="0.4"/>
                <circle cx="250" cy="60" r="2" fill="#fff" opacity="0.7"/>
                <circle cx="120" cy="90" r="25" fill="#fef08a" opacity="0.15"/>
                <circle cx="120" cy="90" r="15" fill="#fef08a" opacity="0.8"/>
                """
                desc = "Space Scene Vector Illustration"
            elif any(k in subject_lower for k in ["nature", "forest", "tree", "plant", "green", "flower", "leaf", "garden"]):
                grad_start = "#064e3b"
                grad_end = "#10b981"
                decorations = """
                <path d="M50 150 L100 80 L150 150 Z" fill="#047857" opacity="0.6"/>
                <path d="M120 160 L170 90 L220 160 Z" fill="#047857" opacity="0.8"/>
                <circle cx="230" cy="50" r="12" fill="#fbbf24" opacity="0.9"/>
                """
                desc = "Nature Silhouette Vector Illustration"
            elif any(k in subject_lower for k in ["cat", "dog", "animal", "pet", "cute"]):
                grad_start = "#7c2d12"
                grad_end = "#f97316"
                decorations = """
                <circle cx="150" cy="100" r="22" fill="#fff" opacity="0.2"/>
                <circle cx="150" cy="108" r="10" fill="#fff" opacity="0.7"/>
                <circle cx="138" cy="92" r="4.5" fill="#fff" opacity="0.7"/>
                <circle cx="150" cy="88" r="5" fill="#fff" opacity="0.7"/>
                <circle cx="162" cy="92" r="4.5" fill="#fff" opacity="0.7"/>
                """
                desc = "Cute Pet Paw Silhouette"
            elif any(k in subject_lower for k in ["code", "tech", "computer", "program", "developer", "robot"]):
                grad_start = "#0f172a"
                grad_end = "#0284c7"
                decorations = """
                <text x="30" y="60" fill="#38bdf8" font-family="Courier New" font-size="12" font-weight="bold" opacity="0.6">&lt;div class="nexa"&gt;</text>
                <text x="50" y="85" fill="#a855f7" font-family="Courier New" font-size="12" font-weight="bold" opacity="0.7">const ai = true;</text>
                <text x="50" y="110" fill="#f43f5e" font-family="Courier New" font-size="12" font-weight="bold" opacity="0.7">nexa.render();</text>
                <text x="30" y="135" fill="#38bdf8" font-family="Courier New" font-size="12" font-weight="bold" opacity="0.6">&lt;/div&gt;</text>
                """
                desc = "Tech Code Visual Mockup"
            else:
                grad_start = "#4c1d95"
                grad_end = "#db2777"
                decorations = """
                <circle cx="100" cy="80" r="45" fill="#ffffff" opacity="0.1"/>
                <circle cx="200" cy="120" r="60" fill="#ffffff" opacity="0.08"/>
                <path d="M30 140 Q 150 50, 270 140" stroke="rgba(255,255,255,0.2)" stroke-width="3" fill="none"/>
                """
                desc = "Modern Abstract Vector Art"
                
            svg_html = f'<div style="text-align: center; margin: 1rem 0;"><svg width="300" height="200" viewBox="0 0 300 200" style="border-radius: 20px; box-shadow: 0 12px 36px rgba(168,85,247,0.25); border: 1px solid rgba(255,255,255,0.3);"><defs><linearGradient id="svgGrad" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" style="stop-color:{grad_start};stop-opacity:1" /><stop offset="100%" style="stop-color:{grad_end};stop-opacity:1" /></linearGradient></defs><rect width="300" height="200" fill="url(#svgGrad)"/>{decorations}<rect x="15" y="150" width="270" height="35" rx="8" fill="rgba(255,255,255,0.12)" style="backdrop-filter: blur(5px); border: 1px solid rgba(255,255,255,0.15);"/><text x="30" y="172" fill="#ffffff" font-family="Poppins, sans-serif" font-size="11" font-weight="600" opacity="0.95">✨ Prompt: {subject}</text></svg><div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.5rem; font-style: italic;">{desc}</div></div>'
            bot_response = f"🎨 **Nexa Image Generator (Simulation)**<br><br>Since I am a text-only AI study companion, I cannot generate or display physical high-resolution raster images directly. However, I can design beautiful vector graphics or write stable diffusion prompts!<br><br>Here is a custom simulated vector graphic for your prompt:<br>{svg_html}"
        else:
            # Prepare messages array for Groq API
            groq_messages = [
                {
                    "role": "system",
                    "content": "You are Nexa, a smart, friendly, and highly responsive AI study companion. "
                               "Help users learn, solve academic problems, write code, and answer questions. "
                               "Provide clear, detailed, and well-structured explanations that are easy to understand. "
                               "Use Markdown elements (bullet points, bold text, and code blocks) to organize information so the user can review it briefly and efficiently. "
                               "Be comprehensive but avoid unnecessary fluff to ensure fast response times."
                }
            ]
            
            # Populate context from MongoDB history
            for msg in chat_doc.get("messages", []):
                groq_messages.append({
                    "role": "user" if msg["role"] == "user" else "assistant",
                    "content": msg["content"]
                })

            # Append current user message
            groq_messages.append({
                "role": "user",
                "content": user_message
            })

            # Call Groq API or fallback if key not configured
            if groq_client:
                try:
                    completion = groq_client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=groq_messages,
                        temperature=0.7,
                        max_tokens=1000
                    )
                    bot_response = completion.choices[0].message.content
                except Exception as e:
                    bot_response = f"⚠️ Groq API Error: {str(e)}. Please check your Groq API key configuration in .env."
            else:
                bot_response = f"Hello! I am Nexa, your responsive companion. (Note: GROQ_API_KEY is not configured or invalid in .env, so I am running in local mock mode. You asked: '{user_message}')"

        # Append messages to MongoDB
        timestamp = datetime.now()
        try:
            if not session_id.startswith("mock_"):
                db.chats.update_one(
                    {"_id": chat_doc["_id"]},
                    {
                        "$push": {
                            "messages": {
                                "$each": [
                                    {"role": "user", "content": user_message, "timestamp": timestamp},
                                    {"role": "assistant", "content": bot_response, "timestamp": timestamp}
                                ]
                            }
                        }
                    }
                )
        except Exception as db_err:
            print(f"Failed to save message to database: {db_err}")

        return jsonify({
            "success": True,
            "response": bot_response,
            "session_id": session_id
        })

    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500

# API: UPLOAD FILE IN CHAT
@app.route("/upload", methods=["POST"])
@login_required
def upload_file():
    try:
        email = session["user_email"]
        session_id = (request.form.get("session_id") or "").strip()
        
        if "file" not in request.files:
            return jsonify({"success": False, "message": "No file part in request."}), 400
            
        file = request.files["file"]
        filename = file.filename
        
        if filename == "":
            return jsonify({"success": False, "message": "No selected file."}), 400

        # Read content (try as text, if binary read metadata only)
        file_bytes = file.read()
        is_text = True
        file_content = ""
        try:
            file_content = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            is_text = False
            file_content = "[Binary file, content not text-readable]"

        # Create or find chat session
        chat_doc = None
        if session_id:
            try:
                chat_doc = db.chats.find_one({"_id": safe_object_id(session_id), "user_email": email})
            except Exception:
                pass

        if not chat_doc:
            title = f"File Upload: {filename}"
            new_chat = {
                "user_email": email,
                "title": title,
                "created_at": datetime.now(),
                "messages": []
            }
            res = db.chats.insert_one(new_chat)
            chat_doc = db.chats.find_one({"_id": res.inserted_id})
            session_id = str(chat_doc["_id"])

        # Create user message notifying file attachment
        attachment_msg = f"📎 Uploaded file: **{filename}**\n\n"
        if is_text and len(file_content) > 0:
            # Append snippet or full content depending on size
            snippet = file_content[:2000] + ("..." if len(file_content) > 2000 else "")
            attachment_msg += f"File content preview:\n```\n{snippet}\n```"
        else:
            attachment_msg += f"Size: {len(file_bytes)} bytes. Type: {file.content_type}"

        # Generate bot response confirming upload
        bot_response = f"I've received your file **{filename}**! "
        if is_text:
            bot_response += "I've extracted its text content. You can now ask me to summarize it, search details, or analyze it!"
        else:
            bot_response += "Since it's a binary file, I've noted its metadata. What would you like to discuss about it?"

        # Save to database
        timestamp = datetime.now()
        db.chats.update_one(
            {"_id": chat_doc["_id"]},
            {
                "$push": {
                    "messages": {
                        "$each": [
                            {"role": "user", "content": attachment_msg, "timestamp": timestamp},
                            {"role": "assistant", "content": bot_response, "timestamp": timestamp}
                        ]
                    }
                }
            }
        )

        return jsonify({
            "success": True,
            "filename": filename,
            "session_id": session_id,
            "user_message": attachment_msg,
            "bot_response": bot_response
        })

    except Exception as e:
        return jsonify({"success": False, "message": f"Upload failed: {str(e)}"}), 500

# PROJECT PAGE
@app.route("/project")
@login_required
def project():
    return render_template("project.html")

# API: GET PROJECTS
@app.route("/api/projects", methods=["GET"])
@login_required
def api_get_projects():
    try:
        email = session["user_email"]
        projects = []
        try:
            projects_cursor = db.projects.find({"user_email": email}).sort("created_at", -1)
            for p in projects_cursor:
                projects.append({
                    "id": str(p["_id"]),
                    "name": p["name"],
                    "tasks": p.get("tasks", [])
                })
        except Exception as db_err:
            print(f"Database error during api_get_projects, returning offline mock projects: {db_err}")
            projects = [
                {
                    "id": "mock_project_1",
                    "name": "Academic Study Plan 📚",
                    "tasks": [
                        {"id": "t1", "text": "Setup local development environment", "completed": True},
                        {"id": "t2", "text": "Resolve SSL handshake error", "completed": True},
                        {"id": "t3", "text": "Review Python and Flask documentation", "completed": False}
                    ]
                }
            ]
        return jsonify({"success": True, "projects": projects})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# API: ADD PROJECT
@app.route("/api/projects", methods=["POST"])
@login_required
def api_add_project():
    try:
        email = session["user_email"]
        data = request.get_json() or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"success": False, "message": "Project name cannot be empty."}), 400
        
        new_project = {
            "user_email": email,
            "name": name,
            "tasks": [],
            "created_at": datetime.now()
        }
        res = db.projects.insert_one(new_project)
        return jsonify({
            "success": True,
            "project": {
                "id": str(res.inserted_id),
                "name": name,
                "tasks": []
            }
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# API: ADD TASK TO PROJECT
@app.route("/api/projects/task", methods=["POST"])
@login_required
def api_add_task():
    try:
        email = session["user_email"]
        data = request.get_json() or {}
        project_id = (data.get("project_id") or "").strip()
        task_text = (data.get("text") or "").strip()
        
        if not project_id or not task_text:
            return jsonify({"success": False, "message": "Invalid project ID or task text."}), 400
            
        task_id = str(ObjectId())
        new_task = {
            "id": task_id,
            "text": task_text,
            "completed": False
        }
        
        res = db.projects.update_one(
            {"_id": safe_object_id(project_id), "user_email": email},
            {"$push": {"tasks": new_task}}
        )
        
        if res.modified_count == 0:
            return jsonify({"success": False, "message": "Project not found."}), 404
            
        return jsonify({"success": True, "task": new_task})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# API: TOGGLE TASK STATUS
@app.route("/api/projects/toggle", methods=["POST"])
@login_required
def api_toggle_task():
    try:
        email = session["user_email"]
        data = request.get_json() or {}
        project_id = (data.get("project_id") or "").strip()
        task_id = (data.get("task_id") or "").strip()
        completed = data.get("completed", False)
        
        if not project_id or not task_id:
            return jsonify({"success": False, "message": "Invalid project ID or task ID."}), 400
            
        res = db.projects.update_one(
            {"_id": safe_object_id(project_id), "user_email": email, "tasks.id": task_id},
            {"$set": {"tasks.$.completed": completed}}
        )
        
        if res.modified_count == 0:
            return jsonify({"success": False, "message": "Failed to toggle task status."}), 404
            
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# API: DELETE PROJECT
@app.route("/api/projects/delete", methods=["POST"])
@login_required
def api_delete_project():
    try:
        email = session["user_email"]
        data = request.get_json() or {}
        project_id = (data.get("project_id") or "").strip()
        
        if not project_id:
            return jsonify({"success": False, "message": "Invalid project ID."}), 400
            
        res = db.projects.delete_one({"_id": safe_object_id(project_id), "user_email": email})
        
        if res.deleted_count == 0:
            return jsonify({"success": False, "message": "Project not found."}), 404
            
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)