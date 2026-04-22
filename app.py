import logging
import asyncio
import os
from typing import Optional

# --- Libraries for SMTP ---
import smtplib
import ssl
from email.message import EmailMessage

# --- External Libraries ---
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel

# --- 1. Configuration ---
class Settings:
    """Stores configuration for the SMTP server."""
    # Use port 587 for TLS (STARTTLS) which is more reliable than 465 for Gmail
    SMTP_SERVER: str = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT: int = int(os.environ.get("SMTP_PORT", 587)) 
    SENDER_EMAIL: str = os.environ.get("SENDER_EMAIL", "satyasaidistrictpolice@gmail.com")
    PASSWORD: str = os.environ.get("SENDER_PASSWORD")

settings = Settings()

# --- 2. Logging Setup ---
logger = logging.getLogger('email_service')
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# --- 3. Pydantic Model (Uses str instead of EmailStr to avoid import errors) ---
class OtpEmailRequest(BaseModel):
    recipient_email: str
    otp: str

# --- 4. Core Email Sending Logic ---

def send_email_sync(to_email: str, subject: str, html_body: str, otp: str) -> bool:
    sender_email = settings.SENDER_EMAIL
    
    plain_body = (
        f"Your One-Time Password (OTP) is: {otp}\n"
        f"This code will expire in 10 minutes."
    )
    
    msg = EmailMessage()
    msg.set_content(plain_body)
    msg.add_alternative(html_body, subtype="html")

    msg["Subject"] = subject
    msg["To"] = to_email
    msg["From"] = sender_email

    context = ssl.create_default_context()

    try:
        logger.info(f"Connecting to {settings.SMTP_SERVER}:{settings.SMTP_PORT}...")
        
        # Use standard SMTP + starttls for port 587
        with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT) as server:
            server.starttls(context=context) # Secure the connection
            server.login(sender_email, settings.PASSWORD)
            server.send_message(msg)
            logger.info(f"Email sent successfully to {to_email}.")
            return True
            
    except Exception as e:
        logger.error(f"SMTP Error: {e}")
        raise ValueError(f"SMTP Error: {e}")

def send_otp_email(to_email: str, otp: str) -> bool:
    subject = "Your Hostel Management OTP Code"
    body_html = f"""
    <html>
      <body style="font-family: Arial, sans-serif;">
        <div style="max-width: 600px; margin: 20px auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
          <h2>Hostel Management System</h2>
          <p>Your One-Time Password (OTP) is:</p>
          <h1 style="background: #f2f2f2; padding: 15px; text-align: center;">{otp}</h1>
          <p>This code will expire in 10 minutes.</p>
        </div>
      </body>
    </html>
    """
    return send_email_sync(to_email, subject, body_html, otp)

# --- 5. FastAPI App ---
app = FastAPI(title="SMTP Email Service")

@app.post("/send-otp")
async def send_otp(request: OtpEmailRequest = Body(...)):
    try:
        success = await asyncio.to_thread(
            send_otp_email,
            to_email=request.recipient_email,
            otp=request.otp
        )
        return {"message": "Email sent successfully"}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
