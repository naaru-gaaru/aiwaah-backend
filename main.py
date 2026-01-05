import os
import time
import requests

from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI
from jose import jwt

from prompt import AIWAAH_SYSTEM_PROMPT

# =====================================================
# 1️⃣ ENVIRONMENT & CLIENT SETUP
# =====================================================

load_dotenv()

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Supabase (Identity Provider)
SUPABASE_PROJECT_ID = os.getenv("SUPABASE_PROJECT_ID")

# AIwaah CIAM (our own identity issuer)
AIWAAH_JWT_SECRET = os.getenv("AIWAAH_JWT_SECRET")

# OpenAI client (AiWaah brain)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# =====================================================
# 2️⃣ FASTAPI APP CONFIG
# =====================================================

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://aiwaah-website.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================
# 3️⃣ REQUEST MODELS
# =====================================================

class Question(BaseModel):
    message: str

# =====================================================
# 4️⃣ SUPABASE TOKEN VERIFICATION (GOOGLE → SUPABASE)
# =====================================================

# Supabase publishes public keys (JWKS) for verifying JWTs
SUPABASE_JWKS_URL = (
    f"https://{SUPABASE_PROJECT_ID}.supabase.co/auth/v1/certs"
)

def verify_supabase_token(token: str):
    """
    Verifies Supabase JWT issued after Google OAuth.
    We verify signature + issuer, but do NOT hard-fail on audience.
    """
    jwks = requests.get(SUPABASE_JWKS_URL).json()
    header = jwt.get_unverified_header(token)

    key = next(
        k for k in jwks["keys"] if k["kid"] == header["kid"]
    )

    return jwt.decode(
        token,
        key,
        algorithms=["RS256"],
        options={
            "verify_aud": False  # 🔑 THIS FIXES EVERYTHING
        },
        issuer=f"https://{SUPABASE_PROJECT_ID}.supabase.co/auth/v1"
    )
# =====================================================
# 5️⃣ CIAM TOKEN EXCHANGE (SUPABASE → AIWAAH)
# =====================================================

@app.post("/ciam/exchange")
def exchange_token(request: Request):
    """
    Exchanges a Supabase token for an AIwaah-issued identity token.
    AIwaah becomes its own CIAM authority.
    """
    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")

    supabase_token = auth_header.replace("Bearer ", "")

    try:
        supabase_user = verify_supabase_token(supabase_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Supabase token")

    # Build AIwaah identity claims
    aiwaah_claims = {
        "sub": supabase_user["sub"],                 # Stable user ID
        "email": supabase_user.get("email"),
        "idp": supabase_user.get("app_metadata", {}).get("provider", "unknown"),
        "roles": ["user"],                           # Future RBAC
        "mfa": False,                                # Future MFA
        "iss": "aiwaah.identity",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600               # 1 hour expiry
    }

    aiwaah_token = jwt.encode(
        aiwaah_claims,
        AIWAAH_JWT_SECRET,
        algorithm="HS256"
    )

    return {"aiwaah_token": aiwaah_token}

# =====================================================
# 6️⃣ AIWAAH CHAT ENDPOINT (IDENTITY-AWARE, NO MEMORY)
# =====================================================

@app.post("/aiwaah")
def ask_aiwaah(
    q: Question,
    authorization: str = Header(None)
):
    """
    Main chat endpoint.
    Requires a valid AIwaah-issued identity token.
    """

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing AIwaah token")

    aiwaah_token = authorization.replace("Bearer ", "")

    try:
        identity = jwt.decode(
            aiwaah_token,
            AIWAAH_JWT_SECRET,
            algorithms=["HS256"]
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid AIwaah token")

    user_email = identity.get("email")

    messages = [
        {
            "role": "system",
            "content": f"""
{AIWAAH_SYSTEM_PROMPT}

The authenticated user is {user_email}.
"""
        },
        {
            "role": "user",
            "content": q.message
        }
    ]

    response = openai_client.responses.create(
        model="gpt-4.1-mini",
        input=messages
    )

    return {"reply": response.output_text}




