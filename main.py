from fastapi import FastAPI, Request

app = FastAPI()

@app.get("/")
def home():
    return {"message": "Webhook running"}

@app.post("/webhook")
async def webhook(req: Request):
    data = await req.json()
    print("INCOMING:", data)
    return {"status": "ok"}
