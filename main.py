import os
import time
import requests

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI
from jose import jwt

from prompt import AIWAAH_SYSTEM_PROMPT

# --------------------
# Setup
# --------------------

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_PROJECT_ID = os.getenv("SUPABASE_PROJECT_ID")
AIWAAH_JWT_SECRET = os.getenv("AIWAAH_JWT_SECRET")

client = OpenAI(api_key=OPENAI_API_KEY)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://aiwaah-website.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------
# Models
# --------------------

class Question(BaseModel):
    message: str

# --------------------
# Supabase Token Verification
# --------------------

SUPABASE_JWKS_URL = (
    f"https://{SUPABASE_PROJECT_ID}.supabase.co/auth/v1/certs"
)

def verify_supabase_token(token: str):
    jwks = requests.get(SUPABASE_JWKS_URL).json()
    header = jwt.get_unverified_header(token)

    key = next(
        k for k in jwks["keys"] if k["kid"] == header["kid"]
    )

    return jwt.decode(
        token,
        key,
        audience="authenticated",
        algorithms=["RS256"]
    )

# --------------------
# CIAM Exchange Endpoint
# --------------------

@app.post("/ciam/exchange")
def exchange_token(request: Request):
    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")

    supabase_token = auth_header.replace("Bearer ", "")

    try:
        supabase_user = verify_supabase_token(supabase_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Supabase token")

    aiwaah_claims = {
        "sub": supabase_user["sub"],
        "email": supabase_user.get("email"),
        "idp": supabase_user.get("app_metadata", {}).get("provider", "unknown"),
        "roles": ["user"],
        "mfa": False,
        "iss": "aiwaah.identity",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600
    }

    aiwaah_token = jwt.encode(
        aiwaah_claims,
        AIWAAH_JWT_SECRET,
        algorithm="HS256"
    )

    return {"aiwaah_token": aiwaah_token}

# --------------------
# AIwaah Chat Endpoint (unchanged for now)
# --------------------

@app.post("/aiwaah")
def ask_aiwaah(q: Question):
    try:
        response = client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {
                    "role": "system",
                    "content": AIWAAH_SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": q.message
                }
            ]
        )

        return {"reply": response.output_text}

    except Exception as e:
        return {"error": str(e)}
