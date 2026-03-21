from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import os
import logging
import httpx
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="9faqs WhatsApp Bot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ZENERAL_API_URL  = "https://zeneral-api-v2.onrender.com/ask"
GUPSHUP_API_KEY  = os.getenv("GUPSHUP_API_KEY")
GUPSHUP_NUMBER   = os.getenv("GUPSHUP_NUMBER")
GUPSHUP_APP_NAME = os.getenv("GUPSHUP_APP_NAME", "9faqsbot")


async def ask_zeneral(question: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                ZENERAL_API_URL,
                json={"question": question}
            )
            data = response.json()
            answer = data.get("answer", "Sorry, I could not find an answer.")
            logger.info(f"Zeneral answered: {answer[:80]}...")
            return answer
    except Exception as e:
        logger.error(f"Error calling Zeneral API: {str(e)}")
        return "Sorry, I'm having trouble answering right now. Please try again later."


async def send_whatsapp_reply(to_number: str, message: str):
    try:
        message = message.replace('"', "'")
        url = "https://api.gupshup.io/sm/api/v1/msg"
        headers = {
            "apikey": GUPSHUP_API_KEY,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "channel": "whatsapp",
            "source": GUPSHUP_NUMBER,
            "destination": to_number,
            "src.name": GUPSHUP_APP_NAME,
            "message": f'{{"type":"text","text":"{message}"}}'
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, data=data)
            logger.info(f"Reply sent to {to_number} | Status: {response.status_code}")
    except Exception as e:
        logger.error(f"Error sending WhatsApp reply: {str(e)}")


@app.get("/")
def home():
    return {"message": "9faqs WhatsApp Bot is running!"}


@app.post("/webhook")
async def webhook(req: Request):
    try:
        data = await req.json()
        logger.info(f"INCOMING: {data}")

        try:
            entry    = data["entry"][0]
            changes  = entry["changes"][0]
            value    = changes["value"]
            messages = value.get("messages", [])

            if not messages:
                return {"status": "ok"}

            msg         = messages[0]
            msg_type    = msg.get("type", "")
            from_number = msg["from"]

            if msg_type == "text":
                user_message = msg["text"]["body"]
                logger.info(f"Message from {from_number}: {user_message}")
                answer = await ask_zeneral(user_message)
                await send_whatsapp_reply(from_number, answer)
            else:
                await send_whatsapp_reply(
                    from_number,
                    "Sorry, I can only understand text messages. Please type your question."
                )

        except (KeyError, IndexError) as e:
            logger.warning(f"Could not parse message: {str(e)}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return {"status": "error", "detail": str(e)}
