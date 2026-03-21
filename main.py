from fastapi import FastAPI, Request
import requests
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

GUPSHUP_API_KEY = os.getenv("GUPSHUP_API_KEY")
GUPSHUP_NUMBER  = os.getenv("GUPSHUP_NUMBER")

@app.get("/")
def home():
    return {"message": "9faqs WhatsApp Bot is running ✅"}

@app.post("/webhook")
async def webhook(req: Request):
    data = await req.json()
    print("INCOMING:", data)

    try:
        messages = data["entry"][0]["changes"][0]["value"].get("messages", [])

        if not messages:
            return {"status": "ok"}

        msg          = messages[0]
        msg_type     = msg.get("type", "")
        phone        = msg["from"]

        if msg_type == "text":
            user_message = msg["text"]["body"]
            print(f"📩 From {phone}: {user_message}")
            send_reply(phone, "Welcome to 9faqs 👋")

    except Exception as e:
        print(f"Error parsing message: {e}")

    return {"status": "ok"}

def send_reply(phone, message):
    url = "https://api.gupshup.io/sm/api/v1/msg"
    headers = {
        "apikey": GUPSHUP_API_KEY
    }
    data = {
        "channel": "whatsapp",
        "source": GUPSHUP_NUMBER,
        "destination": phone,
        "src.name": "9faqsbot",
        "message": '{"type":"text","text":"' + message + '"}'
    }
    response = requests.post(url, headers=headers, data=data)
    print(f"Reply sent: {response.status_code} | {response.text}")