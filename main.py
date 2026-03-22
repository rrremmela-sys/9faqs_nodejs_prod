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
# MULTI-CLIENT CONFIG
# ================================================================
CLIENTS = {
    "9faqs": {
        "name":         "9faqs",
        "welcome":      "👋 *Welcome to 9faqs!*\n\nYour gateway to tech careers 🚀\n\nPlease choose:\n1️⃣ View Courses\n2️⃣ Enroll Now\n3️⃣ Talk to Counselor\n\nOr just ask me anything!",
        "fallback":     "I'm not sure about that 🤔\n\nType *Hi* to see our courses or *3* to talk to a counselor.",
        "enroll_url":   "https://9faqs.com/enroll",
        "support_msg":  "📞 Connecting you to a counselor...\nA human agent will reply shortly! ⏳",
        "catalog_label":"Courses",
        "catalog": {
            "crash_course": {
                "name": "Python Crash Course", "price": "₹1999",
                "duration": "Weekend (Sat & Sun, 10AM–4PM)", "emoji": "🐍",
                "description": "Fast-track live Python training with AI tools intro.",
                "url": "https://9faqs.com/training/python_crash_course"
            },
            "bootcamp": {
                "name": "Python Bootcamp", "price": "Contact us",
                "duration": "90 days Mon–Fri + internship", "emoji": "🚀",
                "description": "Beginner to advanced Python with cloud lab & career prep.",
                "url": "https://9faqs.com/training/python_bootcamp"
            },
            "ai_workshop": {
                "name": "AI Workshop", "price": "₹1999",
                "duration": "4-hour live workshop", "emoji": "🤖",
                "description": "Build a website using AI tools. No coding needed.",
                "url": "https://9faqs.com/training/ai_workshops"
            },
            "python_faqs": {
                "name": "Python FAQs (Free)", "price": "Free",
                "duration": "Self-paced", "emoji": "📚",
                "description": "1736+ Python interview questions with adaptive learning.",
                "url": "https://9faqs.com/python"
            },
        },
        "system_prompt": """You are a helpful WhatsApp assistant for 9faqs (https://9faqs.com), an online tech learning platform in India.

COURSES:
1. Python Crash Course — ₹1999, weekend batches, live, certificate included
2. Python Bootcamp — 90 days Mon-Fri, internship option, cloud lab, career prep
3. AI Workshop — ₹1999, 4-hour live, build website with AI, no coding needed
4. Python FAQs — Free self-learning, 1736+ interview questions

KEY INFO:
- All sessions are LIVE (not recorded)
- Sessions available in Telugu language
- Alumni get 10% discount
- Enroll: https://9faqs.com/enroll

RULES:
- Keep answers SHORT (2-4 lines) — this is WhatsApp
- Be warm and encouraging
- Always suggest enrolling
- Never make up info
- If unsure → "Visit 9faqs.com or type Hi"
- Reply in user's language"""
    },

    # ── TEMPLATE: Add new client below ──
    "resort_demo": {
        "name":         "Sunset Resort",
        "welcome":      "🌅 *Welcome to Sunset Resort!*\n\nYour perfect getaway awaits 🏖️\n\nPlease choose:\n1️⃣ View Rooms\n2️⃣ Book Now\n3️⃣ Talk to Concierge",
        "fallback":     "I'm not sure about that 🤔\n\nType *Hi* to see our rooms or *3* to talk to our team.",
        "enroll_url":   "https://sunsetresort.com/book",
        "support_msg":  "🛎️ Connecting you to our concierge...\nWe'll reply shortly! ⏳",
        "catalog_label":"Rooms",
        "catalog": {
            "deluxe": {
                "name": "Deluxe Room", "price": "₹5000/night",
                "duration": "Min 1 night", "emoji": "🛏️",
                "description": "Comfortable room with garden view and all amenities.",
                "url": "https://sunsetresort.com/rooms/deluxe"
            },
            "suite": {
                "name": "Premium Suite", "price": "₹8000/night",
                "duration": "Min 1 night", "emoji": "👑",
                "description": "Luxury suite with sea view, jacuzzi, and butler service.",
                "url": "https://sunsetresort.com/rooms/suite"
            },
        },
        "system_prompt": """You are a helpful WhatsApp assistant for Sunset Resort.
Help guests with room bookings, amenities, and resort information.
Keep answers SHORT and friendly. Always encourage booking."""
    },
}

def get_client(client_id=None):
    cid = client_id or CLIENT_ID
    return CLIENTS.get(cid, CLIENTS["9faqs"])

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
    client_id  = Column(String, default="9faqs")
    name       = Column(String, default="")
    email      = Column(String, default="")
    course     = Column(String, default="")
    status     = Column(String, default="NEW")
    label      = Column(String, default="NEW")
    timestamp  = Column(DateTime, default=now_ist)

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

def capture_partial_lead(phone, name, cid):
    """Save whoever messages us — even if they never complete enrollment"""
    db   = Session()
    lead = db.query(Lead).filter_by(phone=phone, client_id=cid).first()
    if not lead:
        # New visitor — save with name from WhatsApp profile
        lead = Lead(phone=phone, client_id=cid, name=name,
                    status="NEW", label="NEW", timestamp=now_ist())
        db.add(lead)
        db.commit()
        print(f"👤 [{cid}] Partial lead captured: {name} ({phone})")
    elif lead.name == phone and name != phone:
        # Update name if we only had phone number before
        lead.name = name
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
        flow      = ENROLLMENT_FLOW[step]
        validator = flow.get("validate")
        if validator and not validator(text):
            return flow.get("error", "Invalid input. Please try again.")
        save_to_session(phone, cid, flow["save_as"], text.strip())
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

            # First time user
            if is_new_user(phone, cid):
                mark_user_seen(phone, cid)
                reply = get_client(cid)["welcome"]
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