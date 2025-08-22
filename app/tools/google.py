# tools.py
import os, json, hmac, time, base64, hashlib, logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

import boto3
from botocore.exceptions import ClientError
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)

# ======= ENV =======
SECRET_PREFIX = os.getenv("GOOGLE_OAUTH_SECRET_PREFIX", "prod/google-oauth")
GOOGLE_TOKEN_URI = os.getenv("GOOGLE_TOKEN_URI", "https://oauth2.googleapis.com/token")
GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]

# Where to send users to start OAuth (your webapp or the bridge below)
# Example (bridge): https://auth.example.com/google/connect
OAUTH_START_URL = os.environ["OAUTH_START_URL"]

# Redirect URI registered in Google Console for the bridge/webapp:
# Example: https://auth.example.com/google/callback
OAUTH_REDIRECT_URI = os.environ["OAUTH_REDIRECT_URI"]

# HMAC secret to sign onboarding tokens (store in Secrets Manager or env)
ONBOARDING_SIGNING_SECRET = os.environ["ONBOARDING_SIGNING_SECRET"]

# Default scopes for tools we expose
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
]

secrets = boto3.client("secretsmanager")


# ======= Helpers =======
def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def b64urljson(obj: dict) -> str:
    return b64url(json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode())

def sign_onboarding_token(payload: dict, ttl_seconds: int = 600) -> str:
    # minimal JWT-like: base64url(header).base64url(payload).base64url(sig)
    header = {"alg": "HS256", "typ": "JWS"}
    payload = dict(payload)
    payload["exp"] = int(time.time()) + ttl_seconds
    head = b64urljson(header)
    pay = b64urljson(payload)
    mac = hmac.new(ONBOARDING_SIGNING_SECRET.encode(), f"{head}.{pay}".encode(), hashlib.sha256).digest()
    sig = b64url(mac)
    return f"{head}.{pay}.{sig}"

def verify_onboarding_token(token: str) -> dict:
    try:
        head_b64, pay_b64, sig_b64 = token.split(".")
        mac = hmac.new(ONBOARDING_SIGNING_SECRET.encode(), f"{head_b64}.{pay_b64}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(b64url(mac), sig_b64):
            raise ValueError("Bad signature")
        payload = json.loads(base64.urlsafe_b64decode(pay_b64 + "=="))
        if int(payload["exp"]) < int(time.time()):
            raise ValueError("Token expired")
        return payload
    except Exception as e:
        raise ValueError(f"Invalid onboarding token: {e}")

def extract_sub(event: Dict[str, Any]) -> str:
    # Common shapes from Gateway/Cognito context
    for path in [("principal","sub"), ("context","user","sub"), ("auth","sub")]:
        cur = event
        ok = True
        for k in path:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                ok = False; break
        if ok and isinstance(cur, str) and cur:
            return cur
    if "x_user_id" in event and event["x_user_id"]:
        return event["x_user_id"]
    raise ValueError("No authenticated 'sub' found in event")

def secret_name_for(sub: str) -> str:
    return f"{SECRET_PREFIX}/{sub}"

def load_google_creds_or_none(sub: str) -> Credentials | None:
    try:
        resp = secrets.get_secret_value(SecretId=secret_name_for(sub))
        data = json.loads(resp["SecretString"])
        refresh_token = data.get("refresh_token")
        if not refresh_token: return None
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri=GOOGLE_TOKEN_URI,
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            scopes=GOOGLE_SCOPES,
        )
        creds.refresh(Request())
        return creds
    except ClientError:
        return None

def oauth_prompt_response(sub: str, requested_scopes: List[str]) -> Dict[str, Any]:
    token = sign_onboarding_token({"sub": sub, "scopes": requested_scopes})
    # Pass all params to your bridge/webapp
    url = (
        f"{OAUTH_START_URL}"
        f"?state={token}"
        f"&redirect_uri={b64url(OAUTH_REDIRECT_URI.encode())}"
        f"&scopes={b64url(json.dumps(requested_scopes).encode())}"
    )
    msg = (
        "Google authorization required.\n\n"
        f"Click to connect Google: {url}\n\n"
        "After granting access, run the tool again."
    )
    return {"ok": False, "error": "OAuthRequired", "content": [{"type": "text", "text": msg}]}

def ok(content: Any) -> Dict[str, Any]:
    if not isinstance(content, str):
        content = json.dumps(content, default=str)
    return {"ok": True, "content": [{"type": "text", "text": content}]}

def err(msg: str, code: str="Error") -> Dict[str, Any]:
    return {"ok": False, "error": code, "content": [{"type": "text", "text": msg}]}


# ======= Tool implementations =======
def tool_google_list_calendar_events(args: Dict[str, Any], creds: Credentials) -> Dict[str, Any]:
    svc = build("calendar", "v3", credentials=creds, cache_discovery=False)
    cal_id = args.get("calendar_id", "primary")
    max_results = int(args.get("max_results", 10))
    now = datetime.utcnow()
    time_min = args.get("time_min") or (now - timedelta(days=1)).isoformat() + "Z"
    time_max = args.get("time_max") or (now + timedelta(days=7)).isoformat() + "Z"
    q = args.get("q")
    events = (
        svc.events().list(calendarId=cal_id, timeMin=time_min, timeMax=time_max,
                          q=q, singleEvents=True, orderBy="startTime", maxResults=max_results)
        .execute().get("items", [])
    )
    return ok({"events": [
        {"id": e.get("id"), "summary": e.get("summary"),
         "start": e.get("start"), "end": e.get("end"),
         "htmlLink": e.get("htmlLink")} for e in events
    ]})

def tool_google_list_gmail_messages(args: Dict[str, Any], creds: Credentials) -> Dict[str, Any]:
    svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
    q = args.get("q", "in:inbox newer_than:7d")
    max_results = int(args.get("max_results", 10))
    label_ids = args.get("label_ids") or None
    res = svc.users().messages().list(userId="me", q=q, maxResults=max_results, labelIds=label_ids).execute()
    msgs = res.get("messages", [])
    out = []
    for m in msgs:
        md = svc.users().messages().get(userId="me", id=m["id"], format="metadata",
                                        metadataHeaders=["From","To","Subject","Date"]).execute()
        headers = {h["name"]: h["value"] for h in md.get("payload",{}).get("headers",[])}
        out.append({"id": m["id"], "snippet": md.get("snippet"),
                    "from": headers.get("From"), "to": headers.get("To"),
                    "subject": headers.get("Subject"), "date": headers.get("Date")})
    return ok({"messages": out})


ROUTER = {
    "google_list_calendar_events": lambda a, c: tool_google_list_calendar_events(a, c),
    "google_list_gmail_messages":  lambda a, c: tool_google_list_gmail_messages(a, c),
}

def lambda_handler(event, context):
    try:
        tool = (event or {}).get("tool")
        args = (event or {}).get("arguments", {}) or {}
        if tool not in ROUTER:
            return err(f"Unknown tool: {tool}", "UnknownTool")

        sub = extract_sub(event)
        creds = load_google_creds_or_none(sub)
        if not creds:
            # Ask user to connect Google first:
            return oauth_prompt_response(sub, GOOGLE_SCOPES)

        return ROUTER[tool](args, creds)
    except Exception as e:
        LOG.exception("Unhandled error")
        return err(str(e), "InternalError")
