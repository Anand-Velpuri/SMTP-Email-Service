import asyncio
import logging
import os
import ssl
import smtplib
import mimetypes
import re
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from typing import List

from fastapi import (
    FastAPI,
    HTTPException,
    UploadFile,
    File,
    Form,
    Request,
    Body,
)
from fastapi.responses import HTMLResponse
from pydantic import BaseModel


# ============================================================
# CONFIGURATION
# ============================================================

class Settings:
    SMTP_SERVER: str = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT: int = int(os.environ.get("SMTP_PORT", "587"))

    SENDER_EMAIL: str = os.environ.get(
        "SENDER_EMAIL",
        "satyasaidistrictpolice@gmail.com"
    )

    PASSWORD: str | None = os.environ.get("SENDER_PASSWORD")

    SENDER_NAME: str = os.environ.get(
        "SENDER_NAME",
        "Hostel Management System"
    )


settings = Settings()


# ============================================================
# LOGGING
# ============================================================

logger = logging.getLogger("email_service")

if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

logger.setLevel(logging.INFO)


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="Bulk Email Service",
    version="2.0.0"
)


# ============================================================
# MODELS
# ============================================================

class OtpEmailRequest(BaseModel):
    recipient_email: str
    otp: str


class BulkEmailRequest(BaseModel):
    recipients: List[str]
    subject: str
    html_body: str
    plain_body: str = ""


# ============================================================
# EMAIL VALIDATION
# ============================================================

EMAIL_REGEX = re.compile(
    r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
)


def normalize_recipients(raw_recipients: str) -> List[str]:
    """
    Accept:

        a@gmail.com
        b@gmail.com

    or:

        a@gmail.com, b@gmail.com

    or:

        a@gmail.com
        b@gmail.com
    """

    recipients = re.split(r"[\s,;]+", raw_recipients.strip())

    cleaned = []

    for email in recipients:
        email = email.strip()

        if not email:
            continue

        if EMAIL_REGEX.match(email):
            if email.lower() not in [x.lower() for x in cleaned]:
                cleaned.append(email)

    return cleaned


# ============================================================
# SMTP CONNECTION
# ============================================================

def create_smtp_connection():
    if not settings.PASSWORD:
        raise ValueError(
            "SENDER_PASSWORD environment variable is not configured."
        )

    context = ssl.create_default_context()

    logger.info(
        "Connecting to %s:%s",
        settings.SMTP_SERVER,
        settings.SMTP_PORT
    )

    server = smtplib.SMTP(
        settings.SMTP_SERVER,
        settings.SMTP_PORT,
        timeout=60
    )

    server.ehlo()

    if settings.SMTP_PORT == 587:
        server.starttls(context=context)
        server.ehlo()

    server.login(
        settings.SENDER_EMAIL,
        settings.PASSWORD
    )

    logger.info("SMTP authentication successful.")

    return server


# ============================================================
# EMAIL MESSAGE
# ============================================================

def create_email_message(
    to_email: str,
    subject: str,
    html_body: str,
    plain_body: str,
    attachments: list[dict]
) -> EmailMessage:

    msg = EmailMessage()

    if plain_body.strip():
        msg.set_content(plain_body)
    else:
        msg.set_content(
            "This email requires an HTML-compatible email client."
        )

    msg.add_alternative(
        html_body,
        subtype="html"
    )

    msg["Subject"] = subject

    msg["From"] = formataddr(
        (
            settings.SENDER_NAME,
            settings.SENDER_EMAIL
        )
    )

    # IMPORTANT:
    # Individual To header means recipients cannot see each other.
    msg["To"] = to_email

    # Attach files
    for attachment in attachments:

        filename = attachment["filename"]
        content = attachment["content"]

        content_type, encoding = mimetypes.guess_type(filename)

        if content_type is None:
            content_type = "application/octet-stream"

        maintype, subtype = content_type.split("/", 1)

        msg.add_attachment(
            content,
            maintype=maintype,
            subtype=subtype,
            filename=filename
        )

    return msg


# ============================================================
# BULK SEND
# ============================================================

def send_bulk_email_sync(
    recipients: List[str],
    subject: str,
    html_body: str,
    plain_body: str,
    attachments: list[dict]
):

    results = []

    server = None

    try:

        server = create_smtp_connection()

        for index, recipient in enumerate(recipients, start=1):

            try:

                logger.info(
                    "Sending %s/%s -> %s",
                    index,
                    len(recipients),
                    recipient
                )

                msg = create_email_message(
                    to_email=recipient,
                    subject=subject,
                    html_body=html_body,
                    plain_body=plain_body,
                    attachments=attachments
                )

                server.send_message(msg)

                results.append({
                    "email": recipient,
                    "success": True,
                    "error": None
                })

                logger.info(
                    "Successfully sent -> %s",
                    recipient
                )

            except Exception as e:

                logger.error(
                    "Failed -> %s : %s",
                    recipient,
                    e
                )

                results.append({
                    "email": recipient,
                    "success": False,
                    "error": str(e)
                })

        return results

    finally:

        if server:

            try:
                server.quit()
            except Exception:
                pass


# ============================================================
# BULK API
# ============================================================

@app.post("/send-bulk")
async def send_bulk(
    recipients: str = Form(...),
    subject: str = Form(...),
    html_body: str = Form(...),
    plain_body: str = Form(""),
    attachments: List[UploadFile] = File(default=[])
):

    recipient_list = normalize_recipients(recipients)

    if not recipient_list:
        raise HTTPException(
            status_code=400,
            detail="No valid email addresses were provided."
        )

    if not subject.strip():
        raise HTTPException(
            status_code=400,
            detail="Subject is required."
        )

    if not html_body.strip():
        raise HTTPException(
            status_code=400,
            detail="Email body is required."
        )

    # --------------------------------------------------------
    # Read attachments into memory
    # --------------------------------------------------------

    attachment_data = []

    for attachment in attachments:

        if not attachment.filename:
            continue

        content = await attachment.read()

        attachment_data.append({
            "filename": Path(attachment.filename).name,
            "content": content
        })

    logger.info(
        "Bulk email started: %s recipients, %s attachments",
        len(recipient_list),
        len(attachment_data)
    )

    # --------------------------------------------------------
    # Run SMTP work outside async event loop
    # --------------------------------------------------------

    results = await asyncio.to_thread(
        send_bulk_email_sync,
        recipient_list,
        subject,
        html_body,
        plain_body,
        attachment_data
    )

    successful = sum(
        1 for result in results
        if result["success"]
    )

    failed = len(results) - successful

    return {
        "message": "Bulk email completed.",
        "total": len(results),
        "successful": successful,
        "failed": failed,
        "results": results
    }


# ============================================================
# EXISTING OTP SUPPORT
# ============================================================

def send_otp_email_sync(
    to_email: str,
    otp: str
) -> bool:

    subject = "Your Hostel Management OTP Code"

    plain_body = (
        f"Your One-Time Password (OTP) is: {otp}\n\n"
        "This code will expire in 10 minutes."
    )

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <body style="
        font-family: Arial, sans-serif;
        background: #f5f5f5;
        padding: 30px;
    ">

        <div style="
            max-width: 600px;
            margin: auto;
            background: white;
            padding: 30px;
            border-radius: 12px;
            border: 1px solid #ddd;
        ">

            <h2>Hostel Management System</h2>

            <p>Your One-Time Password (OTP) is:</p>

            <div style="
                font-size: 32px;
                font-weight: bold;
                letter-spacing: 8px;
                text-align: center;
                background: #f2f2f2;
                padding: 20px;
                border-radius: 8px;
            ">
                {otp}
            </div>

            <p>
                This code will expire in 10 minutes.
            </p>

        </div>

    </body>
    </html>
    """

    results = send_bulk_email_sync(
        recipients=[to_email],
        subject=subject,
        html_body=html_body,
        plain_body=plain_body,
        attachments=[]
    )

    return results[0]["success"]


@app.post("/send-otp")
async def send_otp(
    request: OtpEmailRequest = Body(...)
):

    try:

        success = await asyncio.to_thread(
            send_otp_email_sync,
            request.recipient_email,
            request.otp
        )

        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to send OTP."
            )

        return {
            "message": "Email sent successfully"
        }

    except ValueError as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    except HTTPException:
        raise

    except Exception as e:

        logger.exception("OTP sending failed.")

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health():

    return {
        "status": "ok"
    }


# ============================================================
# WEB UI
# ============================================================

HTML_PAGE = r"""
<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>Bulk Mailer</title>

<style>

* {
    box-sizing: border-box;
}

:root {
    color-scheme: light dark;

    --bg: #f5f7fb;
    --card: #ffffff;
    --text: #111827;
    --muted: #6b7280;
    --border: #e5e7eb;
    --input: #ffffff;
    --primary: #2563eb;
    --primary-hover: #1d4ed8;
    --danger: #dc2626;
    --success: #16a34a;
}

@media (prefers-color-scheme: dark) {

    :root {
        --bg: #0b0f19;
        --card: #111827;
        --text: #f9fafb;
        --muted: #9ca3af;
        --border: #263244;
        --input: #0f172a;
        --primary: #3b82f6;
        --primary-hover: #60a5fa;
    }
}

body {

    margin: 0;

    min-height: 100vh;

    background: var(--bg);

    color: var(--text);

    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        Roboto,
        Arial,
        sans-serif;

    padding: 40px 20px;
}

.container {

    width: 100%;

    max-width: 900px;

    margin: auto;
}

.header {

    margin-bottom: 28px;
}

.header h1 {

    margin: 0;

    font-size: 32px;

    font-weight: 700;
}

.header p {

    color: var(--muted);

    margin-top: 8px;

    font-size: 15px;
}

.card {

    background: var(--card);

    border: 1px solid var(--border);

    border-radius: 16px;

    padding: 28px;

    box-shadow:
        0 10px 30px rgba(0,0,0,0.08);
}

.field {

    margin-bottom: 22px;
}

label {

    display: block;

    margin-bottom: 8px;

    font-weight: 600;

    font-size: 14px;
}

input,
textarea {

    width: 100%;

    background: var(--input);

    color: var(--text);

    border: 1px solid var(--border);

    border-radius: 9px;

    padding: 12px 14px;

    font-family: inherit;

    font-size: 14px;

    outline: none;

    transition: 0.2s;
}

input:focus,
textarea:focus {

    border-color: var(--primary);

    box-shadow:
        0 0 0 3px rgba(37,99,235,0.15);
}

textarea {

    resize: vertical;

    min-height: 110px;
}

#htmlBody {

    min-height: 220px;

    font-family:
        ui-monospace,
        SFMono-Regular,
        Menlo,
        Monaco,
        Consolas,
        monospace;
}

.help {

    margin-top: 6px;

    font-size: 12px;

    color: var(--muted);
}

.drop-zone {

    border: 2px dashed var(--border);

    border-radius: 12px;

    padding: 28px;

    text-align: center;

    cursor: pointer;

    transition: 0.2s;
}

.drop-zone:hover,
.drop-zone.dragging {

    border-color: var(--primary);

    background: rgba(37,99,235,0.05);
}

.drop-zone strong {

    display: block;

    margin-bottom: 6px;
}

.drop-zone span {

    color: var(--muted);

    font-size: 13px;
}

#fileInput {

    display: none;
}

.file-list {

    margin-top: 12px;

    display: flex;

    flex-direction: column;

    gap: 8px;
}

.file-item {

    display: flex;

    align-items: center;

    justify-content: space-between;

    padding: 10px 12px;

    border: 1px solid var(--border);

    border-radius: 8px;

    font-size: 13px;
}

.file-name {

    overflow: hidden;

    text-overflow: ellipsis;

    white-space: nowrap;
}

.remove-file {

    border: none;

    background: transparent;

    color: var(--danger);

    cursor: pointer;

    font-weight: 600;
}

.actions {

    display: flex;

    align-items: center;

    gap: 14px;

    margin-top: 26px;
}

button {

    border: none;

    border-radius: 9px;

    padding: 12px 20px;

    font-weight: 600;

    cursor: pointer;
}

.send-button {

    background: var(--primary);

    color: white;

    flex: 1;
}

.send-button:hover {

    background: var(--primary-hover);
}

.send-button:disabled {

    opacity: 0.6;

    cursor: not-allowed;
}

.clear-button {

    background: transparent;

    border: 1px solid var(--border);

    color: var(--text);
}

.status {

    display: none;

    margin-top: 24px;

    padding: 16px;

    border-radius: 10px;

    border: 1px solid var(--border);

    font-size: 14px;
}

.status.visible {

    display: block;
}

.status.success {

    border-color: rgba(22,163,74,0.4);

    background: rgba(22,163,74,0.08);
}

.status.error {

    border-color: rgba(220,38,38,0.4);

    background: rgba(220,38,38,0.08);
}

.results {

    margin-top: 15px;

    display: flex;

    flex-direction: column;

    gap: 6px;

    max-height: 300px;

    overflow-y: auto;
}

.result-row {

    display: flex;

    justify-content: space-between;

    padding: 8px 10px;

    border-radius: 7px;

    background: rgba(127,127,127,0.08);

    font-size: 13px;
}

.success-text {

    color: var(--success);
}

.failed-text {

    color: var(--danger);
}

.counter {

    float: right;

    color: var(--muted);

    font-weight: 400;
}

</style>

</head>

<body>

<div class="container">

    <div class="header">

        <h1>Bulk Mailer</h1>

        <p>
            Send personalized bulk emails with multiple attachments.
        </p>

    </div>

    <div class="card">

        <form id="emailForm">

            <div class="field">

                <label>
                    Recipients
                    <span class="counter" id="recipientCount">
                        0 recipients
                    </span>
                </label>

                <textarea
                    id="recipients"
                    name="recipients"
                    placeholder="person1@example.com
person2@example.com
person3@example.com"
                    required
                ></textarea>

                <div class="help">
                    Separate email addresses with commas, spaces,
                    semicolons, or new lines.
                </div>

            </div>


            <div class="field">

                <label for="subject">
                    Subject
                </label>

                <input
                    id="subject"
                    name="subject"
                    type="text"
                    placeholder="Enter email subject"
                    required
                >

            </div>


            <div class="field">

                <label for="plainBody">
                    Plain-text message
                </label>

                <textarea
                    id="plainBody"
                    name="plain_body"
                    placeholder="Enter the plain-text version of your message..."
                ></textarea>

            </div>


            <div class="field">

                <label for="htmlBody">
                    HTML message
                </label>

                <textarea
                    id="htmlBody"
                    name="html_body"
                    placeholder="<h2>Hello!</h2>
<p>Your message goes here.</p>"
                    required
                ></textarea>

                <div class="help">
                    You can use HTML formatting here.
                </div>

            </div>


            <div class="field">

                <label>
                    Attachments
                </label>

                <div
                    class="drop-zone"
                    id="dropZone"
                >

                    <strong>
                        Drop files here
                    </strong>

                    <span>
                        or click to choose multiple files
                    </span>

                    <input
                        type="file"
                        id="fileInput"
                        multiple
                    >

                </div>

                <div
                    class="file-list"
                    id="fileList"
                ></div>

            </div>


            <div class="actions">

                <button
                    type="button"
                    class="clear-button"
                    id="clearButton"
                >
                    Clear
                </button>

                <button
                    type="submit"
                    class="send-button"
                    id="sendButton"
                >
                    Send to All
                </button>

            </div>

        </form>


        <div
            class="status"
            id="status"
        ></div>

    </div>

</div>


<script>

const form = document.getElementById("emailForm");

const recipientsInput =
    document.getElementById("recipients");

const recipientCount =
    document.getElementById("recipientCount");

const fileInput =
    document.getElementById("fileInput");

const dropZone =
    document.getElementById("dropZone");

const fileList =
    document.getElementById("fileList");

const statusBox =
    document.getElementById("status");

const sendButton =
    document.getElementById("sendButton");

const clearButton =
    document.getElementById("clearButton");


let selectedFiles = [];


function parseRecipients(value) {

    return value
        .split(/[\s,;]+/)
        .map(x => x.trim())
        .filter(Boolean);

}


function updateRecipientCount() {

    const recipients =
        parseRecipients(recipientsInput.value);

    recipientCount.textContent =
        `${recipients.length} recipient${recipients.length === 1 ? "" : "s"}`;
}


recipientsInput.addEventListener(
    "input",
    updateRecipientCount
);


function addFiles(files) {

    for (const file of files) {

        const exists = selectedFiles.some(
            existing =>
                existing.name === file.name &&
                existing.size === file.size
        );

        if (!exists) {
            selectedFiles.push(file);
        }

    }

    renderFiles();

}


function renderFiles() {

    fileList.innerHTML = "";

    selectedFiles.forEach(
        (file, index) => {

            const item =
                document.createElement("div");

            item.className = "file-item";

            const name =
                document.createElement("span");

            name.className = "file-name";

            const size =
                (file.size / 1024 / 1024).toFixed(2);

            name.textContent =
                `${file.name} (${size} MB)`;

            const remove =
                document.createElement("button");

            remove.className =
                "remove-file";

            remove.type =
                "button";

            remove.textContent =
                "Remove";

            remove.onclick =
                () => {

                    selectedFiles.splice(index, 1);

                    renderFiles();

                };

            item.appendChild(name);

            item.appendChild(remove);

            fileList.appendChild(item);

        }
    );

}


dropZone.addEventListener(
    "click",
    () => fileInput.click()
);


fileInput.addEventListener(
    "change",
    event => {

        addFiles(event.target.files);

        fileInput.value = "";

    }
);


dropZone.addEventListener(
    "dragover",
    event => {

        event.preventDefault();

        dropZone.classList.add("dragging");

    }
);


dropZone.addEventListener(
    "dragleave",
    () => {

        dropZone.classList.remove("dragging");

    }
);


dropZone.addEventListener(
    "drop",
    event => {

        event.preventDefault();

        dropZone.classList.remove("dragging");

        addFiles(event.dataTransfer.files);

    }
);


function showStatus(
    message,
    type,
    results = []
) {

    statusBox.className =
        `status visible ${type}`;

    statusBox.innerHTML =
        `<strong>${message}</strong>`;

    if (results.length) {

        const resultContainer =
            document.createElement("div");

        resultContainer.className =
            "results";

        results.forEach(result => {

            const row =
                document.createElement("div");

            row.className =
                "result-row";

            const email =
                document.createElement("span");

            email.textContent =
                result.email;

            const state =
                document.createElement("span");

            if (result.success) {

                state.textContent =
                    "Sent";

                state.className =
                    "success-text";

            } else {

                state.textContent =
                    result.error || "Failed";

                state.className =
                    "failed-text";

            }

            row.appendChild(email);

            row.appendChild(state);

            resultContainer.appendChild(row);

        });

        statusBox.appendChild(resultContainer);

    }

}


form.addEventListener(
    "submit",
    async event => {

        event.preventDefault();

        const recipients =
            parseRecipients(
                recipientsInput.value
            );

        if (!recipients.length) {

            showStatus(
                "Please enter at least one valid recipient.",
                "error"
            );

            return;

        }

        const formData =
            new FormData();

        formData.append(
            "recipients",
            recipients.join(",")
        );

        formData.append(
            "subject",
            document.getElementById("subject").value
        );

        formData.append(
            "plain_body",
            document.getElementById("plainBody").value
        );

        formData.append(
            "html_body",
            document.getElementById("htmlBody").value
        );


        selectedFiles.forEach(
            file => {

                formData.append(
                    "attachments",
                    file,
                    file.name
                );

            }
        );


        sendButton.disabled = true;

        sendButton.textContent =
            "Sending...";

        statusBox.className =
            "status";

        try {

            const response =
                await fetch(
                    "/send-bulk",
                    {
                        method: "POST",
                        body: formData
                    }
                );

            const data =
                await response.json();


            if (!response.ok) {

                throw new Error(
                    data.detail ||
                    "Failed to send emails."
                );

            }


            showStatus(
                `Completed: ${data.successful} sent, ${data.failed} failed.`,
                data.failed === 0
                    ? "success"
                    : "error",
                data.results
            );

        } catch (error) {

            showStatus(
                error.message ||
                "An unexpected error occurred.",
                "error"
            );

        } finally {

            sendButton.disabled = false;

            sendButton.textContent =
                "Send to All";

        }

    }
);


clearButton.addEventListener(
    "click",
    () => {

        form.reset();

        selectedFiles = [];

        renderFiles();

        updateRecipientCount();

        statusBox.className =
            "status";

        statusBox.innerHTML = "";

    }
);


updateRecipientCount();

</script>

</body>

</html>
"""


# ============================================================
# UI ROUTE
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def home():

    return HTML_PAGE


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=7860
    )
