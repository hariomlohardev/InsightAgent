import os
import smtplib
import io
from email.message import EmailMessage
from typing import Optional, List

def send_email(to: str, subject: str, body: str, attachments: Optional[List[tuple]] = None) -> dict:
    """
    Send email via SMTP. Env: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM
    attachments: [(filename, bytes, mimetype)]
    Returns {status, detail}
    In tests, SMTP is mocked; if env missing, returns simulated success for OSS demo.
    """
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    pwd = os.getenv("SMTP_PASS") or os.getenv("SMTP_PASSWORD")
    from_addr = os.getenv("SMTP_FROM") or user or "insightagent@localhost"

    if not host:
        # No SMTP configured — simulate (for OSS demo / tests that mock)
        # check if we are in a test that expects mock to be called; we still return simulated
        return {"status": "simulated", "to": to, "subject": subject, "detail": "SMTP_HOST not set — simulated send (configure .env to actually send)"}
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    # Attachments
    if attachments:
        for fname, data, mtype in attachments:
            main, sub = (mtype.split("/") if "/" in mtype else ("application","octet-stream"))
            msg.add_attachment(data, maintype=main, subtype=sub, filename=fname)

    try:
        # Use SMTP with STARTTLS if port 587, else SSL if 465
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=10) as s:
                if user and pwd:
                    s.login(user, pwd)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=10) as s:
                s.ehlo()
                try:
                    s.starttls()
                except:
                    pass
                if user and pwd:
                    s.login(user, pwd)
                s.send_message(msg)
        return {"status": "sent", "to": to, "subject": subject}
    except Exception as e:
        return {"status": "error", "to": to, "error": str(e)[:300]}

def send_slack(webhook_url: str, text: str, file_bytes: Optional[bytes] = None, filename: str = "chart.png") -> dict:
    """Send Slack via incoming webhook URL. If file_bytes provided, we try files.upload via bot token else just text+link."""
    if not webhook_url:
        return {"status": "simulated", "detail": "SLACK_WEBHOOK_URL not set — simulated (provide webhook in schedule)"}
    # Incoming webhook simple path
    if "hooks.slack.com" in webhook_url or webhook_url.startswith("http"):
        try:
            import httpx
            # If file_bytes, we still send text first; file upload needs bot token not webhook
            # So just send text
            payload = {"text": text}
            # httpx handles json
            r = httpx.post(webhook_url, json=payload, timeout=10)
            if r.status_code in (200, 201, 204):
                return {"status": "sent", "detail": text[:80]}
            else:
                return {"status": "error", "detail": f"Slack webhook {r.status_code}: {r.text[:200]}"}
        except Exception as e:
            # Fallback to requests if httpx fails
            try:
                import requests
                r = requests.post(webhook_url, json={"text": text}, timeout=10)
                if r.status_code in (200,201,204):
                    return {"status": "sent"}
                return {"status": "error", "detail": r.text[:200]}
            except Exception as e2:
                return {"status": "error", "detail": str(e2)[:200]}
    return {"status": "error", "detail": "Unsupported webhook URL"}

def send_slack_via_bot(token: str, channel: str, text: str, file_bytes: Optional[bytes] = None) -> dict:
    """If bot token provided, use chat.postMessage/files.upload"""
    import httpx
    headers = {"Authorization": f"Bearer {token}"}
    try:
        # Post message
        r = httpx.post("https://slack.com/api/chat.postMessage", json={"channel": channel, "text": text}, headers=headers, timeout=10)
        j = r.json() if r.status_code == 200 else {}
        if not j.get("ok"):
            return {"status": "error", "detail": str(j)[:300]}
        if file_bytes:
            # Upload file
            # files.upload is legacy; use files.uploadV2?
            try:
                import requests
                r2 = requests.post("https://slack.com/api/files.upload", headers=headers, data={"channels": channel, "initial_comment": text[:200]}, files={"file": (filename, file_bytes, "image/png")} if 'filename' in locals() else {"file": ("chart.png", file_bytes, "image/png")}, timeout=10)
            except:
                pass
        return {"status": "sent", "channel": channel}
    except Exception as e:
        return {"status": "error", "detail": str(e)[:300]}
