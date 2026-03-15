import os
import requests
from datetime import datetime, timedelta, time
from fastapi import FastAPI, Request
from sqlmodel import SQLModel, Field, create_engine, Session, select

# --- 1. CONFIGURATION ---
EVO_URL = os.getenv("EVOLUTION_API_URL", "").rstrip("/")
EVO_KEY = os.getenv("EVOLUTION_API_KEY")
INSTANCE = os.getenv("INSTANCE_NAME", "Banele")

# Database Connection Logic
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if not DATABASE_URL:
    DATABASE_URL = "postgresql://postgres:0e6dc8c3d4a23e601efe@whatsapp_bot_booking-db:5432/whatsapp_bot"

engine = create_engine(DATABASE_URL)

# --- 2. DATABASE MODELS ---
class Appointment(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    customer_number: str
    customer_name: str
    service_type: str
    appointment_date: datetime
    status: str = "Confirmed"

# In-memory session state to track where each user is in the flow
# Format: { "27xxxxxxx@s.whatsapp.net": { "state": "awaiting_slot", "date": "2026-03-16", "slots": [...] } }
user_sessions: dict = {}

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

# --- 3. APP INITIALIZATION ---
app = FastAPI()

@app.on_event("startup")
def on_startup():
    print("🚀 Bot starting up...")
    create_db_and_tables()
    print("✅ Database tables verified/created.")

# --- 4. HELPER FUNCTIONS ---

def send_text(number: str, text: str):
    """Send a plain text WhatsApp message via Evolution API"""
    url = f"{EVO_URL}/message/sendText/{INSTANCE}"
    headers = {"apikey": EVO_KEY, "Content-Type": "application/json"}
    payload = {"number": number, "text": text}
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        print(f"📡 sendText response: {response.status_code} - {response.text}")
        return response.json()
    except Exception as e:
        print(f"❌ API Error: {str(e)}")
        return {"error": str(e)}

def get_available_slots(target_date: datetime.date) -> list[str]:
    """Returns list of free 1-hour slot strings for a given date"""
    start_working = time(9, 0)
    end_working = time(17, 0)

    with Session(engine) as session:
        statement = select(Appointment).where(
            Appointment.appointment_date >= datetime.combine(target_date, time.min),
            Appointment.appointment_date <= datetime.combine(target_date, time.max),
            Appointment.status == "Confirmed"
        )
        booked = session.exec(statement).all()
        booked_times = {a.appointment_date.strftime("%H:%M") for a in booked}

    slots = []
    curr = datetime.combine(target_date, start_working)
    while curr.time() < end_working:
        t_str = curr.strftime("%H:%M")
        if t_str not in booked_times:
            slots.append(t_str)
        curr += timedelta(hours=1)
    return slots

def send_main_menu(number: str):
    """Send the main menu as a numbered text message"""
    text = (
        "*Banele's Booking Bot 📅*\n\n"
        "How can we help you today?\n\n"
        "1️⃣ Book for Tomorrow\n"
        "2️⃣ My Appointments\n\n"
        "Reply with *1* or *2*"
    )
    send_text(number, text)

def send_slots_menu(number: str, slots: list[str], date_str: str):
    """Send available time slots as a numbered text message"""
    lines = [f"{i+1}️⃣  {slot}" for i, slot in enumerate(slots)]
    text = (
        f"*Available slots for {date_str}* 🕒\n\n"
        + "\n".join(lines)
        + "\n\nReply with the *number* of the slot you want."
    )
    send_text(number, text)

# --- 5. WEBHOOK HANDLER ---

@app.post("/webhook")
async def handle_webhook(request: Request):
    data = await request.json()
    event = data.get("event")

    if event != "messages.upsert":
        return {"status": "ignored"}

    msg_data = data.get("data", {})

    # Ignore messages sent by the bot itself
    if msg_data.get("key", {}).get("fromMe"):
        return {"status": "ignored"}

    customer_num = msg_data["key"]["remoteJid"]
    customer_name = msg_data.get("pushName", "Valued Customer")

    # Extract the message text (handles both plain conversation and extended text)
    message_obj = msg_data.get("message", {})
    text = (
        message_obj.get("conversation")
        or message_obj.get("extendedTextMessage", {}).get("text")
        or ""
    ).strip().lower()

    session = user_sessions.get(customer_num, {})
    state = session.get("state", "idle")

    print(f"📩 From {customer_num} | State: {state} | Text: '{text}'")

    # ── IDLE / MAIN MENU TRIGGERS ──────────────────────────────────────────────
    if state == "idle" or any(word in text for word in ["hi", "hello", "menu", "start", "hey"]):
        user_sessions[customer_num] = {"state": "main_menu"}
        send_main_menu(customer_num)
        return {"status": "success"}

    # ── MAIN MENU RESPONSE ─────────────────────────────────────────────────────
    if state == "main_menu":
        if text == "1":
            tomorrow = datetime.now() + timedelta(days=1)
            date_str = tomorrow.strftime("%Y-%m-%d")
            slots = get_available_slots(tomorrow.date())

            if not slots:
                send_text(customer_num, "😔 Sorry, tomorrow is fully booked! Reply *menu* to go back.")
                user_sessions[customer_num] = {"state": "idle"}
            else:
                user_sessions[customer_num] = {
                    "state": "awaiting_slot",
                    "date": date_str,
                    "slots": slots
                }
                send_slots_menu(customer_num, slots, date_str)

        elif text == "2":
            with Session(engine) as db_session:
                statement = select(Appointment).where(
                    Appointment.customer_number == customer_num,
                    Appointment.status == "Confirmed"
                )
                appointments = db_session.exec(statement).all()

            if not appointments:
                send_text(customer_num, "📭 You have no upcoming appointments.\n\nReply *menu* to go back.")
            else:
                lines = [
                    f"📌 {a.appointment_date.strftime('%Y-%m-%d at %H:%M')} — {a.service_type}"
                    for a in appointments
                ]
                text_out = "*Your Appointments* 📋\n\n" + "\n".join(lines) + "\n\nReply *menu* to go back."
                send_text(customer_num, text_out)

            user_sessions[customer_num] = {"state": "idle"}

        else:
            send_text(customer_num, "Please reply with *1* or *2* to choose an option.")

        return {"status": "success"}

    # ── SLOT SELECTION ─────────────────────────────────────────────────────────
    if state == "awaiting_slot":
        slots = session.get("slots", [])
        date_str = session.get("date", "")

        if text.isdigit():
            slot_index = int(text) - 1
            if 0 <= slot_index < len(slots):
                chosen_time = slots[slot_index]
                dt_obj = datetime.strptime(f"{date_str} {chosen_time}", "%Y-%m-%d %H:%M")

                with Session(engine) as db_session:
                    new_appt = Appointment(
                        customer_number=customer_num,
                        customer_name=customer_name,
                        service_type="General Consultation",
                        appointment_date=dt_obj
                    )
                    db_session.add(new_appt)
                    db_session.commit()

                user_sessions[customer_num] = {"state": "idle"}
                send_text(
                    customer_num,
                    f"✅ *Booking Confirmed!*\n\n"
                    f"Hi {customer_name}, you're all set!\n"
                    f"📅 Date: {date_str}\n"
                    f"🕒 Time: {chosen_time}\n"
                    f"💼 Service: General Consultation\n\n"
                    f"Reply *menu* anytime to book again."
                )
            else:
                send_text(customer_num, f"Invalid choice. Please reply with a number between 1 and {len(slots)}.")
        else:
            send_text(customer_num, f"Please reply with a number to pick a time slot, e.g. *1*")

        return {"status": "success"}

    # ── FALLBACK ───────────────────────────────────────────────────────────────
    user_sessions[customer_num] = {"state": "idle"}
    send_main_menu(customer_num)
    return {"status": "success"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)