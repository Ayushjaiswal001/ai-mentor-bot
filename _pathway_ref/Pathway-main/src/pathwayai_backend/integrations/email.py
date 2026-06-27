import asyncio
import smtplib
from email.message import EmailMessage

from pathwayai_backend.config import Settings
from pathwayai_backend.integrations.base import IntegrationError


class EmailClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send(self, *, subject: str, body: str) -> None:
        if not self.settings.digest_email_enabled:
            raise IntegrationError("SMTP_HOST / DIGEST_EMAIL_TO are not configured")
        sender = self.settings.digest_email_sender
        if not sender:
            raise IntegrationError(
                "DIGEST_EMAIL_FROM or SMTP_USERNAME is required as the sender"
            )
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = sender
        message["To"] = self.settings.digest_email_to
        message.set_content(body)
        try:
            await asyncio.to_thread(self._deliver, message)
        except (smtplib.SMTPException, OSError) as exc:
            raise IntegrationError(f"Email delivery failed: {exc}") from exc

    def _deliver(self, message: EmailMessage) -> None:
        host = self.settings.smtp_host
        port = self.settings.smtp_port
        if port == 465:
            client: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=30)
        else:
            client = smtplib.SMTP(host, port, timeout=30)
        with client:
            if port != 465:
                client.starttls()
            if self.settings.smtp_username and self.settings.smtp_password:
                client.login(
                    self.settings.smtp_username,
                    self.settings.smtp_password.get_secret_value(),
                )
            client.send_message(message)
