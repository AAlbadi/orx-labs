import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import make_msgid
from datetime import datetime
from sqlalchemy.orm import Session
from backend.app.config import settings
from backend.app.database.schema import Lead, EmailLog

class OutreachSequencer:
    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        
        self.imap_host = settings.IMAP_HOST
        self.imap_port = settings.IMAP_PORT
        self.imap_user = settings.IMAP_USER
        self.imap_password = settings.IMAP_PASSWORD

    def send_email(self, to_email: str, subject: str, body: str, reply_to_msg_id: str = None) -> dict:
        """
        Sends an email via SMTP. Automatically adds custom Message-ID.
        Returns metadata including status and message_id.
        """
        generated_msg_id = make_msgid(domain="orx-outreach.ai")
        
        # If running in mock mode, return mock dispatch metadata
        if "mock" in self.smtp_user or not self.smtp_user:
            print(f"[MOCK SMTP] Dispatching email to {to_email} | Subject: '{subject}' | Msg-ID: {generated_msg_id}")
            return {
                "status": "SENT",
                "message_id": generated_msg_id,
                "sent_at": datetime.utcnow(),
                "error": None
            }
            
        try:
            msg = MIMEMultipart()
            msg['From'] = self.smtp_user
            msg['To'] = to_email
            msg['Subject'] = subject
            msg['Message-ID'] = generated_msg_id
            
            if reply_to_msg_id:
                msg['In-Reply-To'] = reply_to_msg_id
                msg['References'] = reply_to_msg_id

            msg.attach(MIMEText(body, 'plain'))

            server = smtplib.SMTP(self.smtp_host, self.smtp_port)
            server.starttls()
            server.login(self.smtp_user, self.smtp_password)
            server.sendmail(self.smtp_user, to_email, msg.as_string())
            server.quit()
            
            return {
                "status": "SENT",
                "message_id": generated_msg_id,
                "sent_at": datetime.utcnow(),
                "error": None
            }
        except Exception as e:
            print(f"SMTP send failed: {e}")
            return {
                "status": "BOUNCED",
                "message_id": None,
                "sent_at": datetime.utcnow(),
                "error": str(e)
            }

    def check_inbox_and_apply_smart_stop(self, db: Session) -> list[str]:
        """
        Connects via IMAP to check for replies from leads.
        Triggers Smart-Stop rule (marks Lead as REPLIED and stops campaigns).
        Returns list of email addresses that replied.
        """
        replied_emails = []
        
        # In mock mode, we look at the database or simulate replies
        if "mock" in self.imap_user or not self.imap_user:
            # We will simulate reply checks
            print("[MOCK IMAP] Checking inbox for replies...")
            return replied_emails

        try:
            mail = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
            mail.login(self.imap_user, self.imap_password)
            mail.select("inbox")

            # Search for unread messages
            status, messages = mail.search(None, 'UNSEEN')
            if status == "OK" and messages[0]:
                for num in messages[0].split():
                    status, data = mail.fetch(num, '(RFC822)')
                    if status == "OK":
                        raw_email = data[0][1]
                        msg = email.message_from_bytes(raw_email)
                        from_header = msg.get("From", "")
                        
                        # Extract email address
                        email_addr = email.utils.parseaddr(from_header)[1]
                        
                        if email_addr:
                            # Verify if this matches any of our active leads
                            lead = db.query(Lead).filter(
                                Lead.email == email_addr, 
                                Lead.status.in_(["CONTACTED", "DRAFTED"])
                            ).first()
                            
                            if lead:
                                # Apply Smart-Stop: Mark status as REPLIED
                                lead.status = "REPLIED"
                                db.commit()
                                replied_emails.append(email_addr)
                                print(f"[SMART-STOP] Reply detected from {email_addr}. Disabling follow-up sequence.")
                                
            mail.close()
            mail.logout()
        except Exception as e:
            print(f"IMAP check failed: {e}")
            
        return replied_emails

    def simulate_incoming_reply(self, db: Session, email_addr: str) -> bool:
        """Simulates receiving a reply from a lead (useful for manual testing & frontend demo)."""
        lead = db.query(Lead).filter(Lead.email == email_addr).first()
        if lead:
            lead.status = "REPLIED"
            db.commit()
            print(f"[TEST SMART-STOP] Simulated reply from {email_addr}. Lead state updated to REPLIED.")
            return True
        return False

sequencer = OutreachSequencer()
