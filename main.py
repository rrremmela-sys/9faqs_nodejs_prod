from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, String, DateTime, Boolean, Text, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from openai import OpenAI
import urllib.request
import urllib.parse
import urllib.error
import json
import os
from datetime import datetime, timezone, timedelta

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ================================================================
# CONFIG
# ================================================================
GUPSHUP_API_KEY = os.getenv("GUPSHUP_API_KEY")
GUPSHUP_NUMBER  = os.getenv("GUPSHUP_NUMBER")
DATABASE_URL    = os.getenv("DATABASE_URL", "sqlite:///leads.db")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY")

openai_client   = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

def now_ist():
    return (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).replace(tzinfo=None)

# ================================================================
# KNOWLEDGE BASE (from 9faqs.com)
# ================================================================
COURSES = {
    "crash_course": {
        "name": "Python Crash Course", "price": "₹1999",
        "duration": "Weekend (Sat & Sun, 10AM–4PM)", "emoji": "🐍",
        "level": "Beginner–Intermediate", "certificate": True,
        "highlights": ["Live instructor-led", "AI tools intro", "Git & Jira", "Interview prep"],
        "url": "https://9faqs.com/training/python_crash_course"
    },
    "bootcamp": {
        "name": "Python Bootcamp", "price": "Contact for pricing",
        "duration": "90 days (Mon–Fri, 12PM–6PM) + 3mo internship", "emoji": "🚀",
        "level": "Beginner–Advanced", "certificate": True, "internship": True,
        "highlights": ["Cloud lab support", "Hands-on projects", "Career prep", "Mock interviews"],
        "url": "https://9faqs.com/training/python_bootcamp"
    },
    "ai_workshop": {
        "name": "AI Workshop", "price": "₹1999",
        "duration": "4-hour live workshop", "emoji": "🤖",
        "level": "No coding required", "certificate": False,
        "highlights": ["Build website with AI", "ChatGPT + Cursor IDE", "Domain & hosting setup", "1-1 post support"],
        "url": "https://9faqs.com/training/ai_workshops"
    },
    "python_faqs": {
        "name": "Python FAQs (Self-Learn)", "price": "Free",
        "duration": "Self-paced", "emoji": "📚",
        "level": "All levels", "certificate": False,
        "highlights": ["1736+ Python questions", "Adaptive learning", "Interview prep"],
        "url": "https://9faqs.com/python"
    },
}

GENERAL_FAQS = [
    {"q": "best for beginners",     "a": "🚀 Python Bootcamp is best for complete beginners — 90 days with cloud lab + internship. For a quick start, try the weekend Crash Course (₹1999)."},
    {"q": "working professionals",  "a": "🐍 Python Crash Course is perfect for working professionals — weekend batches, intensive, only ₹1999."},
    {"q": "cheapest course",        "a": "💰 Python Crash Course & AI Workshop are both ₹1999. Python FAQs self-learning is completely free!"},
    {"q": "certificate",            "a": "🎓 Yes! Python Crash Course and Bootcamp both give a Certificate of Completion."},
    {"q": "job guarantee",          "a": "We don't offer job guarantee, but we provide profile building, LinkedIn guidance & mock interviews."},
    {"q": "telugu",                 "a": "Yes! 9faqs offers Python sessions in Telugu 🇮🇳. Enroll at https://9faqs.com/enroll"},
    {"q": "alumni",                 "a": "9FAQs Alumni get 10% discount on future courses and join our growing tech community!"},
    {"q": "internship",             "a": "Yes! Python Bootcamp includes an optional 3-month internship after the 90-day program."},
]

SYSTEM_PROMPT = """You are a helpful WhatsApp assistant for 9faqs (https://9faqs.com), an online tech learning platform in India.

COURSES AVAILABLE:
1. Python Crash Course — ₹1999, weekend batches (Sat & Sun), live instructor-led, certificate included
2. Python Bootcamp — 90 days Mon-Fri, internship option, cloud lab, career prep
3. AI Workshop — ₹1999, 4-hour live session, build website using AI tools, no coding needed
4. Python FAQs — Free self-learning, 1736+ interview questions

KEY FACTS:
- All sessions are LIVE (not recorded)
- Sessions available in Telugu language
- Alumni get 10% discount on future courses
- Enroll at: https://9faqs.com/enroll
- No job guarantee but career guidance & mock interviews provided

RULES:
- Keep answers SHORT (2-4 lines max) — this is WhatsApp
- Be warm, friendly and encouraging
- Always end with a call to action (enroll or type Hi)
- Never make up info not listed above
- If unsure → "Visit 9faqs.com or type Hi to talk to our team"
- Reply in same language as the user
"""

BOT_CONFIG = {
    "welcome": "👋 *Welcome to 9faqs!*\n\nYour gateway to tech careers 🚀\n\nPlease choose:\n1️⃣ View Courses\n2️⃣ Enroll Now\n3️⃣ Talk to Counselor\n\nOr just ask me anything!",
    "fallback": "I'm not sure about that 🤔\n\nType *Hi* to see our courses or *3* to talk to a counselor.",
}

# ================================================================
# DATABASE
# ================================================================
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
Base   = declarative_base()

class Lead(Base):
    __tablename__ = "leads"
    phone      = Column(String, primary_key=True)
    name       = Column(String)
    email      = Column(String, default="")
    course     = Column(String, default="")
    status     = Column(String, default="NEW")       # NEW / INTERESTED / ENROLLED / CLOSED
    label      = Column(String, default="NEW")
    timestamp  = Column(DateTime, default=now_ist)

class Message(Base):
    __tablename__ = "messages"
    id         = Column(String, primary_key=True)
    phone      = Column(String)
    name       = Column(String)
    text       = Column(Text)
    direction  = Column(String)
    timestamp  = Column(DateTime, default=now_ist)

class UserControl(Base):
    __tablename__ = "user_control"
    phone      = Column(String, primary_key=True)
    is_human   = Column(Boolean, default=False)
    tag        = Column(String, default="")
    is_new     = Column(Boolean, default=True)   # First time visitor

Base.metadata.create_all(engine)

# DB Migration
from sqlalchemy import text
with engine.connect() as conn:
    for col_sql in [
        "ALTER TABLE user_control ADD COLUMN tag VARCHAR DEFAULT ''",
        "ALTER TABLE user_control ADD COLUMN is_new BOOLEAN DEFAULT TRUE",
        "ALTER TABLE leads ADD COLUMN email VARCHAR DEFAULT ''",
        "ALTER TABLE leads ADD COLUMN status VARCHAR DEFAULT 'NEW'",
        "ALTER TABLE leads ADD COLUMN label VARCHAR DEFAULT 'NEW'",
    ]:
        try:
            conn.execute(text(col_sql))
            conn.commit()
        except Exception:
            pass

Session = sessionmaker(bind=engine)

# ================================================================
# DB HELPERS
# ================================================================
def now_ist():
    return (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).replace(tzinfo=None)

def save_lead(phone, name, email, course):
    db = Session()
    lead = Lead(phone=phone, name=name, email=email, course=course,
                status="ENROLLED", label="ENROLLED", timestamp=now_ist())
    db.merge(lead)
    db.commit()
    db.close()
    print(f"💾 LEAD: {name} | {email} | {course}")

def upsert_lead_interest(phone, course):
    """Create/update lead when user shows interest in a course"""
    db = Session()
    lead = db.query(Lead).filter_by(phone=phone).first()
    if not lead:
        lead = Lead(phone=phone, name=phone, course=course,
                    status="INTERESTED", label="INTERESTED", timestamp=now_ist())
        db.add(lead)
    elif lead.status == "NEW":
        lead.status = "INTERESTED"
        lead.label  = "INTERESTED"
        lead.course = course
    db.commit()
    db.close()

def save_message(phone, name, text_content, direction):
    db = Session()
    msg_id = f"{phone}_{now_ist().timestamp()}"
    db.add(Message(id=msg_id, phone=phone, name=name,
                   text=text_content, direction=direction, timestamp=now_ist()))
    db.commit()
    db.close()

def is_human_mode(phone):
    db = Session()
    ctrl = db.query(UserControl).filter_by(phone=phone).first()
    db.close()
    return ctrl.is_human if ctrl else False

def is_new_user(phone):
    db = Session()
    ctrl = db.query(UserControl).filter_by(phone=phone).first()
    db.close()
    return ctrl.is_new if ctrl else True

def mark_user_seen(phone):
    db = Session()
    ctrl = db.query(UserControl).filter_by(phone=phone).first()
    if not ctrl:
        ctrl = UserControl(phone=phone, is_new=False)
        db.add(ctrl)
    else:
        ctrl.is_new = False
    db.commit()
    db.close()

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

def update_lead_status(phone, status):
    db = Session()
    lead = db.query(Lead).filter_by(phone=phone).first()
    if not lead:
        lead = Lead(phone=phone, name=phone, status=status,
                    label=status, timestamp=now_ist())
        db.add(lead)
    else:
        lead.status = status
        lead.label  = status
    ctrl = db.query(UserControl).filter_by(phone=phone).first()
    if not ctrl:
        ctrl = UserControl(phone=phone, tag=status)
        db.add(ctrl)
    else:
        ctrl.tag = status
    db.commit()
    db.close()

# ================================================================
# WEBSOCKET
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
# STATE MACHINE
# ================================================================
ENROLLMENT_FLOW = {
    "ask_name": {
        "message": "Please share your *full name*:",
        "save_as": "name", "next": "ask_email", "validate": None,
    },
    "ask_email": {
        "message": "Please share your *email address*:",
        "save_as": "email", "next": "ask_phone",
        "validate": lambda v: "@" in v and "." in v,
        "error": "Please enter a valid email 📧 (e.g. name@gmail.com)",
    },
    "ask_phone": {
        "message": "Please share your *contact number*:",
        "save_as": "contact", "next": "done",
        "validate": lambda v: v.replace(" ","").replace("+","").isdigit() and len(v) >= 8,
        "error": "Please enter a valid phone number 📱",
    },
}

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
# BOT HELPERS
# ================================================================
def course_list_msg():
    lines = ["📚 *Our Courses:*\n"]
    for i, (_, c) in enumerate(COURSES.items(), 1):
        lines.append(f"{i}. {c['emoji']} {c['name']} — {c['price']}")
    lines.append("\nReply with *number* (1-4) to know more!")
    return "\n".join(lines)

def course_detail_msg(key):
    c = COURSES[key]
    h = "\n".join([f"✅ {x}" for x in c['highlights'][:3]])
    return (f"{c['emoji']} *{c['name']}*\n\n"
            f"💰 {c['price']}\n"
            f"📅 {c['duration']}\n\n"
            f"{h}\n\n"
            f"Reply *Enroll* to join or visit:\n{c['url']}")

def enrollment_done_msg(session):
    d = session["data"]
    return (f"✅ *Enrollment Confirmed!*\n\n"
            f"👤 Name: {d.get('name','—')}\n"
            f"📧 Email: {d.get('email','—')}\n"
            f"📱 Phone: {d.get('contact','—')}\n"
            f"📚 Course: {d.get('course','General')}\n\n"
            f"Our team will contact you within 24 hours! 🎉\n\n"
            f"Type *Hi* to explore more courses.")

# ================================================================
# AI LAYER
# ================================================================
def call_ai(message: str) -> str:
    if not openai_client:
        return None
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": message}
            ],
            max_tokens=150,
            temperature=0.7
        )
        answer = response.choices[0].message.content.strip()
        # Phase 1: Fallback if AI answer is too long or empty
        if not answer or len(answer) > 400:
            return None
        print(f"🤖 AI: {answer[:80]}...")
        return answer
    except Exception as e:
        print(f"⚠️ AI error: {e}")
        return None

# ================================================================
# MAIN MESSAGE HANDLER
# ================================================================
def handle_message(text, phone):
    msg           = text.lower().strip()
    msg_words     = msg.split()
    text_original = text.strip()
    session       = get_session(phone)
    step          = session["step"]

    # ── Enrollment Flow ──
    if step in ENROLLMENT_FLOW:
        flow      = ENROLLMENT_FLOW[step]
        validator = flow.get("validate")
        if validator and not validator(text):
            return flow.get("error", "Invalid input. Please try again.")
        save_to_session(phone, flow["save_as"], text.strip())
        next_step = flow["next"]
        set_step(phone, next_step)
        if next_step == "done":
            name   = get_from_session(phone, "name", "Friend")
            email  = get_from_session(phone, "email", "")
            course = get_from_session(phone, "course", "General")
            save_lead(phone, name, email, course)
            reply  = enrollment_done_msg(session)
            reset_session(phone)
            return reply
        return ENROLLMENT_FLOW[next_step]["message"]

    # ── Phase 1: Restart command ──
    if any(x in msg_words for x in ["hi", "hello", "hey", "start", "menu", "restart"]):
        reset_session(phone)
        return BOT_CONFIG["welcome"]

    # ── View courses ──
    if msg in ["1", "courses", "course", "view courses", "view"]:
        session["fallback_count"] = 0
        set_step(phone, "pick_course")
        return course_list_msg()

    # ── Pick course by number ──
    if step == "pick_course":
        course_keys = list(COURSES.keys())
        course_map  = {str(i+1): key for i, key in enumerate(course_keys)}
        if msg in course_map:
            key = course_map[msg]
            save_to_session(phone, "course", COURSES[key]["name"])
            set_step(phone, None)
            upsert_lead_interest(phone, COURSES[key]["name"])
            session["fallback_count"] = 0
            return course_detail_msg(key)
        return "Please reply with a number 1-4 to select a course 👆"

    # ── Course by name ──
    for key in COURSES:
        if key.replace("_", " ") in msg or key.split("_")[0] in msg:
            save_to_session(phone, "course", COURSES[key]["name"])
            upsert_lead_interest(phone, COURSES[key]["name"])
            set_step(phone, None)
            session["fallback_count"] = 0
            return course_detail_msg(key)

    # ── Enroll ──
    if msg in ["2", "enroll", "enroll now", "join", "register"] and step != "pick_course":
        set_step(phone, "ask_name")
        session["fallback_count"] = 0
        return f"Great choice! 🎉\n\n{ENROLLMENT_FLOW['ask_name']['message']}"

    # ── Counselor ──
    if msg in ["3", "counselor", "human", "agent", "help", "talk to counselor", "talk"]:
        set_human_mode(phone, True)
        reset_session(phone)
        update_lead_status(phone, "HOT LEAD")
        session["fallback_count"] = 0
        return "📞 Connecting you to a counselor...\nA human agent will reply shortly! ⏳"

    # ── AI Layer ──
    ai_answer = call_ai(text_original)
    if ai_answer:
        session["fallback_count"] = 0
        return ai_answer

    # ── Smart escalation ──
    session["fallback_count"] = session.get("fallback_count", 0) + 1
    if session["fallback_count"] >= 2:
        session["fallback_count"] = 0
        set_human_mode(phone, True)
        return "🙏 Let me connect you to a human agent!\n\nPlease wait..."

    return BOT_CONFIG["fallback"]

# ================================================================
# SEND WHATSAPP
# ================================================================
def send_whatsapp(phone, message):
    try:
        url    = "https://api.gupshup.io/wa/api/v1/msg"
        params = urllib.parse.urlencode({
            "channel":     "whatsapp",
            "source":      GUPSHUP_NUMBER,
            "destination": phone,
            "src.name":    "9faqsbot",
            "message":     json.dumps({"type": "text", "text": message})
        }).encode()
        req = urllib.request.Request(url, data=params)
        req.add_header("apikey", GUPSHUP_API_KEY)
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(req) as res:
            print(f"✅ Sent → {phone}: {message[:60]}...")
    except Exception as e:
        print(f"❌ Send error: {e}")

# ================================================================
# ROUTES
# ================================================================
@app.get("/")
def home():
    return {"status": "9faqs Bot v4.0 ✅"}

@app.get("/dashboard")
def dashboard():
    return FileResponse("dashboard.html")

@app.get("/leads")
def get_leads():
    db    = Session()
    leads = db.query(Lead).order_by(Lead.timestamp.desc()).all()
    db.close()
    return [{"phone": l.phone, "name": l.name, "email": l.email or "",
             "course": l.course or "", "status": l.status or "NEW",
             "label": l.label or "NEW", "timestamp": str(l.timestamp)} for l in leads]

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

# Phase 2: Update lead status from dashboard
@app.post("/status/{phone}")
async def update_status(phone: str, req: Request):
    body   = await req.json()
    status = body.get("status", "NEW")
    update_lead_status(phone, status)
    await manager.broadcast({"type": "status_update", "phone": phone, "status": status})
    return {"status": "updated"}

@app.get("/metrics")
def get_metrics():
    db    = Session()
    leads = db.query(Lead).all()
    msgs  = db.query(Message).all()
    db.close()
    today = now_ist().date()
    return {
        "total_leads":         len(leads),
        "enrolled":            len([l for l in leads if l.status == "ENROLLED"]),
        "interested":          len([l for l in leads if l.status == "INTERESTED"]),
        "hot_leads":           len([l for l in leads if "HOT" in (l.status or "")]),
        "new":                 len([l for l in leads if l.status == "NEW"]),
        "today_leads":         len([l for l in leads if l.timestamp and l.timestamp.date() == today]),
        "total_messages":      len(msgs),
        "total_conversations": len(set(m.phone for m in msgs)),
    }

@app.post("/takeover/{phone}")
async def takeover(phone: str):
    set_human_mode(phone, True)
    update_lead_status(phone, "HOT LEAD")
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
    update_lead_status(phone, tag)
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

            # Phase 6: Broadcast for real-time dashboard
            await manager.broadcast({"type": "new_message", "phone": phone,
                                     "name": name, "text": text, "direction": "in"})

            if is_human_mode(phone):
                print(f"👤 Human mode — skipping bot for {phone}")
                return {"status": "ok"}

            # Phase 1: First time user gets welcome
            if is_new_user(phone):
                mark_user_seen(phone)
                reply = BOT_CONFIG["welcome"]
            else:
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