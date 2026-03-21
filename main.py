from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, String, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import urllib.request
import urllib.parse
import urllib.error
import urllib.parse
import json
import os
from datetime import datetime, timezone, timedelta

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

GUPSHUP_API_KEY = os.getenv("GUPSHUP_API_KEY")
GUPSHUP_NUMBER  = os.getenv("GUPSHUP_NUMBER")
DATABASE_URL    = os.getenv("DATABASE_URL", "sqlite:///leads.db")
IST = timezone(timedelta(hours=5, minutes=30))  # Indian Standard Time

# ================================================================
# 1. KNOWLEDGE BASE (Config-driven — change without touching code)
# ================================================================
COURSES = {
    "python": {"name": "Python Basics",     "duration": "4 weeks",  "price": "₹1999", "batch": "April 1",  "emoji": "🐍"},
    "ai":     {"name": "AI for Beginners",  "duration": "6 weeks",  "price": "₹2999", "batch": "April 5",  "emoji": "🤖"},
    "web":    {"name": "Web Development",   "duration": "8 weeks",  "price": "₹3999", "batch": "April 10", "emoji": "🌐"},
    "data":   {"name": "Data Science",      "duration": "10 weeks", "price": "₹4999", "batch": "April 15", "emoji": "📊"},
}

BOT_CONFIG = {
    "name":     "9faqs",
    "welcome":  "👋 *Welcome to 9faqs!*\n\nWe offer industry-ready tech courses.\n\nPlease choose:\n1️⃣ View Courses\n2️⃣ Enroll Now\n3️⃣ Talk to Counselor",
    "fallback": "Sorry, I didn't understand 🤔\n\nPlease choose:\n1️⃣ View Courses\n2️⃣ Enroll Now\n3️⃣ Talk to Counselor\n\nOr type *Hi* to restart.",
}

# ================================================================
# 2. STATE MACHINE ENGINE
# ================================================================
# Each state has:
#   - message  : what bot asks
#   - validate : optional validation function
#   - next     : next state after valid input
#   - save_as  : key to save user's answer in session data

ENROLLMENT_FLOW = {
    "ask_name": {
        "message":  "Please share your *full name*:",
        "save_as":  "name",
        "next":     "ask_email",
        "validate": None,
    },
    "ask_email": {
        "message":  "Please share your *email address*:",
        "save_as":  "email",
        "next":     "ask_phone",
        "validate": lambda v: "@" in v and "." in v,
        "error":    "Please enter a valid email 📧 (e.g. name@gmail.com)",
    },
    "ask_phone": {
        "message":  "Please share your *contact number*:",
        "save_as":  "contact",
        "next":     "done",
        "validate": lambda v: v.replace(" ","").replace("+","").isdigit() and len(v) >= 8,
        "error":    "Please enter a valid phone number 📱",
    },
}

# Session store: { phone: { "step": "ask_name", "data": { "name": ..., "course": ... } } }
sessions = {}

def get_session(phone):
    if phone not in sessions:
        sessions[phone] = {"step": None, "data": {}, "fallback_count": 0}
    return sessions[phone]

def reset_session(phone):
    sessions[phone] = {"step": None, "data": {}, "fallback_count": 0}

def set_step(phone, step):
    sessions[phone]["step"] = step

def save_to_session(phone, key, value):
    sessions[phone]["data"][key] = value

def get_from_session(phone, key, default=None):
    return sessions[phone]["data"].get(key, default)

# ================================================================
# 3. DATABASE
# ================================================================
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
Base   = declarative_base()

class Lead(Base):
    __tablename__ = "leads"
    phone     = Column(String, primary_key=True)
    name      = Column(String)
    email     = Column(String)
    course    = Column(String)
    status    = Column(String, default="new")
    label     = Column(String, default="NEW")
    timestamp = Column(DateTime, default=lambda: (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).replace(tzinfo=None))

class Message(Base):
    __tablename__ = "messages"
    id        = Column(String, primary_key=True)
    phone     = Column(String)
    name      = Column(String)
    text      = Column(Text)
    direction = Column(String)
    timestamp = Column(DateTime, default=lambda: (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).replace(tzinfo=None))

class UserControl(Base):
    __tablename__ = "user_control"
    phone    = Column(String, primary_key=True)
    is_human = Column(Boolean, default=False)
    tag      = Column(String, default="")

Base.metadata.create_all(engine)

# ── DB MIGRATION: Add missing columns safely ──
from sqlalchemy import text
with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE user_control ADD COLUMN tag VARCHAR DEFAULT ''"))
        conn.commit()
        print("✅ Migration: added tag column")
    except Exception:
        pass  # Column already exists
    try:
        conn.execute(text("ALTER TABLE leads ADD COLUMN email VARCHAR DEFAULT ''"))
        conn.commit()
        print("✅ Migration: added email column")
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE leads ADD COLUMN status VARCHAR DEFAULT 'new'"))
        conn.commit()
        print("✅ Migration: added status column")
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE leads ADD COLUMN label VARCHAR DEFAULT 'NEW'"))
        conn.commit()
        print("✅ Migration: added label column")
    except Exception:
        pass
Session = sessionmaker(bind=engine)

def save_lead(phone, name, email, course):
    db = Session()
    lead = Lead(phone=phone, name=name, email=email, course=course,
                status="enrolled", label="ENROLLED", timestamp=(datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).replace(tzinfo=None))
    db.merge(lead)
    db.commit()
    db.close()
    print(f"💾 LEAD: {name} | {email} | {course}")

def save_message(phone, name, text, direction):
    db = Session()
    now = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).replace(tzinfo=None)  # IST
    msg_id = f"{phone}_{now.timestamp()}"
    db.add(Message(id=msg_id, phone=phone, name=name,
                   text=text, direction=direction, timestamp=now))
    db.commit()
    db.close()

def is_human_mode(phone):
    db = Session()
    ctrl = db.query(UserControl).filter_by(phone=phone).first()
    db.close()
    return ctrl.is_human if ctrl else False

def set_human_mode(phone, value: bool):
    db = Session()
    ctrl = db.query(UserControl).filter_by(phone=phone).first()
    if not ctrl:
        ctrl = UserControl(phone=phone, is_human=value)
        db.add(ctrl)
    else:
        ctrl.is_human = value
    db.commit()
    db.close()

def update_label(phone, label):
    db = Session()
    lead = db.query(Lead).filter_by(phone=phone).first()
    if lead:
        lead.label = label
    ctrl = db.query(UserControl).filter_by(phone=phone).first()
    if not ctrl:
        ctrl = UserControl(phone=phone, tag=label)
        db.add(ctrl)
    else:
        ctrl.tag = label
    db.commit()
    db.close()

# ================================================================
# 4. WEBSOCKET
# ================================================================
class ConnectionManager:
    def __init__(self):
        self.connections = []
    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)
    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)
    async def broadcast(self, data: dict):
        for conn in self.connections:
            try: await conn.send_json(data)
            except: pass

manager = ConnectionManager()

# ================================================================
# 5. BOT RESPONSE BUILDER
# ================================================================
def course_list_msg():
    lines = ["📚 *Available Courses:*\n"]
    for i, (_, c) in enumerate(COURSES.items(), 1):
        lines.append(f"{i}. {c['emoji']} {c['name']} — {c['price']}")
    lines.append("\nReply with *number* to know more! (e.g. 1, 2, 3, 4)")
    return "\n".join(lines)

def course_detail_msg(key):
    c = COURSES[key]
    return (f"{c['emoji']} *{c['name']}*\n\n"
            f"📅 Duration: {c['duration']}\n"
            f"💰 Price: {c['price']}\n"
            f"🗓 Next batch: {c['batch']}\n\n"
            f"Reply *Enroll* to join!")

def enrollment_done_msg(session):
    d = session["data"]
    return (f"✅ *Enrollment Confirmed!*\n\n"
            f"👤 Name: {d.get('name','—')}\n"
            f"📧 Email: {d.get('email','—')}\n"
            f"📱 Phone: {d.get('contact','—')}\n"
            f"📚 Course: {d.get('course','—')}\n\n"
            f"Our team will contact you within 24 hours! 🎉\n\n"
            f"Type *Hi* to explore more courses.")

# ================================================================
# 6. AI LAYER (Mock now → Real AI next)
# ================================================================
def call_ai(message: str) -> str:
    """
    AI response function.
    Currently: Smart keyword-based mock
    Next step: Replace with OpenAI / Pinecone RAG
    """
    msg = message.lower().strip()

    # Course queries
    if any(x in msg for x in ["what course", "which course", "courses available",
                                "what do you offer", "what can i learn"]):
        return course_list_msg()

    if "best course" in msg or "recommend" in msg or "suggest" in msg:
        return "Great question! 🤔\n\nFor beginners → 🐍 Python Basics\nFor future jobs → 🤖 AI for Beginners\nFor websites → 🌐 Web Development\nFor data jobs → 📊 Data Science\n\nType the course name to know more!"

    if any(x in msg for x in ["learn coding", "learn programming", "start coding", "become developer"]):
        return "🐍 *Python Basics* is the perfect start!\n\n✅ No prior experience needed\n✅ 4 weeks, ₹1999 only\n✅ Next batch: April 1\n\nReply *Enroll* to join!"

    if any(x in msg for x in ["price", "cost", "fee", "how much", "fees"]):
        return "💰 *Course Fees:*\n\n🐍 Python Basics — ₹1999\n🤖 AI for Beginners — ₹2999\n🌐 Web Development — ₹3999\n📊 Data Science — ₹4999\n\nAll include certificate + placement support!"

    if any(x in msg for x in ["duration", "how long", "weeks", "months"]):
        return "📅 *Course Durations:*\n\n🐍 Python Basics — 4 weeks\n🤖 AI for Beginners — 6 weeks\n🌐 Web Development — 8 weeks\n📊 Data Science — 10 weeks\n\nWeekend batches available!"

    if any(x in msg for x in ["certificate", "placement", "job", "career"]):
        return "🎓 Yes! All courses include:\n\n✅ Industry certificate\n✅ Placement assistance\n✅ Live projects\n✅ Mentor support\n\nType course name to know more!"

    if any(x in msg for x in ["batch", "when", "start", "next batch"]):
        return "🗓 *Upcoming Batches:*\n\n🐍 Python — April 1\n🤖 AI — April 5\n🌐 Web Dev — April 10\n📊 Data Science — April 15\n\nLimited seats! Reply *Enroll* to reserve."

    if any(x in msg for x in ["contact", "call", "phone", "reach", "support"]):
        return "📞 You can reach us at:\n\n📧 info@9faqs.com\n🌐 www.9faqs.com\n\nOr type *3* to talk to a counselor right now!"

    if any(x in msg for x in ["thank", "thanks", "ok", "okay", "great", "good"]):
        return "You're welcome! 😊\n\nType *Hi* anytime to explore courses or enroll!"

    # No match → return None so fallback handles it
    return None

# 7. MAIN MESSAGE HANDLER (State Machine)
# ================================================================
def handle_message(text, phone):
    msg          = text.lower().strip()
    text_original = text.strip()  # Keep original for Zeneral AI
    session = get_session(phone)
    step    = session["step"]
    data    = session["data"]

    # ── ACTIVE ENROLLMENT FLOW ──
    if step in ENROLLMENT_FLOW:
        flow = ENROLLMENT_FLOW[step]

        # Validate input
        validator = flow.get("validate")
        if validator and not validator(text):
            return flow.get("error", "Invalid input. Please try again.")

        # Save answer
        save_to_session(phone, flow["save_as"], text.strip())

        # Move to next step
        next_step = flow["next"]
        set_step(phone, next_step)

        # If flow complete
        if next_step == "done":
            name   = get_from_session(phone, "name", "Friend")
            email  = get_from_session(phone, "email", "")
            course = get_from_session(phone, "course", "General")
            save_lead(phone, name, email, course)
            reply  = enrollment_done_msg(session)
            reset_session(phone)
            return reply

        # Ask next question
        return ENROLLMENT_FLOW[next_step]["message"]

    # ── MENU FLOW ──
    # Reset / Welcome
    if any(x in msg for x in ["hi", "hello", "hey", "start", "menu"]):
        reset_session(phone)
        return BOT_CONFIG["welcome"]

    # View courses
    if msg in ["1", "courses", "course", "view courses", "view"]:
        session["fallback_count"] = 0
        set_step(phone, "pick_course")
        return course_list_msg()

    # Pick course by number (1-4) after seeing list
    if step == "pick_course" or msg in ["1","2","3","4"]:
        course_keys = list(COURSES.keys())
        course_map  = {str(i+1): key for i, key in enumerate(course_keys)}
        if msg in course_map:
            key = course_map[msg]
            save_to_session(phone, "course", COURSES[key]["name"])
            set_step(phone, None)
            session["fallback_count"] = 0
            return course_detail_msg(key)

    # Course details by name
    for key in COURSES:
        if key in msg:
            save_to_session(phone, "course", COURSES[key]["name"])
            set_step(phone, None)
            session["fallback_count"] = 0
            return course_detail_msg(key)

    # Start enrollment
    if msg in ["2", "enroll", "enroll now", "join", "register"] and step != "pick_course":
        set_step(phone, "ask_name")
        session["fallback_count"] = 0
        return f"Great choice! 🎉\n\n{ENROLLMENT_FLOW['ask_name']['message']}"

    # Talk to counselor — always available regardless of step
    if msg in ["3", "counselor", "human", "agent", "help", "talk to counselor", "talk"]:
        set_human_mode(phone, True)
        reset_session(phone)
        session["fallback_count"] = 0
        return "📞 Connecting you to a counselor...\nA human agent will reply shortly! ⏳"

    # ── AI LAYER ──
    # If no menu option matched → try AI
    ai_answer = call_ai(text_original)
    if ai_answer:
        session["fallback_count"] = 0
        return ai_answer

    # If Zeneral also fails → smart escalation
    session["fallback_count"] = session.get("fallback_count", 0) + 1
    if session["fallback_count"] >= 2:
        session["fallback_count"] = 0
        set_human_mode(phone, True)
        return "🙏 Let me connect you to a human agent who can help better!\n\nPlease wait..."

    return BOT_CONFIG["fallback"]

# ================================================================
# 7. SEND WHATSAPP
# ================================================================
def send_whatsapp(phone, message):
    url    = "https://api.gupshup.io/sm/api/v1/msg"
    params = urllib.parse.urlencode({
        "channel":   "whatsapp",
        "source":    GUPSHUP_NUMBER,
        "destination": phone,
        "src.name":  "9faqsbot",
        "message":   json.dumps({"type": "text", "text": message})
    }).encode()
    req = urllib.request.Request(url, data=params)
    req.add_header("apikey", GUPSHUP_API_KEY)
    urllib.request.urlopen(req)
    print(f"✅ Sent → {phone}: {message[:60]}...")

# ================================================================
# 8. API ROUTES
# ================================================================
@app.get("/")
def home():
    return {"status": "9faqs Bot v3.0 ✅", "flows": list(ENROLLMENT_FLOW.keys())}

@app.get("/dashboard")
def dashboard():
    return FileResponse("dashboard.html")

@app.get("/leads")
def get_leads():
    db    = Session()
    leads = db.query(Lead).order_by(Lead.timestamp.desc()).all()
    db.close()
    return [{"phone": l.phone, "name": l.name, "email": l.email,
             "course": l.course, "status": l.status, "label": l.label,
             "timestamp": str(l.timestamp)} for l in leads]

@app.get("/conversations")
def get_conversations():
    db   = Session()
    msgs = db.query(Message).order_by(Message.timestamp.desc()).all()
    db.close()
    seen = {}
    for m in msgs:
        if m.phone not in seen:
            seen[m.phone] = {"phone": m.phone, "name": m.name,
                             "last_message": m.text, "timestamp": str(m.timestamp),
                             "is_human": is_human_mode(m.phone)}
    return list(seen.values())

@app.get("/messages/{phone}")
def get_messages(phone: str):
    db   = Session()
    msgs = db.query(Message).filter_by(phone=phone).order_by(Message.timestamp.asc()).all()
    db.close()
    return [{"text": m.text, "direction": m.direction,
             "timestamp": str(m.timestamp), "name": m.name} for m in msgs]

@app.post("/takeover/{phone}")
async def takeover(phone: str):
    set_human_mode(phone, True)
    update_label(phone, "HOT LEAD")
    await manager.broadcast({"type": "takeover", "phone": phone})
    return {"status": "human mode on"}

@app.post("/handback/{phone}")
async def handback(phone: str):
    set_human_mode(phone, False)
    await manager.broadcast({"type": "handback", "phone": phone})
    return {"status": "bot mode on"}

@app.post("/reply/{phone}")
async def agent_reply(phone: str, req: Request):
    body    = await req.json()
    message = body.get("message", "")
    if message:
        send_whatsapp(phone, message)
        save_message(phone, "Agent", message, "out")
        await manager.broadcast({"type": "new_message", "phone": phone,
                                  "text": message, "direction": "out", "name": "Agent"})
    return {"status": "sent"}

@app.post("/tag/{phone}")
async def tag_lead(phone: str, req: Request):
    body = await req.json()
    tag  = body.get("tag", "")
    update_label(phone, tag)
    await manager.broadcast({"type": "tag_update", "phone": phone, "tag": tag})
    return {"status": "tagged"}

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/webhook")
async def webhook(req: Request):
    data = await req.json()
    print("INCOMING:", data)
    try:
        messages = data["entry"][0]["changes"][0]["value"].get("messages", [])
        contacts = data["entry"][0]["changes"][0]["value"].get("contacts", [])
        if not messages:
            return {"status": "ok"}

        msg   = messages[0]
        phone = msg["from"]
        name  = contacts[0]["profile"]["name"] if contacts else phone

        if msg.get("type") == "text":
            text = msg["text"]["body"]
            print(f"📩 {name} ({phone}): {text}")
            save_message(phone, name, text, "in")
            await manager.broadcast({"type": "new_message", "phone": phone,
                                     "name": name, "text": text, "direction": "in"})

            if is_human_mode(phone):
                print(f"👤 Human mode active — skipping bot for {phone}")
                return {"status": "ok"}

            reply = handle_message(text, phone)
            send_whatsapp(phone, reply)
            save_message(phone, "Bot", reply, "out")
            await manager.broadcast({"type": "new_message", "phone": phone,
                                     "name": "Bot", "text": reply, "direction": "out"})
        else:
            if not is_human_mode(phone):
                send_whatsapp(phone, "Sorry, I only understand text. Type *Hi* to start 👋")

    except Exception as e:
        print(f"❌ Error: {e}")

    return {"status": "ok"}