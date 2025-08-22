# oauth_bridge.py  (FastAPI app; deploy behind API Gateway/Lambda or anywhere)
from dotenv import load_dotenv
load_dotenv()
import os, json, time, hmac, hashlib, base64
from typing import List
from urllib.parse import urlencode, quote
import boto3, requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse

app = FastAPI()
secrets = boto3.client("secretsmanager")

GOOGLE_CLIENT_ID     = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
GOOGLE_TOKEN_URI     = os.getenv("GOOGLE_TOKEN_URI", "https://oauth2.googleapis.com/token")
SECRET_PREFIX        = os.getenv("GOOGLE_OAUTH_SECRET_PREFIX", "prod/google-oauth")

SIGNING_SECRET       = os.environ["ONBOARDING_SIGNING_SECRET"]
CALLBACK_URL         = os.environ["OAUTH_REDIRECT_URI"]  # e.g., https://auth.example.com/google/callback

def b64url(s: bytes) -> str:
    return base64.urlsafe_b64encode(s).rstrip(b"=").decode()

def b64urldecode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "==")

def verify_state(token: str) -> dict:
    try:
        head_b64, pay_b64, sig_b64 = token.split(".")
        mac = hmac.new(SIGNING_SECRET.encode(), f"{head_b64}.{pay_b64}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(b64url(mac), sig_b64):
            raise ValueError("bad signature")
        payload = json.loads(b64urldecode(pay_b64))
        if int(payload["exp"]) < int(time.time()):
            raise ValueError("expired")
        return payload
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid state: {e}")

def secret_name_for(sub: str) -> str:
    return f"{SECRET_PREFIX}/{sub}"

@app.get("/google/connect")
def google_connect(state: str, redirect_uri: str, scopes: str):
    payload = verify_state(state)
    sub = payload["sub"]
    scope_list: List[str] = json.loads(b64urldecode(scopes).decode())

    # Ask Google for offline consent to get a refresh_token
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": CALLBACK_URL,
        "response_type": "code",
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "scope": " ".join(scope_list),
        "state": state,  # echo back
    }
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}")

@app.get("/google/callback")
def google_callback(code: str, state: str):
    payload = verify_state(state)
    sub = payload["sub"]

    # Exchange code for tokens
    data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": CALLBACK_URL,
        "grant_type": "authorization_code",
    }
    r = requests.post(GOOGLE_TOKEN_URI, data=data, timeout=20)
    if r.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {r.text}")
    tok = r.json()
    refresh_token = tok.get("refresh_token")
    if not refresh_token:
        # If missing, the user might have granted before; force prompt=consent next time.
        return HTMLResponse("<h3>Connected, but no refresh_token returned. Remove prior consent and try again.</h3>")

    # Store/overwrite secret
    secret_name = secret_name_for(sub)
    payload = json.dumps({"refresh_token": refresh_token})
    try:
        secrets.create_secret(Name=secret_name, SecretString=payload)
    except secrets.exceptions.ResourceExistsException:
        secrets.put_secret_value(SecretId=secret_name, SecretString=payload)

    return HTMLResponse("<h3>Success! You can return to the chat and use the Google tools now.</h3>")
