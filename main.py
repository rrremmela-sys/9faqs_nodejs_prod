from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, String, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import urllib.request
import urllib.parse
import json
import os
from datetime import datetime, timezone, timedelta

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GUPSHUP_API_KEY = os.getenv("GUPSHUP_API_KEY")
GUPSHUP_NUMBER  = os.getenv("GUPSHUP_NUMBER")
DATABASE_URL    = os.getenv("DATABASE_URL", "sqlite:///leads.db")

IST = timezone(timedelta(hours=5, minutes=30))

# ================================
# DATABASE SETUP
# ================================
# Fix for SQLAlchemy + PostgreSQL on Render
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
Base   = declarative_base()

class Lead(Base):
    __tablename__ = "leads"
    phone     = Column(String, primary_key=True)
    name      = Column(String)
    course    = Column(String)
    timestamp = Column(DateTime, default=lambda: datetime.now(IST))

class Message(Base):
    __tablename__ = "messages"
    id         = Column(String, primary_key=True)
    phone      = Column(String)
    name       = Column(String)
    text       = Column(Text)
    direction  = Column(String)  # "in" or "out"
    timestamp  = Column(DateTime, default=lambda: datetime.now(IST))

class UserControl(Base):
    __tablename__ = "user_control"
    phone      = Column(String, primary_key=True)
    is_human   = Column(Boolean, default=False)  # True = human takeover

Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)


# ================================
# WEBSOCKET MANAGER
# ================================
class ConnectionManager:
    def __init__(self):
        self.active_connections = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, data: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(data)
            except:
                pass

manager = ConnectionManager()


# ================================
# DB HELPERS
# ================================
def save_lead(phone, name, course):
    session = Session()
    lead = Lead(phone=phone, name=name, course=course, timestamp=datetime.now(IST))
    session.merge(lead)
    session.commit()
    session.close()
    print(f"💾 Lead saved: {name} | {phone} | {course}")

def save_message(phone, name, text, direction):
    session = Session()
    msg_id = f"{phone}_{datetime.now(IST).timestamp()}"
    msg = Message(id=msg_id, phone=phone, name=name, text=text,
                  direction=direction, timestamp=datetime.now(IST))
    session.add(msg)
    session.commit()
    session.close()

def is_human_mode(phone):
    session = Session()
    ctrl = session.query(UserControl).filter_by(phone=phone).first()
    session.close()
    return ctrl.is_human if ctrl else False

def set_human_mode(phone, value: bool):
    session = Session()
    ctrl = session.query(UserControl).filter_by(phone=phone).first()
    if not ctrl:
        ctrl = UserControl(phone=phone, is_human=value)
        session.add(ctrl)
    else:
        ctrl.is_human = value
    session.commit()
    session.close()


# ================================
# TEMPORARY STATE STORAGE
# ================================
user_state = {}


# ================================
# CONVERSATION LOGIC
# ================================
def handle_message(msg, phone):
    msg = msg.lower().strip()

    if phone not in user_state:
        user_state[phone] = {}
    state = user_state[phone]

    if state.get("step") == "ask_name":
        state["name"] = msg.title()
        state["step"] = "ask_phone"
        return f"Nice to meet you, {msg.title()}! 😊\nPlease share your *phone number* so we can contact you."

    if state.get("step") == "ask_phone":
        name   = state.get("name", "Friend")
        course = state.get("course", "General")
        state["step"] = "done"
        save_lead(phone, name, course)
        return f"Thank you {name}! 🎉\nYou are enrolled in *{course}*.\nOur team will contact you at {msg} shortly.\n\nType *Hi* to explore more courses."

    if any(x in msg for x in ["hi", "hello", "hey", "start"]):
        state.clear()
        return """Welcome to 9faqs 👋

Please choose an option:
1️⃣ View Courses
2️⃣ Talk to Counselor"""

    elif "1" in msg or "course" in msg:
        return """📚 Available Courses:

1. Python Basics
2. AI for Beginners
3. Web Development

Reply with the course name to know more!"""

    elif "python" in msg:
        state["course"] = "Python Basics"
        return """🐍 Python Basics:

📅 Duration: 4 weeks
💰 Price: ₹1999
🗓 Next batch: March 25

Reply *Enroll* to join!"""

    elif "ai" in msg:
        state["course"] = "AI for Beginners"
        return """🤖 AI for Beginners:

📅 Duration: 6 weeks
💰 Price: ₹2999
🗓 Next batch: April 1

Reply *Enroll* to join!"""

    elif "web" in msg:
        state["course"] = "Web Development"
        return """🌐 Web Development:

📅 Duration: 8 weeks
💰 Price: ₹3999
🗓 Next batch: April 5

Reply *Enroll* to join!"""

    elif "enroll" in msg:
        state["step"] = "ask_name"
        return "Great choice! 🎉\nPlease share your *full name* to proceed."

    elif "2" in msg or "counselor" in msg:
        set_human_mode(phone, True)
        return "📞 Connecting you to a counselor...\nA human agent will reply shortly!"

    else:
        return """Sorry, I didn't understand that 🙏

Please choose:
1️⃣ View Courses
2️⃣ Talk to Counselor

Or type *Hi* to start over."""


# ================================
# SEND WHATSAPP REPLY
# ================================
def send_reply(phone, message):
    url = "https://api.gupshup.io/sm/api/v1/msg"
    params = urllib.parse.urlencode({
        "channel": "whatsapp",
        "source": GUPSHUP_NUMBER,
        "destination": phone,
        "src.name": "9faqsbot",
        "message": json.dumps({"type": "text", "text": message})
    }).encode()
    req = urllib.request.Request(url, data=params)
    req.add_header("apikey", GUPSHUP_API_KEY)
    urllib.request.urlopen(req)
    print(f"✅ Reply sent to {phone}: {message[:50]}...")


# ================================
# ROUTES
# ================================
@app.get("/")
def home():
    return {"message": "9faqs Bot running ✅"}

@app.get("/dashboard")
def dashboard():
    return FileResponse("dashboard.html")

@app.get("/leads")
def get_leads():
    session = Session()
    leads = session.query(Lead).all()
    session.close()
    return [{"phone": l.phone, "name": l.name, "course": l.course,
             "timestamp": str(l.timestamp)} for l in leads]

@app.get("/conversations")
def get_conversations():
    session = Session()
    # Get unique phones with latest message
    messages = session.query(Message).order_by(Message.timestamp.desc()).all()
    session.close()
    seen = {}
    for m in messages:
        if m.phone not in seen:
            seen[m.phone] = {
                "phone": m.phone,
                "name": m.name,
                "last_message": m.text,
                "timestamp": str(m.timestamp),
                "is_human": is_human_mode(m.phone)
            }
    return list(seen.values())

@app.get("/messages/{phone}")
def get_messages(phone: str):
    session = Session()
    msgs = session.query(Message).filter_by(phone=phone)\
                  .order_by(Message.timestamp.asc()).all()
    session.close()
    return [{"text": m.text, "direction": m.direction,
             "timestamp": str(m.timestamp)} for m in msgs]

@app.post("/takeover/{phone}")
async def takeover(phone: str):
    set_human_mode(phone, True)
    await manager.broadcast({"type": "takeover", "phone": phone})
    return {"status": "human mode on"}

@app.post("/handback/{phone}")
async def handback(phone: str):
    set_human_mode(phone, False)
    await manager.broadcast({"type": "handback", "phone": phone})
    return {"status": "bot mode on"}

@app.post("/reply/{phone}")
async def agent_reply(phone: str, req: Request):
    body = await req.json()
    message = body.get("message", "")
    if message:
        send_reply(phone, message)
        save_message(phone, "Agent", message, "out")
        await manager.broadcast({
            "type": "new_message",
            "phone": phone,
            "text": message,
            "direction": "out"
        })
    return {"status": "sent"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
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

        msg      = messages[0]
        msg_type = msg.get("type", "")
        phone    = msg["from"]
        name     = contacts[0]["profile"]["name"] if contacts else phone

        if msg_type == "text":
            user_message = msg["text"]["body"]
            print(f"📩 From {name} ({phone}): {user_message}")

            # Save incoming message
            save_message(phone, name, user_message, "in")

            # Broadcast to dashboard
            await manager.broadcast({
                "type": "new_message",
                "phone": phone,
                "name": name,
                "text": user_message,
                "direction": "in"
            })

            # Check if human has taken over
            if is_human_mode(phone):
                print(f"👤 Human mode active for {phone} — skipping bot reply")
                return {"status": "ok"}

            # Bot reply
            reply = handle_message(user_message, phone)
            send_reply(phone, reply)
            save_message(phone, "Bot", reply, "out")

            await manager.broadcast({
                "type": "new_message",
                "phone": phone,
                "name": "Bot",
                "text": reply,
                "direction": "out"
            })

        else:
            if not is_human_mode(phone):
                send_reply(phone, "Sorry, I can only understand text messages. Type *Hi* to start 👋")

    except Exception as e:
        print(f"❌ Error: {e}")

    return {"status": "ok"}