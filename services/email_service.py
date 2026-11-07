"""Email service for sending session summaries."""

import os
import smtplib
import asyncio
from email.message import EmailMessage
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

async def send_session_summary_email(session_id: str, session_data: dict, transcript: list) -> bool:
    """
    Compiles session storage and transcript data into a formatted email
    and sends it to the target recipient address.
    """
    sender_email = os.getenv("AGENT_SENDER_EMAIL")
    sender_password = os.getenv("AGENT_SENDER_APP_PASSWORD")
    recipient_email = os.getenv("TARGET_RECIPIENT_EMAIL", "Britomars04@gmail.com")
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 465))

    if not sender_email or not sender_password:
        print("[EmailService Error] Sender credentials not configured in environment variables.")
        return False

    # Format execution timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Build clear textual presentation of stored session data
    formatted_stored_info = ""
    if isinstance(session_data, dict) and session_data:
        for key, value in session_data.items():
            formatted_stored_info += f"- **{key}**: {value}\n"
    else:
        formatted_stored_info = "No specific stored parameters recorded for this session."

    # Build formatted transcript representation
    formatted_transcript = ""
    if isinstance(transcript, list) and transcript:
        for entry in transcript:
            speaker = entry.get("role", entry.get("speaker", "Unknown"))
            text = entry.get("text", entry.get("content", ""))
            formatted_transcript += f"[{speaker.capitalize()}]: {text}\n"
    elif isinstance(transcript, str):
        formatted_transcript = transcript
    else:
        formatted_transcript = "No transcript recorded."

    # Construct plain text body
    email_body = f"""AUTOMATED AGENT SESSION REPORT
========================================
Session ID: {session_id}
Date/Time:  {timestamp}
Recipient:  {recipient_email}
========================================

--- STORED SESSION INFORMATION ---
{formatted_stored_info}

--- COMPLETE SESSION TRANSCRIPT ---
{formatted_transcript}

========================================
End of Session Report.
"""

    # Prepare Email Structure
    msg = EmailMessage()
    msg["Subject"] = f"Session Report [{session_id}] - {timestamp}"
    msg["From"] = sender_email
    msg["To"] = recipient_email
    msg.set_content(email_body)

    # Dispatch via non-blocking thread execution
    def _send():
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)

    try:
        await asyncio.to_thread(_send)
        print(f"[EmailService Success] Session summary successfully sent to {recipient_email}")
        return True
    except Exception as e:
        print(f"[EmailService Error] Failed to send email for session {session_id}: {str(e)}")
        return False