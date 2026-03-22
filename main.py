from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, String, DateTime, Boolean, Text
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
CLIENT_ID       = os.getenv("CLIENT_ID", "9faqs")   # ← change per deployment

openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

def now_ist():
    return (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).replace(tzinfo=None)

# ================================================================
# MULTI-CLIENT CONFIG (imported from clients_config.py)
# ================================================================
from clients_config import CLIENTS, get_client as _get_client

def get_client(client_id=None):
    cid = client_id or CLIENT_ID
    return _get_client(cid)

# ================================================================
# DATABASE
# ================================================================
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=5,
    pool_timeout=30,
    pool_recycle=1800,
    pool_pre_ping=True
)
Base   = declarative_base()

class Lead(Base):
    __tablename__ = "leads"
    phone      = Column(String, primary_key=True)
    client_id  = Column(String, default="9faqs")
    name       = Column(String, default="")
    email      = Column(String, default="")
    course     = Column(String, default="")
    status             = Column(String, default="NEW")
    label              = Column(String, default="NEW")
    timestamp          = Column(DateTime, default=now_ist)
    last_followup_sent = Column(DateTime, nullable=True)
    last_seen          = Column(DateTime, nullable=True)
    last_seen  = Column(DateTime, default=now_ist)

class Message(Base):
    __tablename__ = "messages"
    id         = Column(String, primary_key=True)   # timestamp-based unique id
    phone      = Column(String)
    client_id  = Column(String, default="9faqs")
    name       = Column(String, default="")
    text       = Column(Text)
    direction  = Column(String)
    timestamp  = Column(DateTime, default=now_ist)

class UserControl(Base):
    __tablename__ = "user_control"
    phone      = Column(String, primary_key=True)
    client_id  = Column(String, default="9faqs")
    is_human   = Column(Boolean, default=False)
    is_new     = Column(Boolean, default=True)
    tag        = Column(String, default="")

Base.metadata.create_all(engine)

# DB Migration
from sqlalchemy import text
with engine.connect() as conn:
    migrations = [
        "ALTER TABLE user_control ADD COLUMN tag VARCHAR DEFAULT ''",
        "ALTER TABLE user_control ADD COLUMN is_new BOOLEAN DEFAULT TRUE",
        "ALTER TABLE user_control ADD COLUMN client_id VARCHAR DEFAULT '9faqs'",
        "ALTER TABLE leads ADD COLUMN email VARCHAR DEFAULT ''",
        "ALTER TABLE leads ADD COLUMN status VARCHAR DEFAULT 'NEW'",
        "ALTER TABLE leads ADD COLUMN label VARCHAR DEFAULT 'NEW'",
        "ALTER TABLE leads ADD COLUMN client_id VARCHAR DEFAULT '9faqs'",
        "ALTER TABLE messages ADD COLUMN client_id VARCHAR DEFAULT '9faqs'",
        "ALTER TABLE leads ADD COLUMN last_seen TIMESTAMP DEFAULT NOW()",
    ]
    for sql in migrations:
        try:
            conn.execute(text(sql))
            conn.commit()
            print(f"✅ Migration: {sql[:60]}")
        except Exception:
            try: conn.rollback()
            except: pass

Session = sessionmaker(bind=engine)

from contextlib import contextmanager

@contextmanager
def get_db():
    """Context manager to handle DB sessions properly"""
    db = Session()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

# ================================================================
# DB HELPERS (all scoped to client_id)
# ================================================================
def make_id(phone, client_id=None):
    return f"{client_id or CLIENT_ID}_{phone}"

def save_lead(phone, name, email, course, client_id=None):
    cid = client_id or CLIENT_ID
    db  = Session()
    lead = Lead(phone=phone, client_id=cid,
                name=name, email=email, course=course,
                status="ENROLLED", label="ENROLLED", timestamp=now_ist())
    db.merge(lead)
    db.commit()
    db.close()
    print(f"💾 [{cid}] LEAD: {name} | {email} | {course}")

def upsert_lead_interest(phone, course, client_id=None):
    cid = client_id or CLIENT_ID
    db  = Session()
    lead = db.query(Lead).filter_by(phone=phone, client_id=cid).first()
    if not lead:
        lead = Lead(phone=phone, client_id=cid,
                    name=phone, course=course, status="INTERESTED",
                    label="INTERESTED", timestamp=now_ist())
        db.add(lead)
    elif lead.status == "NEW":
        lead.status = "INTERESTED"
        lead.label  = "INTERESTED"
        lead.course = course
    db.commit()
    db.close()

def save_message(phone, name, text_content, direction, client_id=None):
    cid    = client_id or CLIENT_ID
    db     = Session()
    msg_id = f"{cid}_{phone}_{now_ist().timestamp()}"
    db.add(Message(id=msg_id, phone=phone, client_id=cid, name=name,
                   text=text_content, direction=direction, timestamp=now_ist()))
    db.commit()
    db.close()
    # Auto-capture partial lead on first inbound message
    if direction == "in":
        capture_partial_lead(phone, name, cid)

def update_last_seen(phone, cid):
    """Update last seen timestamp on every message"""
    db   = Session()
    lead = db.query(Lead).filter_by(phone=phone, client_id=cid).first()
    if lead:
        lead.last_seen = now_ist()
        db.commit()
    db.close()

def find_dropoffs(minutes=30, cid=None):
    """Find leads who were interested but dropped off"""
    cid     = cid or CLIENT_ID
    db      = Session()
    cutoff  = now_ist() - timedelta(minutes=minutes)
    leads   = db.query(Lead).filter(
        Lead.client_id == cid,
        Lead.status != "ENROLLED",
        Lead.status != "CLOSED",
        Lead.status != "NEW",
        Lead.last_seen != None,
        Lead.last_seen < cutoff
    ).all()
    db.close()
    return leads

def send_followup(lead):
    """Send a follow-up message to a dropped-off lead"""
    course  = lead.course or "our courses"
    name    = lead.name if lead.name and lead.name != lead.phone else "there"
    lines   = [
        "Hey " + name + " 👋",
        "",
        "You were checking out *" + course + "* earlier 👀",
        "",
        "Still interested? I can help you enroll right now!",
        "",
        "Type *Hi* to continue or *3* to talk to a counselor 😊"
    ]
    message = "\n".join(lines)
    send_whatsapp(lead.phone, message)
    # Mark as followed up so we don't spam
    db = Session()
    l  = db.query(Lead).filter_by(phone=lead.phone, client_id=lead.client_id).first()
    if l:
        l.status = "FOLLOWUP_SENT"
        l.label  = "FOLLOWUP"
    db.commit()
    db.close()
    print(f"📤 Follow-up sent to {lead.name} ({lead.phone})")

def capture_partial_lead(phone, name, cid):
    """Save whoever messages us — even if they never complete enrollment"""
    db   = Session()
    lead = db.query(Lead).filter_by(phone=phone, client_id=cid).first()
    if not lead:
        lead = Lead(phone=phone, client_id=cid, name=name,
                    status="NEW", label="NEW",
                    timestamp=now_ist(), last_seen=now_ist())
        db.add(lead)
        db.commit()
        print(f"👤 [{cid}] Partial lead captured: {name} ({phone})")
    else:
        # Update name + last_seen
        if lead.name == phone and name != phone:
            lead.name = name
        lead.last_seen = now_ist()
        db.commit()
    db.close()

def get_ctrl(phone, client_id=None):
    cid = client_id or CLIENT_ID
    db  = Session()
    ctrl = db.query(UserControl).filter_by(phone=phone, client_id=cid).first()
    db.close()
    return ctrl

def is_human_mode(phone, client_id=None):
    ctrl = get_ctrl(phone, client_id)
    return ctrl.is_human if ctrl else False

def is_new_user(phone, client_id=None):
    ctrl = get_ctrl(phone, client_id)
    return ctrl.is_new if ctrl else True

def mark_user_seen(phone, client_id=None):
    cid = client_id or CLIENT_ID
    db  = Session()
    ctrl = db.query(UserControl).filter_by(phone=phone, client_id=cid).first()
    if not ctrl:
        ctrl = UserControl(phone=phone, client_id=cid, is_new=False)
        db.add(ctrl)
    else:
        ctrl.is_new = False
    db.commit()
    db.close()

def set_human_mode(phone, value: bool, client_id=None):
    cid = client_id or CLIENT_ID
    db  = Session()
    ctrl = db.query(UserControl).filter_by(phone=phone, client_id=cid).first()
    if not ctrl:
        ctrl = UserControl(phone=phone, client_id=cid, is_human=value)
        db.add(ctrl)
    else:
        ctrl.is_human = value
    db.commit()
    db.close()

def update_lead_status(phone, status, client_id=None):
    cid = client_id or CLIENT_ID
    db  = Session()
    lead = db.query(Lead).filter_by(phone=phone, client_id=cid).first()
    if not lead:
        lead = Lead(phone=phone, client_id=cid,
                    name=phone, status=status, label=status, timestamp=now_ist())
        db.add(lead)
    else:
        lead.status = status
        lead.label  = status
    ctrl = db.query(UserControl).filter_by(phone=phone, client_id=cid).first()
    if not ctrl:
        ctrl = UserControl(phone=phone, client_id=cid, tag=status)
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
# STATE MACHINE (per client)
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

def get_session(phone, cid):
    key = f"{cid}_{phone}"
    if key not in sessions:
        sessions[key] = {"step": None, "data": {}, "fallback_count": 0}
    return sessions[key]

def reset_session(phone, cid):
    sessions[f"{cid}_{phone}"] = {"step": None, "data": {}, "fallback_count": 0}

def set_step(phone, cid, step):
    sessions[f"{cid}_{phone}"]["step"] = step

def save_to_session(phone, cid, key, value):
    sessions[f"{cid}_{phone}"]["data"][key] = value

def get_from_session(phone, cid, key, default=None):
    return sessions.get(f"{cid}_{phone}", {}).get("data", {}).get(key, default)

# ================================================================
# BOT HELPERS
# ================================================================
def catalog_list_msg(client):
    label  = client.get("catalog_label", "Items")
    items  = client.get("catalog", {})
    lines  = [f"📋 *Our {label}:*\n"]
    for i, (_, item) in enumerate(items.items(), 1):
        lines.append(f"{i}. {item['emoji']} {item['name']} — {item['price']}")
    lines.append("\nReply with *number* to know more!")
    return "\n".join(lines)

def catalog_detail_msg(item):
    return (f"{item['emoji']} *{item['name']}*\n\n"
            f"💰 {item['price']}\n"
            f"📅 {item['duration']}\n"
            f"ℹ️ {item['description']}\n\n"
            f"Reply *Enroll* to proceed!\n🔗 {item['url']}")

def enrollment_done_msg(session, client):
    d = session["data"]
    return (f"✅ *Booking Confirmed!*\n\n"
            f"👤 Name: {d.get('name','—')}\n"
            f"📧 Email: {d.get('email','—')}\n"
            f"📱 Phone: {d.get('contact','—')}\n"
            f"📋 Selected: {d.get('course','—')}\n\n"
            f"Our team will contact you within 24 hours! 🎉\n\n"
            f"Type *Hi* to explore more.")

# ================================================================
# AI LAYER
# ================================================================
def call_ai(message: str, client: dict) -> str:
    if not openai_client:
        return None
    try:
        prompt = client.get("system_prompt", "You are a helpful assistant.")
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user",   "content": message}
            ],
            max_tokens=150,
            temperature=0.7
        )
        answer = response.choices[0].message.content.strip()
        if not answer or len(answer) > 400:
            return None
        print(f"🤖 AI: {answer[:80]}...")
        return answer
    except Exception as e:
        print(f"⚠️ AI error: {e}")
        return None

# ================================================================
# RETURNING USER CHECK
# ================================================================
def get_returning_user_msg(phone, cid):
    """Check if user is already enrolled and show personalized message"""
    db   = Session()
    lead = db.query(Lead).filter_by(phone=phone, client_id=cid).first()
    db.close()
    if not lead:
        return None
    name   = lead.name or "there"
    course = lead.course or "our course"
    if lead.status == "ENROLLED":
        lines = [
            "👋 Welcome back *" + name + "*!",
            "",
            "You are already enrolled in *" + course + "* ✅",
            "",
            "What would you like to do?",
            "1️⃣ Enroll in a new course",
            "2️⃣ Talk to counselor about your course",
            "3️⃣ See all courses",
        ]
        return "\n".join(lines)
    elif lead.status == "INTERESTED":
        lines = [
            "👋 Welcome back *" + name + "*!",
            "",
            "You were looking at *" + course + "* last time 👀",
            "",
            "Ready to enroll? Type *Enroll* to continue!",
            "Or type *1* to see all courses.",
        ]
        return "\n".join(lines)
    return None

# ================================================================
# MAIN MESSAGE HANDLER
# ================================================================
def handle_message(text, phone, cid=None):
    cid           = cid or CLIENT_ID
    client        = get_client(cid)
    msg           = text.lower().strip()
    msg_words     = msg.split()
    text_original = text.strip()
    session       = get_session(phone, cid)
    step          = session["step"]
    catalog       = client.get("catalog", {})
    catalog_keys  = list(catalog.keys())

    # ── Enrollment Flow ──
    if step in ENROLLMENT_FLOW:
        flow = ENROLLMENT_FLOW[step]

        # Allow exit from flow anytime
        if msg in ["cancel", "stop", "quit", "exit", "hi", "menu"]:
            reset_session(phone, cid)
            return client["welcome"]

        # Allow AI for off-topic questions during flow
        if "?" in text or len(msg.split()) > 4:
            # Check if it looks like an answer to the current question
            validator = flow.get("validate")
            if validator and not validator(text):
                # Might be a question — try AI first
                ai = call_ai(text_original, client)
                if ai:
                    return ai + "\n\n_(To continue enrollment: " + flow["message"] + ")_"
                return flow.get("error", "Invalid input. Please try again.")

        validator = flow.get("validate")
        if validator and not validator(text):
            return flow.get("error", "Invalid input. Please try again.")

        # Handle skip for email
        val = "not provided" if text.lower().strip() == "skip" else text.strip()
        save_to_session(phone, cid, flow["save_as"], val)
        next_step = flow["next"]
        set_step(phone, cid, next_step)
        if next_step == "done":
            name   = get_from_session(phone, cid, "name", "Friend")
            email  = get_from_session(phone, cid, "email", "")
            course = get_from_session(phone, cid, "course", "General")
            save_lead(phone, name, email, course, cid)
            reply  = enrollment_done_msg(session, client)
            reset_session(phone, cid)
            return reply
        return ENROLLMENT_FLOW[next_step]["message"]

    # ── Restart ──
    if any(x in msg_words for x in ["hi", "hello", "hey", "start", "menu", "restart"]):
        reset_session(phone, cid)
        return client["welcome"]

    # ── View catalog ──
    if msg in ["1", "courses", "course", "rooms", "room", "view", "catalog"]:
        session["fallback_count"] = 0
        set_step(phone, cid, "pick_item")
        return catalog_list_msg(client)

    # ── Pick by number ──
    if step == "pick_item":
        item_map = {str(i+1): key for i, key in enumerate(catalog_keys)}
        if msg in item_map:
            key  = item_map[msg]
            item = catalog[key]
            save_to_session(phone, cid, "course", item["name"])
            set_step(phone, cid, None)
            upsert_lead_interest(phone, item["name"], cid)
            session["fallback_count"] = 0
            return catalog_detail_msg(item)
        return f"Please reply with a number 1-{len(catalog_keys)} 👆"

    # ── Pick by keyword ──
    for key in catalog_keys:
        if key.split("_")[0] in msg or catalog[key]["name"].lower() in msg:
            item = catalog[key]
            save_to_session(phone, cid, "course", item["name"])
            upsert_lead_interest(phone, item["name"], cid)
            set_step(phone, cid, None)
            session["fallback_count"] = 0
            return catalog_detail_msg(item)

    # ── Enroll ──
    if msg in ["2", "enroll", "enroll now", "join", "register", "book", "book now"]:
        set_step(phone, cid, "ask_name")
        session["fallback_count"] = 0
        return f"Great! 🎉\n\n{ENROLLMENT_FLOW['ask_name']['message']}"

    # ── Counselor ──
    if msg in ["3", "counselor", "human", "agent", "help", "talk", "concierge"]:
        set_human_mode(phone, True, cid)
        reset_session(phone, cid)
        update_lead_status(phone, "HOT LEAD", cid)
        session["fallback_count"] = 0
        return client["support_msg"]

    # ── AI Layer ──
    ai_answer = call_ai(text_original, client)
    if ai_answer:
        session["fallback_count"] = 0
        return ai_answer

    # ── Escalation ──
    session["fallback_count"] = session.get("fallback_count", 0) + 1
    if session["fallback_count"] >= 2:
        session["fallback_count"] = 0
        set_human_mode(phone, True, cid)
        return "🙏 Let me connect you to a human agent!\n\nPlease wait..."

    return client["fallback"]

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
            "src.name":    get_client()["name"],
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
# LEAD RECOVERY + ANTI-SPAM
# ================================================================
def can_send_followup(lead, min_hours=24):
    """Check if enough time has passed since last followup"""
    if not lead.last_followup_sent:
        return True
    time_since = now_ist() - lead.last_followup_sent
    return time_since.total_seconds() > (min_hours * 3600)

def mark_followup_sent(phone, cid):
    """Update last_followup_sent timestamp"""
    db   = Session()
    lead = db.query(Lead).filter_by(phone=phone, client_id=cid).first()
    if lead:
        lead.last_followup_sent = now_ist()
        db.commit()
    db.close()

def get_smart_followup_msg(lead):
    """Generate smart personalized followup based on lead status"""
    name   = lead.name or "there"
    course = lead.course or "our courses"

    if lead.status == "INTERESTED":
        return "\n".join([
            "👋 Hi " + name + "!",
            "",
            "You were checking out *" + course + "* recently 👀",
            "",
            "Seats are filling up fast! 🔥",
            "Type *Enroll* to secure your spot or",
            "Type *Hi* to explore more options.",
        ])
    elif lead.status == "NEW":
        return "\n".join([
            "👋 Hi " + name + "!",
            "",
            "We noticed you visited 9faqs recently 🙌",
            "",
            "Can we help you pick the right course?",
            "Type *Hi* to get started!",
        ])
    elif lead.status == "HOT LEAD":
        return "\n".join([
            "👋 Hi " + name + "!",
            "",
            "Our counselor will reach out to you shortly 📞",
            "",
            "Meanwhile, type *Hi* to explore our courses!",
        ])
    return None

# ================================================================
# API ROUTES
# ================================================================
@app.get("/")
def home():
    return {"status": "Zeneral Bot Platform v1.0 ✅", "client": CLIENT_ID}

@app.get("/dashboard")
def dashboard():
    return FileResponse("dashboard.html")

@app.get("/leads")
def get_leads(client_id: str = None):
    cid = client_id or CLIENT_ID
    db  = Session()
    leads = db.query(Lead).filter_by(client_id=cid).order_by(Lead.timestamp.desc()).all()
    db.close()
    return [{"phone": l.phone, "name": l.name, "email": l.email or "",
             "course": l.course or "", "status": l.status or "NEW",
             "label": l.label or "NEW", "timestamp": str(l.timestamp)} for l in leads]

@app.get("/conversations")
def get_conversations(client_id: str = None):
    cid  = client_id or CLIENT_ID
    db   = Session()
    msgs = db.query(Message).filter_by(client_id=cid).order_by(Message.timestamp.desc()).all()
    db.close()
    seen = {}
    for m in msgs:
        if m.phone not in seen:
            seen[m.phone] = {"phone": m.phone, "name": m.name,
                             "last_message": m.text, "timestamp": str(m.timestamp),
                             "is_human": is_human_mode(m.phone, cid)}
    return list(seen.values())

@app.get("/messages/{phone}")
def get_messages(phone: str, client_id: str = None):
    cid  = client_id or CLIENT_ID
    db   = Session()
    msgs = db.query(Message).filter_by(phone=phone, client_id=cid).order_by(Message.timestamp.asc()).all()
    db.close()
    return [{"text": m.text, "direction": m.direction,
             "timestamp": str(m.timestamp), "name": m.name} for m in msgs]

@app.get("/metrics")
def get_metrics(client_id: str = None):
    cid   = client_id or CLIENT_ID
    db    = Session()
    leads = db.query(Lead).filter_by(client_id=cid).all()
    msgs  = db.query(Message).filter_by(client_id=cid).all()
    db.close()
    today = now_ist().date()
    return {
        "client_id":           cid,
        "total_leads":         len(leads),
        "enrolled":            len([l for l in leads if l.status == "ENROLLED"]),
        "interested":          len([l for l in leads if l.status == "INTERESTED"]),
        "hot_leads":           len([l for l in leads if "HOT" in (l.status or "")]),
        "new":                 len([l for l in leads if l.status == "NEW"]),
        "today_leads":         len([l for l in leads if l.timestamp and l.timestamp.date() == today]),
        "total_messages":      len(msgs),
        "total_conversations": len(set(m.phone for m in msgs)),
    }

@app.post("/followup/{phone}")
async def send_followup(phone: str, req: Request):
    """Manually trigger a followup message to a lead"""
    body    = await req.json()
    cid     = body.get("client_id", CLIENT_ID)
    db      = Session()
    lead    = db.query(Lead).filter_by(phone=phone, client_id=cid).first()
    db.close()

    if not lead:
        return {"status": "error", "message": "Lead not found"}

    # Anti-spam check
    if not can_send_followup(lead, min_hours=1):
        return {"status": "skipped", "message": "Followup sent recently — wait before sending again"}

    # Get smart message or use custom
    custom_msg = body.get("message")
    message    = custom_msg or get_smart_followup_msg(lead)

    if not message:
        return {"status": "error", "message": "No followup message available"}

    # Send it
    send_whatsapp(phone, message)
    save_message(phone, "Bot", message, "out", cid)
    mark_followup_sent(phone, cid)

    await manager.broadcast({"type": "new_message", "phone": phone,
                              "text": message, "direction": "out", "name": "Followup"})
    return {"status": "sent", "message": message}

@app.get("/followup/eligible")
def get_followup_eligible(client_id: str = None):
    """Get all leads eligible for followup (not contacted in 24hrs)"""
    cid   = client_id or CLIENT_ID
    db    = Session()
    leads = db.query(Lead).filter_by(client_id=cid).filter(
        Lead.status.in_(["NEW", "INTERESTED", "HOT LEAD"])
    ).all()
    db.close()
    eligible = []
    for l in leads:
        if can_send_followup(l, min_hours=24):
            eligible.append({
                "phone":    l.phone,
                "name":     l.name,
                "course":   l.course,
                "status":   l.status,
                "last_followup": str(l.last_followup_sent) if l.last_followup_sent else "Never"
            })
    return eligible

@app.get("/clients")
def list_clients():
    return [{"id": k, "name": v["name"]} for k, v in CLIENTS.items()]

@app.post("/status/{phone}")
async def update_status(phone: str, req: Request):
    body   = await req.json()
    status = body.get("status", "NEW")
    cid    = body.get("client_id", CLIENT_ID)
    update_lead_status(phone, status, cid)
    await manager.broadcast({"type": "status_update", "phone": phone, "status": status})
    return {"status": "updated"}

@app.post("/takeover/{phone}")
async def takeover(phone: str, req: Request = None):
    cid = CLIENT_ID
    set_human_mode(phone, True, cid)
    update_lead_status(phone, "HOT LEAD", cid)
    await manager.broadcast({"type": "takeover", "phone": phone})
    return {"status": "human mode on"}

@app.post("/handback/{phone}")
async def handback(phone: str):
    set_human_mode(phone, False, CLIENT_ID)
    await manager.broadcast({"type": "handback", "phone": phone})
    return {"status": "bot mode on"}

@app.post("/reply/{phone}")
async def agent_reply(phone: str, req: Request):
    body    = await req.json()
    message = body.get("message", "")
    if message:
        send_whatsapp(phone, message)
        save_message(phone, "Agent", message, "out", CLIENT_ID)
        await manager.broadcast({"type": "new_message", "phone": phone,
                                  "text": message, "direction": "out", "name": "Agent"})
    return {"status": "sent"}

@app.post("/tag/{phone}")
async def tag_lead(phone: str, req: Request):
    body = await req.json()
    tag  = body.get("tag", "")
    update_lead_status(phone, tag, CLIENT_ID)
    await manager.broadcast({"type": "tag_update", "phone": phone, "tag": tag})
    return {"status": "tagged"}

# ================================================================
# DROP-OFF FOLLOW-UP ROUTES
# ================================================================
@app.get("/run-followup")
def run_followup(minutes: int = 30, client_id: str = None):
    """Manually trigger follow-up for dropped-off leads"""
    cid   = client_id or CLIENT_ID
    leads = find_dropoffs(minutes=minutes, cid=cid)
    sent  = []
    for lead in leads:
        try:
            send_followup(lead)
            sent.append({"phone": lead.phone, "name": lead.name, "course": lead.course})
        except Exception as e:
            print(f"❌ Follow-up error for {lead.phone}: {e}")
    return {
        "status": "done",
        "sent_count": len(sent),
        "leads": sent
    }

@app.get("/dropoffs")
def get_dropoffs(minutes: int = 30, client_id: str = None):
    """Preview who would get a follow-up (without sending)"""
    cid   = client_id or CLIENT_ID
    leads = find_dropoffs(minutes=minutes, cid=cid)
    return [{"phone": l.phone, "name": l.name, "course": l.course,
             "status": l.status, "last_seen": str(l.last_seen)} for l in leads]

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
        cid   = CLIENT_ID

        if msg.get("type") == "text":
            text = msg["text"]["body"]
            print(f"📩 [{cid}] {name} ({phone}): {text}")
            save_message(phone, name, text, "in", cid)
            await manager.broadcast({"type": "new_message", "phone": phone,
                                     "name": name, "text": text, "direction": "in",
                                     "client_id": cid})

            if is_human_mode(phone, cid):
                print(f"👤 Human mode — skipping bot for {phone}")
                return {"status": "ok"}

            # Check if returning enrolled user
            if is_new_user(phone, cid):
                mark_user_seen(phone, cid)
                returning = get_returning_user_msg(phone, cid)
                reply = returning if returning else get_client(cid)["welcome"]
            else:
                reply = handle_message(text, phone, cid)

            send_whatsapp(phone, reply)
            save_message(phone, "Bot", reply, "out", cid)
            await manager.broadcast({"type": "new_message", "phone": phone,
                                     "name": "Bot", "text": reply, "direction": "out"})
        else:
            if not is_human_mode(phone, cid):
                send_whatsapp(phone, "Sorry, I only understand text. Type *Hi* to start 👋")

    except Exception as e:
        print(f"❌ Error: {e}")

    return {"status": "ok"}