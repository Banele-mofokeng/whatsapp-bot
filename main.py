from fastapi import FastAPI, Request
import requests
import os
import json

app = FastAPI()

# Configuration
EVO_URL = os.getenv("EVOLUTION_API_URL", "").rstrip("/")
EVO_KEY = os.getenv("EVOLUTION_API_KEY")
INSTANCE = os.getenv("INSTANCE_NAME")

@app.get("/")
def home():
    return {"status": "Bot is online", "instance": INSTANCE, "url": EVO_URL}

@app.post("/webhook")
async def handle_whatsapp_message(request: Request):
    try:
        data = await request.json()
        print("\n--- NEW WEBHOOK RECEIVED ---")
        # print(json.dumps(data, indent=2)) # Uncomment this if you want to see the RAW JSON in logs

        event = data.get("event")
        if event != "messages.upsert":
            print(f"⏩ Ignoring event type: {event}")
            return {"status": "ignored"}

        # Extracting data for Evolution API v2.x
        msg_data = data.get("data", {})
        key = msg_data.get("key", {})
        from_me = key.get("fromMe", False)
        remote_jid = key.get("remoteJid")

        if from_me:
            print("🚫 Ignoring message sent by myself.")
            return {"status": "ignored"}

        # Extract message text
        message_obj = msg_data.get("message", {})
        text = message_obj.get("conversation") or \
               message_content.get("extendedTextMessage", {}).get("text", "") or \
               "Non-text message"

        print(f"📩 Message from {remote_jid}: {text}")

        # REPLY TO EVERYTHING (For Testing)
        reply = f"✅ Bot received: '{text}'"
        print(f"📤 Attempting to send reply to {EVO_URL}...")
        
        # Calling the send function
        result = send_text(remote_jid, reply)
        print(f"🏁 Final Result: {result}")

        return {"status": "success"}

    except Exception as e:
        print(f"❌ Error in webhook: {str(e)}")
        return {"status": "error", "message": str(e)}

def send_text(to: str, text: str):
    # CRITICAL: If EVO_URL is http://evolution-api:8080, ensure service name is correct
    url = f"{EVO_URL}/message/sendText/{INSTANCE}"
    headers = {"apikey": EVO_KEY, "Content-Type": "application/json"}
    payload = {"number": to, "text": text}
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        return {"status_code": response.status_code, "response": response.text}
    except Exception as e:
        return {"error": str(e)}