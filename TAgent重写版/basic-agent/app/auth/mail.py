"""账号邮件传输。开发测试使用内存信箱，正式部署使用 SMTP。"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage


class MemoryMailer:
    def __init__(self):
        self.outbox: list[dict[str, str]] = []

    def send(self, to: str, subject: str, body: str) -> None:
        self.outbox.append({"to": to, "subject": subject, "body": body})


class SMTPMailer:
    def __init__(self, host: str, port: int, username: str, password: str, sender: str):
        if not all((host, port, username, password, sender)):
            raise ValueError("SMTP configuration is incomplete")
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.sender = sender

    def send(self, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        if self.port == 465:
            with smtplib.SMTP_SSL(self.host, self.port, timeout=10) as smtp:
                smtp.login(self.username, self.password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                smtp.login(self.username, self.password)
                smtp.send_message(message)
