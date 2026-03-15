import os
import requests
from datetime import datetime, timedelta, time
from fastapi import FastAPI, Request
from sqlmodel import SQLModel, Field, create_engine, Session, select

# --- CONFIGURATION ---
# These must be set in your EasyPanel Environment Variables
EVO_URL = os.getenv("EVOLUTION_API_URL", "").rstrip("/")
EVO_KEY = os.getenv("EVOLUTION_API_KEY")
INSTANCE = os.getenv("INSTANCE_NAME")
DATABASE_URL = os.getenv("DATABASE_URL", "postgres://postgres:1a4d1b7774b22ad8dca6@whatsapp-1_evolution-api-db:5432/whatsapp-1?sslmode=disable")

# --- DATABASE MODELS ---
class Appointment(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    customer_number: str
    customer_name: str
    service_type: str
    appointment_date: datetime
    status: str = "Confirmed"

engine = create_engine(DATABASE_URL)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

# --- APP INITIALIZATION ---
app = FastAPI()

@app.on_event("startup")
def on_startup():
    create_db_and_tables()

# --- HELPER FUNCTIONS ---

def send_whatsapp(endpoint: str, payload: dict):
    """Generic function to send data to Evolution API"""
    url = f"{EVO_URL}/{endpoint}/{INSTANCE}"
    headers = {"apikey": EVO_KEY, "Content-Type": "application/json"}
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        return response.json()
    except Exception as e:
        print(f"❌ API Error: {str(e)}")
        return {"error": str(e)}

def get_available_slots(target_date: datetime.date):
    """Checks DB for existing appointments and returns free 1-hour slots"""
    start_working = time(9, 0) # 9 AM
    end_working = time(17, 0)  # 5 PM
    
    with Session(engine) as session:
        statement = select(Appointment).where(
            Appointment.appointment_date >= datetime.combine(target_date, time.min),
            Appointment.appointment_date <= datetime.combine(target_date, time.max)
        )
        booked = session.exec(statement).all()
        booked_times = [a.appointment_date.strftime("%H:%M") for a in booked]

    slots = []
    curr = datetime.combine(target_date, start_working)
    while curr.time() < end_working:
        t_str = curr.strftime("%H:%M")
        if t_str not in booked_times:
            slots.append(t_str)
        curr += timedelta(hours=1)
    return slots

# --- WEBHOOK HANDLER ---

@app.post("/webhook")
async def handle_webhook(request: Request):
    data = await request.json()
    event = data.get("event")
    
    # 1. Handle New Incoming Messages
    if event == "messages.upsert":
        msg_data = data.get("data", {})
        if msg_data.get("key", {}).get("fromMe"): return {"status": "ignored"}
        
        customer_num = msg_data['key']['remoteJid']
        text = (msg_data.get("message", {}).get("conversation") or "").lower()

        if "book" in text or "hi" in text:
            # Send initial Menu
            payload = {
                "number": customer_num,
                "title": "Banele's Booking Bot 📅",
                "description": "How can we help you today?",
                "buttons": [
                    {"display": "Book for Tomorrow", "id": "action_book_tomorrow"},
                    {"display": "My Appointments", "id": "action_view"}
                ]
            }
            send_whatsapp("message/sendButtons", payload)

    # 2. Handle Button Responses
    elif event == "buttons.response":
        button_id = data['data']['id']
        customer_num = data['data']['key']['remoteJid']

        if button_id == "action_book_tomorrow":
            tomorrow = datetime.now() + timedelta(days=1)
            date_str = tomorrow.strftime("%Y-%m-%d")
            slots = get_available_slots(tomorrow.date())
            
            if not slots:
                send_whatsapp("message/sendText", {"number": customer_num, "text": "Sorry, tomorrow is fully booked!"})
            else:
                # Send List of Slots
                rows = [{"title": f"Time: {s}", "rowId": f"final_book_{date_str}_{s}"} for s in slots]
                payload = {
                    "number": customer_num,
                    "title": "Select a Time 🕒",
                    "description": f"Available slots for {date_str}:",
                    "buttonText": "See Slots",
                    "sections": [{"title": "Tomorrow", "rows": rows}]
                }
                send_whatsapp("message/sendList", payload)

    # 3. Handle List Selections (Final Booking)
    elif event == "list.response":
        row_id = data['data']['rowId'] # e.g., final_book_2026-03-16_10:00
        customer_num = data['data']['key']['remoteJid']
        customer_name = data['data']['pushName']

        if row_id.startswith("final_book_"):
            parts = row_id.split("_")
            date_part = parts[2] # 2026-03-16
            time_part = parts[3] # 10:00
            
            dt_obj = datetime.strptime(f"{date_part} {time_part}", "%Y-%m-%d %H:%M")
            
            with Session(engine) as session:
                new_appt = Appointment(
                    customer_number=customer_num,
                    customer_name=customer_name,
                    service_type="General Consultation",
                    appointment_date=dt_obj
                )
                session.add(new_appt)
                session.commit()

            send_whatsapp("message/sendText", {
                "number": customer_num, 
                "text": f"✅ Confirmed! See you on {date_part} at {time_part}."
            })

    return {"status": "success"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)