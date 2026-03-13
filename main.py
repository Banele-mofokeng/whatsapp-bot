from fastapi import FastAPI, Request
import requests
import os

app = FastAPI()

# These variables come from your EasyPanel environment settings
EVO_URL = os.getenv("EVOLUTION_API_URL")
EVO_KEY = os.getenv("EVOLUTION_API_KEY")
INSTANCE = os.getenv("INSTANCE_NAME")

@app.post("/webhook")
async def handle_whatsapp_message(request: Request):
    data = await request.json()
    
    # 1. Extract the message and sender's number
    # Evolution API sends data in a specific "MESSAGES_UPSERT" format
    try:
        message_text = data['data']['message']['conversation']
        remote_jid = data['data']['key']['remoteJid']
        from_me = data['data']['key']['fromMe']
        
        # 2. Ignore messages sent by the bot itself to avoid infinite loops
        if from_me:
            return {"status": "ignored"}

        # 3. Simple Logic: If user says "Hi", reply with a greeting
        if "hi" in message_text.lower():
            send_text(remote_jid, "👋 Hello! Your FastAPI bot is officially alive.")
            
    except KeyError:
        # This handles other events like status updates or image messages
        pass

    return {"status": "success"}

def send_text(to, text):
    url = f"{EVO_URL}/message/sendText/{INSTANCE}"
    headers = {"apikey": EVO_KEY, "Content-Type": "application/json"}
    payload = {
        "number": to,
        "options": {"delay": 1200, "presence": "composing"},
        "textMessage": {"text": text}
    }
    response = requests.post(url, json=payload, headers=headers)
    return response.json()