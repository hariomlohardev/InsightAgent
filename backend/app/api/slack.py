import time
import hmac
import hashlib
import os
from fastapi import APIRouter, Request, HTTPException, Header
from typing import Optional

router = APIRouter(prefix="/api/slack", tags=["slack"])

def verify_slack_signature(signing_secret: str, timestamp: str, body: bytes, signature: str) -> bool:
    if not signing_secret:
        return False
    try:
        ts = int(timestamp)
        if abs(time.time() - ts) > 60 * 5:
            return False
    except:
        return False
    basestring = f"v0:{timestamp}:{body.decode('utf-8', errors='ignore')}"
    my_sig = "v0=" + hmac.new(signing_secret.encode(), basestring.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(my_sig, signature)

@router.post("/events")
async def slack_events(request: Request, x_slack_signature: Optional[str] = Header(None), x_slack_request_timestamp: Optional[str] = Header(None)):
    body = await request.body()
    # JSON parse
    import json
    try:
        data = json.loads(body.decode() or "{}")
    except:
        data = {}
    # URL verification challenge
    if data.get("type") == "url_verification":
        challenge = data.get("challenge","")
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(content=challenge, media_type="text/plain")
    # Verify signature if secrets set
    signing_secret = os.getenv("SLACK_SIGNING_SECRET")
    verify_env = os.getenv("SLACK_VERIFY", "true").lower()
    if signing_secret and verify_env not in ("false","0","no"):
        if not x_slack_signature or not x_slack_request_timestamp:
            raise HTTPException(status_code=401, detail="Missing Slack signature")
        if not verify_slack_signature(signing_secret, x_slack_request_timestamp, body, x_slack_signature):
            raise HTTPException(status_code=401, detail="Invalid Slack signature")

    event = data.get("event", {})
    # Handle slash command payload is form-encoded, not JSON — slack sends as x-www-form-urlencoded for slash
    # But our endpoint expects JSON for events; slash command handling separately
    text = ""
    channel = None
    user = None
    if event:
        etype = event.get("type")
        if etype in ("app_mention", "message"):
            # Avoid bot messages
            if event.get("bot_id"):
                return {"status": "ignored bot"}
            text = event.get("text","")
            # Remove bot mention <@U123>
            import re
            text = re.sub(r"<@[^>]+>", "", text).strip()
            channel = event.get("channel")
            user = event.get("user")
        else:
            return {"status": "ignored event type", "type": etype}
    else:
        # Could be slack slash command form?
        # If body is form-encoded and has 'command'='/insight'
        # Try to parse as form
        try:
            from urllib.parse import parse_qs, unquote_plus
            form = parse_qs(body.decode())
            if form.get("command", [""])[0] == "/insight" or "text" in form:
                text = form.get("text",[""])[0]
                channel = form.get("channel_id",[""])[0]
                user = form.get("user_id",[""])[0]
            else:
                return {"status": "no event"}
        except:
            return {"status": "no event"}
    if not text:
        return {"status": "no text"}

    # Default dataset_id: try env DEFAULT_DATASET_ID or pick first dataset
    dataset_id = os.getenv("DEFAULT_DATASET_ID")
    if not dataset_id:
        from app.core import storage
        ds = storage.list_datasets()
        if ds:
            dataset_id = ds[0]["id"]
        else:
            # No dataset — reply with help
            return {"status": "no dataset", "reply": "No dataset uploaded yet — upload a CSV in the app first."}
    # Call chat service
    from app.services.chat_service import process_query_v2
    try:
        result = await process_query_v2(dataset_id, text)
        insight = result.get("insight","")
        # Build reply text
        reply_text = f"*{text}*\n{insight}"
        # Truncate
        if len(reply_text) > 3000:
            reply_text = reply_text[:3000] + "…"
        # Include result preview
        res = result.get("result")
        if res and res.get("data"):
            # Format as table text (first 5 rows)
            try:
                import pandas as pd
                df = pd.DataFrame(res["data"][:5])
                reply_text += "\n\n```\n" + df.to_string(index=False) + "\n```"
            except:
                pass
        # Send to Slack via bot token if available, else return in response (for testing)
        bot_token = os.getenv("SLACK_BOT_TOKEN")
        if bot_token and channel:
            import httpx
            try:
                r = httpx.post("https://slack.com/api/chat.postMessage", json={"channel": channel, "text": reply_text}, headers={"Authorization": f"Bearer {bot_token}"}, timeout=10)
                j = r.json() if r.status_code == 200 else {}
                if not j.get("ok"):
                    return {"status": "slack error", "detail": str(j)[:300], "reply": reply_text}
                return {"status": "sent", "reply": reply_text}
            except Exception as e:
                return {"status": "error posting", "detail": str(e)[:300], "reply": reply_text}
        else:
            # No token — return reply for caller to handle (useful for webhook-less demo)
            return {"status": "ok (no token)", "reply": reply_text, "result": result.get("result"), "chart": result.get("chart") is not None}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/slash")
async def slack_slash(request: Request):
    # For slash command /insight installed via Slack app
    body = await request.body()
    from urllib.parse import parse_qs
    form = parse_qs(body.decode())
    text = form.get("text",[""])[0]
    channel = form.get("channel_id",[""])[0]
    user = form.get("user_id",[""])[0]
    # We reuse events logic but simpler
    if not text:
        return {"response_type":"ephemeral","text":"Usage: /insight <your question> — e.g., /insight top products by sales"}
    # Reuse same dataset logic
    import os
    dataset_id = os.getenv("DEFAULT_DATASET_ID")
    if not dataset_id:
        from app.core import storage
        ds = storage.list_datasets()
        if ds:
            dataset_id = ds[0]["id"]
        else:
            return {"response_type":"ephemeral","text":"No dataset uploaded yet"}
    from app.services.chat_service import process_query_v2
    try:
        result = await process_query_v2(dataset_id, text)
        insight = result.get("insight","")
        reply = f"*{text}*\n{insight}"
        return {"response_type":"in_channel","text": reply[:3000]}
    except Exception as e:
        return {"response_type":"ephemeral","text": f"Error: {str(e)[:200]}"}
