# import smtplib
# import ssl
# from email.message import EmailMessage
# import os
# import asyncio
# from typing import Optional

# from fastapi import FastAPI, HTTPException, Body
# from pydantic import BaseModel, EmailStr

# # --- 1. Configuration ---
# # IMPORTANT: Never hardcode credentials in production.
# # Use environment variables for sensitive information.
# class EmailConfig:
#     """Stores configuration for the SMTP server."""
#     # Use environment variables if available, otherwise use placeholders
#     SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
#     SMTP_PORT = int(os.environ.get("SMTP_PORT", 465)) # 465 for SSL, 587 for TLS
#     SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "velpurianand8005@gmail.com")
#     PASSWORD = os.environ.get("SENDER_PASSWORD")

#     if SENDER_EMAIL == "your_sender_email@example.com" or PASSWORD == "your_app_password":
#         print("Warning: Using placeholder email/password. Please set environment variables (SMTP_SERVER, SMTP_PORT, SENDER_EMAIL, SENDER_PASSWORD) or update the EmailConfig class.")

# # --- 2. Pydantic Model for Request Body ---
# class EmailRequest(BaseModel):
#     """Defines the structure for the incoming email request."""
#     recipient_email: EmailStr
#     subject: str
#     body: str
#     sender_name: Optional[str] = None # Optional name to appear as the sender

# # --- 3. Core Email Sending Logic (Synchronous) ---
# def send_email_sync(recipient: str, subject: str, body: str, sender_name: Optional[str]):
#     """
#     Sends the email using smtplib. This is a synchronous (blocking) operation.
#     It is designed to run in a separate thread.
#     """
#     msg = EmailMessage()
#     msg.set_content(body)
#     msg["Subject"] = subject
#     msg["To"] = recipient

#     # Set the 'From' field. Use the provided sender_name if available.
#     if sender_name:
#         msg["From"] = f"{sender_name} <{EmailConfig.SENDER_EMAIL}>"
#     else:
#         msg["From"] = EmailConfig.SENDER_EMAIL

#     # Create a secure SSL context
#     context = ssl.create_default_context()

#     try:
#         # Connect to the SMTP server (uses SSL on port 465)
#         with smtplib.SMTP_SSL(EmailConfig.SMTP_SERVER, EmailConfig.SMTP_PORT, context=context) as server:
#             # Log in to the account
#             server.login(EmailConfig.SENDER_EMAIL, EmailConfig.PASSWORD)
#             # Send the email
#             server.send_message(msg)
#             return {"message": "Email sent successfully"}
#     except smtplib.SMTPAuthenticationError:
#         raise ValueError("SMTP Authentication failed. Check your SENDER_EMAIL and PASSWORD (ensure it's an App Password if using services like Gmail).")
#     except Exception as e:
#         raise ValueError(f"Failed to send email: {e}")


# # --- 4. FastAPI Application Setup ---
# app = FastAPI(
#     title="SMTP Email Service",
#     description="A FastAPI endpoint to send emails using Python's smtplib.",
#     version="1.0.0"
# )

# # --- 5. FastAPI Endpoint ---
# @app.post("/send-email", tags=["Email"])
# async def send_email(request: EmailRequest = Body(...)):
#     """
#     Endpoint to trigger the email sending process.
#     The synchronous function is executed in a background thread to prevent blocking
#     the main asynchronous event loop.
#     """
#     try:
#         # Use asyncio.to_thread to run the blocking send_email_sync function
#         # This keeps the main FastAPI event loop free to handle other requests
#         result = await asyncio.to_thread(
#             send_email_sync,
#             recipient=request.recipient_email,
#             subject=request.subject,
#             body=request.body,
#             sender_name=request.sender_name
#         )
#         return result
#     except ValueError as e:
#         # Catch exceptions raised from the synchronous function and convert to HTTP 500
#         raise HTTPException(status_code=500, detail=str(e))
#     except Exception as e:
#         # Catch any unexpected errors
#         raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

# # Example usage (run with Uvicorn):
# # uvicorn main:app --reload

# # Example POST body:
# # {
# #   "recipient_email": "test@example.com",
# #   "subject": "FastAPI Test Email",
# #   "body": "This email was sent from a FastAPI endpoint using smtplib.",
# #   "sender_name": "API Service"
# # }



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
from pydantic import BaseModel, EmailStr

# --- 1. Configuration (REVERTED TO SMTP) ---
class Settings:
    """Stores configuration for the SMTP server."""
    # Use environment variables if available, otherwise use placeholders
    SMTP_SERVER: str = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    # 465 for SSL, 587 for TLS
    SMTP_PORT: int = int(os.environ.get("SMTP_PORT", 465)) 
    SENDER_EMAIL: EmailStr = os.environ.get("SENDER_EMAIL", "velpurianand8005@gmail.com")
    # For security, use an App Password if using services like Gmail
    PASSWORD: str = os.environ.get("SENDER_PASSWORD")

    if SENDER_EMAIL == "your_sender_email@example.com" or PASSWORD == "your_app_password":
        print("Warning: Using placeholder email/password. Please set environment variables for production use.")

settings = Settings()

# --- 2. Logging Setup ---
logger = logging.getLogger('email_service')
if not logger.handlers:
    # Basic console logging setup
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# --- 3. Pydantic Model for Request Body ---
class OtpEmailRequest(BaseModel):
    """Defines the structure for the OTP email request."""
    recipient_email: EmailStr
    otp: str

# --- 4. Core Email Sending Logic (REPLACED with SMTP) ---

def send_email_sync(to_email: str, subject: str, html_body: str, otp: str) -> bool:
    """
    Sends the email using smtplib, supporting HTML content with a plain text fallback.
    This function is synchronous and must be run in a thread pool.
    """
    sender_email = settings.SENDER_EMAIL
    
    # 1. Create the plain text fallback content
    plain_body = (
        f"Subject: {subject}\n\n"
        f"Your One-Time Password (OTP) for your request is: {otp}\n"
        f"This code will expire in 10 minutes.\n"
        "Please view in an HTML-enabled client for the best format."
    )
    
    msg = EmailMessage()
    msg.set_content(plain_body) # Set the plain text content first
    msg.add_alternative(html_body, subtype="html") # Add the HTML alternative

    msg["Subject"] = subject
    msg["To"] = to_email
    msg["From"] = sender_email

    # Create a secure SSL context
    context = ssl.create_default_context()

    try:
        logger.info(f"Attempting to send email to {to_email} via SMTP ({settings.SMTP_SERVER}:{settings.SMTP_PORT})")
        
        # Connect to the SMTP server (uses SSL for port 465 for Gmail)
        with smtplib.SMTP_SSL(settings.SMTP_SERVER, settings.SMTP_PORT, context=context) as server:
            server.login(sender_email, settings.PASSWORD)
            server.send_message(msg)
            logger.info(f"Email sent successfully to {to_email} via SMTP.")
            return True
            
    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP Authentication failed. Check SENDER_EMAIL/SENDER_PASSWORD.")
        # Raise an exception instead of returning False so FastAPI handles the error
        raise ValueError("SMTP Authentication failed. Check credentials.")
    except Exception as e:
        logger.error(f"Failed to send email to {to_email} via SMTP: {e}")
        # Re-raise as ValueError to be caught by the FastAPI endpoint handler
        raise ValueError(f"SMTP Error: {e}")

# This is the specialized function that defines the content
def send_otp_email(to_email: str, otp: str) -> bool:
    """
    Sends a pre-formatted OTP email to a user using the underlying email service.
    """
    subject = "Your Hostel Management OTP Code"
    body_html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6;">
        <div style="max-width: 600px; margin: 20px auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
          <h2 style="color: #333;">Hostel Management System</h2>
          <p>Dear User,</p>
          <p>Your One-Time Password (OTP) for your request is:</p>
          <p style="text-align: center; font-size: 24px; font-weight: bold; color: #333; background-color: #f2f2f2; padding: 15px; border-radius: 5px; letter-spacing: 2px;">
            {otp}
          </p>
          <p>This code will expire in 10 minutes.</p>
          <p>If you did not request this OTP, please ignore this email or contact support if you have concerns.</p>
          <br>
          <p>Thank you,</p>
          <p><strong>The Sanskriti School of Engineering Hostel Team</strong></p>
        </div>
      </body>
    </html>
    """
    # Call the new SMTP synchronous function, passing the OTP for plaintext generation
    return send_email_sync(to_email, subject, body_html, otp)


# --- 5. FastAPI Application Setup ---
app = FastAPI(
    title="SMTP Email Service (OTP)",
    description="A FastAPI endpoint to send OTP emails using standard Python smtplib (SMTP).",
    version="2.0.1"
)

# --- 6. FastAPI Endpoint ---
@app.post("/send-otp", tags=["Email"])
async def send_otp(request: OtpEmailRequest = Body(...)):
    """
    Endpoint to trigger the sending of a formatted OTP email via SMTP.
    The synchronous SMTP call is executed in a background thread.
    """
    try:
        # Run the synchronous function in a separate thread
        success = await asyncio.to_thread(
            send_otp_email,
            to_email=request.recipient_email,
            otp=request.otp
        )

        if success:
            return {"message": f"OTP email successfully sent to {request.recipient_email} via SMTP."}
        else:
            raise HTTPException(status_code=500, detail="SMTP server reported an unknown issue during email delivery.")

    except ValueError as e:
        # Catch configuration or SMTP errors
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        # Catch unexpected errors
        logger.error(f"Endpoint failure: {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred.")
