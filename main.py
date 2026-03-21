from fastapi import FastAPI, Request
import urllib.request
import urllib.parse
import json
import os

app = FastAPI()

GUPSHUP_API_KEY = os.getenv("GUPSHUP_API_KEY")
GUPSHUP_NUMBER  = os.getenv("GUPSHUP_NUMBER")

@app.get("/")
def home():
    return {"message": "9faqs WhatsApp Bot is running"}

@app.post("/webhook")
async def webhook(req: Request):
    data = await req.json()
    print("INCOMING:", data)
    try:
        messages = data["entry"][0]["changes"][0]["value"].get("messages", [])
        if not messages:
            return {"status": "ok"}
        msg   = messages[0]
        phone = msg["from"]
        if msg.get("type") == "text":
            text = msg["text"]["body"]
            print(f"From {phone}: {text}")
            send_reply(phone, "Welcome to 9faqs 👋")
    except Exception as e:
        print(f"Error: {e}")
    return {"status": "ok"}

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
    print(f"Reply sent to {phone}")
