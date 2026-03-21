from fastapi import FastAPI, Request
from sqlalchemy import create_engine, Column, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import urllib.request
import urllib.parse
import json
import os
from datetime import datetime

app = FastAPI()

GUPSHUP_API_KEY = os.getenv("GUPSHUP_API_KEY")
GUPSHUP_NUMBER  = os.getenv("GUPSHUP_NUMBER")

# ================================
# DATABASE SETUP
# ================================
engine = create_engine("sqlite:///leads.db")
Base   = declarative_base()

class Lead(Base):
    __tablename__ = "leads"
    phone     = Column(String, primary_key=True)
    name      = Column(String)
    course    = Column(String)
    timestamp = Column(DateTime, default=datetime.now)

Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

def save_lead(phone, name, course):
    session = Session()
    lead = Lead(phone=phone, name=name, course=course, timestamp=datetime.now())
    session.merge(lead)
    session.commit()
    session.close()
    print(f"💾 Lead saved: {name} | {phone} | {course}")


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

    # ── Lead Capture Flow ──
    if state.get("step") == "ask_name":
        state["name"] = msg.title()
        state["step"] = "ask_phone"
        return f"Nice to meet you, {msg.title()}! 😊\nPlease share your *phone number* so we can contact you."

    if state.get("step") == "ask_phone":
        name   = state.get("name", "Friend")
        course = state.get("course", "General")
        state["step"] = "done"
        # Save to database
        save_lead(phone, name, course)
        return f"Thank you {name}! 🎉\nYou are enrolled in *{course}*.\nOur team will contact you at {msg} shortly.\n\nType *Hi* to explore more courses."

    # ── Menu Flow ──
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
        return "📞 Connecting you to a counselor...\nOur team will reach out to you shortly!"

    else:
        return """Sorry, I didn't understand that 🙏

Please choose:
1️⃣ View Courses
2️⃣ Talk to Counselor

Or type *Hi* to start over."""


# ================================
# VIEW ALL LEADS (Admin endpoint)
# ================================
@app.get("/leads")
def get_leads():
    session = Session()
    leads = session.query(Lead).all()
    session.close()
    return [
        {
            "phone": l.phone,
            "name": l.name,
            "course": l.course,
            "timestamp": str(l.timestamp)
        }
        for l in leads
    ]


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
    return {"message": "9faqs Enrollment Bot is running ✅"}


@app.post("/webhook")
async def webhook(req: Request):
    data = await req.json()
    print("INCOMING:", data)

    try:
        messages = data["entry"][0]["changes"][0]["value"].get("messages", [])

        if not messages:
            return {"status": "ok"}

        msg      = messages[0]
        msg_type = msg.get("type", "")
        phone    = msg["from"]

        if msg_type == "text":
            user_message = msg["text"]["body"]
            print(f"📩 From {phone}: {user_message}")
            reply = handle_message(user_message, phone)
            send_reply(phone, reply)
        else:
            send_reply(phone, "Sorry, I can only understand text messages. Type *Hi* to start 👋")

    except Exception as e:
        print(f"❌ Error: {e}")

    return {"status": "ok"}