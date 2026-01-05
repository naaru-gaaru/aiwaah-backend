import os
import time
import requests

from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI
from jose import jwt

from supabase import create_client

from prompt import AIWAAH_SYSTEM_PROMPT

# =====================================================
# 1️⃣ ENVIRONMENT & CLIENT SETUP
# =====================================================

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

SUPABASE_PROJECT_ID = os.getenv("SUPABASE_PROJECT_ID")
SUPABASE_URL = f"https://{SUPABASE_PROJECT_ID}.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

AIWAAH_JWT_SECRET = os.getenv("AIWAAH_JWT_SECRET")

# OpenAI client (AiWaah's "brain")
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Supabase server-side client (used for memory storage)
supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY
)

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

# Supabase publishes public keys (JWKS) for verifying tokens
SUPABASE_JWKS_URL = (
    f"https://{SUPABASE_PROJECT_ID}.supabase.co/auth/v1/certs"
)

def verify_supabase_token(token: str):
    """
    Verifies a Supabase-issued JWT (from Google SSO).
    This proves the user authenticated with Supabase.
    """
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

# =====================================================
# 5️⃣ CIAM TOKEN EXCHANGE (SUPABASE → AIWAAH)
# =====================================================

@app.post("/ciam/exchange")
def exchange_token(request: Request):
    """
    Exchanges a Supabase token for an AiWaah-issued identity token.
    This allows AiWaah to act as its own CIAM authority.
    """
    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")

    supabase_token = auth_header.replace("Bearer ", "")

    try:
        supabase_user = verify_supabase_token(supabase_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Supabase token")

    # Build AiWaah identity claims
    aiwaah_claims = {
        "sub": supabase_user["sub"],               # Stable user ID
        "email": supabase_user.get("email"),
        "idp": supabase_user.get("app_metadata", {}).get("provider", "unknown"),
        "roles": ["user"],                         # Future RBAC
        "mfa": False,                              # Future MFA
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

# =====================================================
# 6️⃣ USER MEMORY HELPERS (IDENTITY-SCOPED)
# =====================================================

def fetch_user_memory(user_id: str, limit: int = 6):
    """
    Fetches the last N messages for a specific user.
    Memory is strictly scoped by user_id (CIAM principle).
    """
    response = (
        supabase.table("aiwaah_memory")
        .select("role, content")
        .eq("user_id", user_id)
        .order("created_at", desc=False)
        .limit(limit)
        .execute()
    )

    return response.data or []

def store_message(user_id: str, role: str, content: str):
    """
    Stores a single message in persistent memory.
    """
    supabase.table("aiwaah_memory").insert({
        "user_id": user_id,
        "role": role,
        "content": content
    }).execute()

# =====================================================
# 7️⃣ AIWAAH CHAT ENDPOINT (IDENTITY + MEMORY AWARE)
# =====================================================

@app.post("/aiwaah")
def ask_aiwaah(
    q: Question,
    authorization: str = Header(None)
):
    """
    Main chat endpoint.
    Requires a valid AiWaah identity token.
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

    user_id = identity["sub"]
    user_email = identity.get("email")

    # 1️⃣ Load past memory for this user
    memory = fetch_user_memory(user_id)

    # 2️⃣ Build prompt with memory
    messages = [
        {
            "role": "system",
            "content": f"""
{AIWAAH_SYSTEM_PROMPT}

The authenticated user is {user_email}.
Use prior context when relevant.
"""
        },
        *memory,
        {"role": "user", "content": q.message}
    ]

    # 3️⃣ Call OpenAI
    response = openai_client.responses.create(
        model="gpt-4.1-mini",
        input=messages
    )

    reply = response.output_text

    # 4️⃣ Store conversation in memory
    store_message(user_id, "user", q.message)
    store_message(user_id, "assistant", reply)

    return {"reply": reply}
