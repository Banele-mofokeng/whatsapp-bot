from fastapi import FastAPI, Request
import requests
import os

app = FastAPI()

# 1. Configuration - These should be set in EasyPanel Environment Variables
# Example: http://evolution-api.whatsapp-1:8080 (Internal) or your Public IP
EVO_URL = os.getenv("EVOLUTION_API_URL", "").rstrip("/")
EVO_KEY = os.getenv("EVOLUTION_API_KEY")
INSTANCE = os.getenv("INSTANCE_NAME")

@app.get("/")
def home():
    return {"status": "Bot is running"}

@app.post("/webhook")
async def handle_whatsapp_message(request: Request):
    try:
        data = await request.json()
        
        # Log the incoming message event type for debugging
        event_type = data.get("event", "unknown")
        print(f"📥 Received Event: {event_type}")

        # Check if this is a message update (MESSAGES_UPSERT)
        if event_type == "messages.upsert":
            message_data = data.get("data", {})
            message_content = message_data.get("message", {})
            key = message_data.get("key", {})
            
            remote_jid = key.get("remoteJid")
            from_me = key.get("fromMe", False)

            # 1. Ignore messages sent by the bot itself to prevent infinite loops
            if from_me:
                return {"status": "ignored", "reason": "message_from_me"}

            # 2. Extract text (handles direct text and extended messages)
            text = message_content.get("conversation") or \
                   message_content.get("extendedTextMessage", {}).get("text", "")

            print(f"💬 Message from {remote_jid}: {text}")

            # 3. Simple Bot Logic: Reply to 'hi' or 'hello'
            if text and any(word in text.lower() for word in ["hi", "hello", "hey"]):
                reply_text = "👋 Hello! Your FastAPI bot is officially working."
                print(f"🚀 Sending reply to {remote_jid}...")
                
                result = send_text(remote_jid, reply_text)
                print(f"📤 Send Result: {result}")

        return {"status": "success"}

    except Exception as e:
        print(f"❌ Error in webhook: {str(e)}")
        return {"status": "error", "message": str(e)}

def send_text(to: str, text: str):
    """
    Sends a text message via the Evolution API
    """
    url = f"{EVO_URL}/message/sendText/{INSTANCE}"
    headers = {
        "apikey": EVO_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "number": to,
        "text": text,
        "options": {
            "delay": 1200,
            "presence": "composing",
            "linkPreview": False
        }
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)