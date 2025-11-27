import smtplib
import ssl
from email.message import EmailMessage
import os
import asyncio
from typing import Optional

from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel, EmailStr

# --- 1. Configuration ---
# IMPORTANT: Never hardcode credentials in production.
# Use environment variables for sensitive information.
class EmailConfig:
    """Stores configuration for the SMTP server."""
    # Use environment variables if available, otherwise use placeholders
    SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 465)) # 465 for SSL, 587 for TLS
    SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "velpurianand8005@gmail.com")
    PASSWORD = os.environ.get("SENDER_PASSWORD")

    if SENDER_EMAIL == "your_sender_email@example.com" or PASSWORD == "your_app_password":
        print("Warning: Using placeholder email/password. Please set environment variables (SMTP_SERVER, SMTP_PORT, SENDER_EMAIL, SENDER_PASSWORD) or update the EmailConfig class.")

# --- 2. Pydantic Model for Request Body ---
class EmailRequest(BaseModel):
    """Defines the structure for the incoming email request."""
    recipient_email: EmailStr
    subject: str
    body: str
    sender_name: Optional[str] = None # Optional name to appear as the sender

# --- 3. Core Email Sending Logic (Synchronous) ---
def send_email_sync(recipient: str, subject: str, body: str, sender_name: Optional[str]):
    """
    Sends the email using smtplib. This is a synchronous (blocking) operation.
    It is designed to run in a separate thread.
    """
    msg = EmailMessage()
    msg.set_content(body)
    msg["Subject"] = subject
    msg["To"] = recipient

    # Set the 'From' field. Use the provided sender_name if available.
    if sender_name:
        msg["From"] = f"{sender_name} <{EmailConfig.SENDER_EMAIL}>"
    else:
        msg["From"] = EmailConfig.SENDER_EMAIL

    # Create a secure SSL context
    context = ssl.create_default_context()

    try:
        # Connect to the SMTP server (uses SSL on port 465)
        with smtplib.SMTP_SSL(EmailConfig.SMTP_SERVER, EmailConfig.SMTP_PORT, context=context) as server:
            # Log in to the account
            server.login(EmailConfig.SENDER_EMAIL, EmailConfig.PASSWORD)
            # Send the email
            server.send_message(msg)
            return {"message": "Email sent successfully"}
    except smtplib.SMTPAuthenticationError:
        raise ValueError("SMTP Authentication failed. Check your SENDER_EMAIL and PASSWORD (ensure it's an App Password if using services like Gmail).")
    except Exception as e:
        raise ValueError(f"Failed to send email: {e}")


# --- 4. FastAPI Application Setup ---
app = FastAPI(
    title="SMTP Email Service",
    description="A FastAPI endpoint to send emails using Python's smtplib.",
    version="1.0.0"
)

# --- 5. FastAPI Endpoint ---
@app.post("/send-email", tags=["Email"])
async def send_email(request: EmailRequest = Body(...)):
    """
    Endpoint to trigger the email sending process.
    The synchronous function is executed in a background thread to prevent blocking
    the main asynchronous event loop.
    """
    try:
        # Use asyncio.to_thread to run the blocking send_email_sync function
        # This keeps the main FastAPI event loop free to handle other requests
        result = await asyncio.to_thread(
            send_email_sync,
            recipient=request.recipient_email,
            subject=request.subject,
            body=request.body,
            sender_name=request.sender_name
        )
        return result
    except ValueError as e:
        # Catch exceptions raised from the synchronous function and convert to HTTP 500
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        # Catch any unexpected errors
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

# Example usage (run with Uvicorn):
# uvicorn main:app --reload

# Example POST body:
# {
#   "recipient_email": "test@example.com",
#   "subject": "FastAPI Test Email",
#   "body": "This email was sent from a FastAPI endpoint using smtplib.",
#   "sender_name": "API Service"
# }
