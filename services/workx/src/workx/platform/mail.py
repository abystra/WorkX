"""Outgoing email. Selected by ``WORKX_MAIL_URL``: ``smtp://…`` (production), ``file:<dir>`` (development and
tests, one .eml per message) or ``log``. Real SMTP delivery is verified only where an SMTP server exists."""

from __future__ import annotations

import logging
import smtplib
import uuid
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Protocol
from urllib.parse import unquote, urlparse

log = logging.getLogger("workx.mail")


@dataclass(frozen=True)
class Mail:
    to: str
    subject: str
    text: str


class Mailer(Protocol):
    def send(self, mail: Mail) -> None: ...


def _message(sender: str, mail: Mail) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = mail.to
    message["Subject"] = mail.subject
    message.set_content(mail.text)
    return message


@dataclass
class FileMailer:
    directory: Path
    sender: str

    def send(self, mail: Mail) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / f"{uuid.uuid4().hex}.eml").write_bytes(bytes(_message(self.sender, mail)))


@dataclass
class SmtpMailer:
    host: str
    port: int
    username: str
    password: str
    sender: str
    starttls: bool = True

    def send(self, mail: Mail) -> None:
        with smtplib.SMTP(self.host, self.port, timeout=20) as smtp:
            if self.starttls:
                smtp.starttls()
            if self.username:
                smtp.login(self.username, self.password)
            smtp.send_message(_message(self.sender, mail))


@dataclass
class LogMailer:
    sender: str

    def send(self, mail: Mail) -> None:
        # Never logs the body: invitation links are bearer tokens.
        log.info("mail not sent (WORKX_MAIL_URL=log)", extra={"to": mail.to, "subject": mail.subject})


def from_url(url: str, sender: str) -> Mailer:
    if url.startswith("file:"):
        return FileMailer(Path(url.removeprefix("file:")), sender)
    if url.startswith(("smtp://", "smtps://")):
        parsed = urlparse(url)
        return SmtpMailer(
            parsed.hostname or "localhost",
            parsed.port or 587,
            unquote(parsed.username or ""),
            unquote(parsed.password or ""),
            sender,
        )
    return LogMailer(sender)
