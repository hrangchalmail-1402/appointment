import streamlit as st
import sqlite3
from datetime import datetime, date, time
from google.oauth2 import service_account
from googleapiclient.discovery import build

# --- GOOGLE CALENDAR CONFIGURATION ---
# Replace this with your actual Google Calendar ID
CALENDAR_ID = "hrangchalmail@gmail.com"
SCOPES = ['https://googleapis.com']

def get_calendar_service():
    """Initializes the Google Calendar API client using service account keys."""
    try:
        creds = service_account.Credentials.from_service_account_file(
            'google_keys.json', scopes=SCOPES
        )
        return build('calendar', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"Failed to connect to Google Calendar API: {e}")
        return None

def add_google_calendar_event(summary, date_str, time_str, description):
    """Inserts a new event into the designated Google Calendar."""
    service = get_calendar_service()
    if not service:
        return None
    
    # Format times into ISO 8601 formatting required by Google
    start_datetime = f"{date_str}T{time_str}:00"
    # Assume 1-hour interview block duration
    hour = int(time_str.split(':')[0])
    minute = time_str.split(':')[1]
    end_datetime = f"{date_str}T{str(hour+1).zfill(2)}:{minute}:00"
    
    event = {
        'summary': summary,
        'description': description,
        'start': {'dateTime': start_datetime, 'timeZone': 'UTC'},
        'end': {'dateTime': end_datetime, 'timeZone': 'UTC'},
    }
    
    try:
        created_event = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
        return created_event.get('id')
    except Exception as e:
        st.warning(f"Database saved, but Google Calendar Sync failed: {e}")
        return None

def delete_google_calendar_event(event_id):
    """Removes an event from Google Calendar using its Event ID."""
    service = get_calendar_service()
    if not service or not event_id:
        return
    try:
        service.events().delete(calendarId=CALENDAR_ID, eventId=event_id).execute()
    except Exception as e:
        st.error(f"Failed to delete event from Google Calendar: {e}")

# --- SQLITE DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('reservations.db', check_same_thread=False)
    cursor = conn.cursor()
    # Added gcal_event_id string column to link SQLite rows directly to Google Calendar instances
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS interviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_name TEXT NOT NULL,
            bookedby_name TEXT NOT NULL,
            interview_date TEXT NOT NULL,
            interview_time TEXT NOT NULL,
            notes TEXT,
            gcal_event_id TEXT
        )
    ''')
    conn.commit()
    return conn

conn = init_db()
cursor = conn.cursor()

# --- STREAMLIT UI SETUP ---
st.set_page_config(page_title="Appointment Scheduler", page_icon="📅", layout="centered")
st.title("📅 CM Appointment Reservation Sync")

st.sidebar.header("Navigation")
menu = ["Book Appointment", "View Schedule", "Cancel Appointment"]
choice = st.sidebar.selectbox("Go to:", menu)

# --- BOOK APPOINTMENT WITH GOOGLE SYNC ---
if choice == "Book Appointment":
    st.subheader("📝 Schedule a New Appointment")
    
    with st.form("booking_form", clear_on_submit=True):
        candidate = st.text_input("Full Name")
        bookedby = st.text_input("Book Appointment by")
        
        col1, col2 = st.columns(2)
        with col1:
            booking_date = st.date_input("Select Date", min_value=date.today())
        with col2:
            booking_time = st.time_input("Select Time", value=time(9, 0))
            
        notes = st.text_area("Interview Notes / Job Role")
        submit = st.form_submit_button("Confirm Booking")
        
        if submit:
            if not candidate.strip() or not bookedby.strip():
                st.error("Please fill out both Full N ame and Book Appointment By names.")
            else:
                date_s = str(booking_date)
                time_s = str(booking_time)[:5]
                summary = f"Interview: {candidate} vs {bookedby}"
                
                st.info("Syncing appointment with Google Calendar...")
                gcal_id = add_google_calendar_event(summary, date_s, time_s, notes)
                
                cursor.execute(
                    "INSERT INTO interviews (candidate_name, bookedby_name, interview_date, interview_time, notes, gcal_event_id) VALUES (?, ?, ?, ?, ?, ?)",
                    (candidate, bookedby, date_s, time_s, notes, gcal_id)
                )
                conn.commit()
                st.success(f"🎉 Scheduled successfully & synced to Google Calendar!")

# --- VIEW SCHEDULE ---
elif choice == "View Schedule":
    st.subheader("📋 Current Interview Calendar")
    cursor.execute("SELECT id, candidate_name, bookedby_name, interview_date, interview_time, notes FROM interviews ORDER BY interview_date, interview_time")
    data = cursor.fetchall()
    
    if not data:
        st.info("No interviews scheduled at the moment.")
    else:
        for row in data:
            with st.expander(f"👤 {row[1]} vs {row[2]} — 📅 {row[3]} at ⏰ {row[4]}"):
                st.write(f"**Candidate:** {row[1]} | **bookedby:** {row[2]}")
                st.write(f"**Notes:** {row[5] if row[5] else 'None'}")

# --- CANCEL RESERVATION WITH GOOGLE REMOVAL ---
elif choice == "Cancel Appointment":
    st.subheader("❌ Cancel a Reservation")
    cursor.execute("SELECT id, candidate_name, interview_date, gcal_event_id FROM interviews")
    records = cursor.fetchall()
    
    if not records:
        st.info("No appointments available to cancel.")
    else:
        record_dict = {f"{r[1]} ({r[2]})": (r[0], r[3]) for r in records}
        selected_record = st.selectbox("Select interview to cancel:", list(record_dict.keys()))
        db_id, gcal_id = record_dict[selected_record]
        
        if st.button("Delete Appointment Permanently", type="primary"):
            if gcal_id:
                st.info("Removing event from Google Calendar...")
                delete_google_calendar_event(gcal_id)
                
            cursor.execute("DELETE FROM interviews WHERE id = ?", (db_id,))
            conn.commit()
            st.warning("Appointment deleted successfully from everywhere.")
            st.rerun()