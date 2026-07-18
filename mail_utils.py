import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Load SMTP configuration variables from environmental settings
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = os.getenv("SMTP_PORT")
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM", "SQL Genie <noreply@sqlgenie.tech>")

def send_event_email(to_email: str, name: str, event_type: str) -> None:
    """
    Dispatches a monospaced brand email notification for signup/login actions.
    If SMTP credentials are not configured, it logs the simulated email body.
    """
    subject = ""
    body_html = ""
    
    if event_type == "signup":
        subject = "[SQL Genie] Account Registration Complete"
        body_html = f"""
        <html>
        <body style="margin: 0; padding: 20px; background-color: #fdfcfc;">
            <div style="font-family: 'Courier New', Courier, monospace; background-color: #fdfcfc; color: #201d1d; border: 1px solid #201d1d; padding: 24px; max-width: 500px; margin: 0 auto;">
                <h2 style="margin-top: 0; font-size: 18px; border-bottom: 1px solid #201d1d; padding-bottom: 10px;">[SQL GENIE PORTAL]</h2>
                <p>Hello <strong>{name}</strong>,</p>
                <p>Your user profile has been successfully registered on the SQL Genie text-to-SQL platform.</p>
                <div style="background-color: #f5f4f4; border: 1px solid #e0dfdf; padding: 12px; margin: 16px 0;">
                    <span style="font-size: 13px;">🔑 <strong>Security Status: Active</strong></span>
                </div>
                <p>You can now save your database connection credentials persistently across workspaces.</p>
                <hr style="border: none; border-top: 1px dashed #201d1d; margin: 20px 0;">
                <p style="font-size: 11px; color: #888; margin-bottom: 0;">This is an automated notification. Please do not reply.</p>
            </div>
        </body>
        </html>
        """
    elif event_type == "login":
        subject = "[SQL Genie] Account Login Alert"
        body_html = f"""
        <html>
        <body style="margin: 0; padding: 20px; background-color: #fdfcfc;">
            <div style="font-family: 'Courier New', Courier, monospace; background-color: #fdfcfc; color: #201d1d; border: 1px solid #201d1d; padding: 24px; max-width: 500px; margin: 0 auto;">
                <h2 style="margin-top: 0; font-size: 18px; border-bottom: 1px solid #201d1d; padding-bottom: 10px;">[SQL GENIE PORTAL]</h2>
                <p>Hello <strong>{name}</strong>,</p>
                <p>Your account was successfully logged in.</p>
                <div style="background-color: #f5f4f4; border: 1px solid #e0dfdf; padding: 12px; margin: 16px 0;">
                    <span style="font-size: 13px;">🛡️ <strong>Notification Alert: Success</strong></span>
                </div>
                <p>If you did not initiate this login session, please secure your cloud profile database password immediately.</p>
                <hr style="border: none; border-top: 1px dashed #201d1d; margin: 20px 0;">
                <p style="font-size: 11px; color: #888; margin-bottom: 0;">This is an automated security notification. Please do not reply.</p>
            </div>
        </body>
        </html>
        """
    else:
        return

    # Check if SMTP details are loaded
    if not SMTP_HOST or not SMTP_USERNAME or not SMTP_PASSWORD:
        print("\n=== [SIMULATED EMAIL DISPATCH] ===")
        print(f"To: {to_email}")
        print(f"Subject: {subject}")
        print(f"Event: {event_type.upper()}")
        print(f"Recipient: {name}")
        print("==================================\n")
        return

    try:
        # Build message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = to_email
        
        # Attach HTML body
        msg.attach(MIMEText(body_html, "html"))
        
        # Connect to server
        port = int(SMTP_PORT) if SMTP_PORT else 587
        server = smtplib.SMTP(SMTP_HOST, port, timeout=10)
        
        server.ehlo()
        server.starttls()  # Secure connection
        server.ehlo()
        
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.sendmail(SMTP_FROM, [to_email], msg.as_string())
        server.quit()
        print(f"Email alert successfully sent to {to_email} for {event_type} event.")
    except Exception as e:
        print(f"Error sending email to {to_email}: {str(e)}")
