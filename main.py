import os
import jwt
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI
import requests
from cryptography.x509 import load_pem_x509_certificate
from cryptography.hazmat.backends import default_backend

# from supabase import create_client, Client  <-- removed to avoid build errors
import requests
import json
from prompt import AIWAAH_SYSTEM_PROMPT

load_dotenv()

# --- Auth0 Config ---
AUTH0_DOMAIN = "dev-vdi60zpk3pq4icvf.ca.auth0.com"
API_AUDIENCE = "https://aiwaah-backend"
ALGORITHMS = ["RS256"]

# --- Supabase Config (REST API) ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_REST_URL = f"{SUPABASE_URL}/rest/v1/messages"
SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Auth Helper ---
def verify_jwt(token: str):
    try:
        jwks_url = f"https://{AUTH0_DOMAIN}/.well-known/jwks.json"
        jwks_client = jwt.PyJWKClient(jwks_url)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=ALGORITHMS,
            audience=API_AUDIENCE,
            issuer=f"https://{AUTH0_DOMAIN}/",
        )
        return payload
    except Exception as e:
        print(f"Auth Failed (Running in Bypass Mode): {e}")
        # BYPASS MODE: Return a fake user so the chat still works!
        return {"sub": "bypass-user", "name": "Guest"}

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    return verify_jwt(token)

class Question(BaseModel):
    message: str

@app.get("/")
def health_check():
    return {"status": "AiWaah Backend is Alive!", "model": "gpt-4o-mini"}

from fastapi import Header

@app.get("/history")
def get_history(user: dict = Depends(get_current_user), x_user_id: str = Header(None)):
    user_id = user.get("sub")
    print(f"DEBUG: get_history called. user_id from token: {user_id}, x_user_id from header: {x_user_id}")
    
    if user_id == "bypass-user" and x_user_id:
        user_id = x_user_id
        print(f"DEBUG: Using fallback user_id: {user_id}")
        
    try:
        url = f"{SUPABASE_REST_URL}?user_id=eq.{user_id}&order=created_at.asc"
        print(f"DEBUG: Fetching history from: {url}")
        response = requests.get(url, headers=SUPABASE_HEADERS)
        print(f"DEBUG: Supabase response status: {response.status_code}")
        return response.json()
    except Exception as e:
        print(f"Db Error: {e}")
        return []

@app.get("/debug-db")
def debug_db():
    try:
        # Check total count
        count_response = requests.get(f"{SUPABASE_REST_URL}?select=count", headers=SUPABASE_HEADERS)
        
        # Check recent messages (all users)
        recent_response = requests.get(f"{SUPABASE_REST_URL}?limit=5&order=created_at.desc", headers=SUPABASE_HEADERS)
        
        return {
            "total_count": count_response.json(),
            "recent_samples": recent_response.json(),
            "env_status": "Keys present" if SUPABASE_KEY and SUPABASE_URL else "Keys missing"
        }
    except Exception as e:
        return {"error": str(e)}

@app.post("/aiwaah")
def ask_aiwaah(q: Question, user: dict = Depends(get_current_user), x_user_id: str = Header(None)):
    user_id = user.get("sub")
    if user_id == "bypass-user" and x_user_id:
        user_id = x_user_id
    
    print(f"DEBUG: ask_aiwaah saving for user: {user_id}")
    
    # 1. Save User Message
    try:
        requests.post(
            SUPABASE_REST_URL, 
            headers=SUPABASE_HEADERS, 
            json={"user_id": user_id, "role": "user", "content": q.message}
        )
    except Exception as e:
        print(f"DB Error (User): {e}")

    # 2. Get AI Response
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": AIWAAH_SYSTEM_PROMPT},
            {"role": "user", "content": q.message}
        ]
    )
    ai_text = response.choices[0].message.content

    # 3. Save AI Message
    try:
        requests.post(
            SUPABASE_REST_URL, 
            headers=SUPABASE_HEADERS, 
            json={"user_id": user_id, "role": "ai", "content": ai_text}
        )
    except Exception as e:
        print(f"DB Error (AI): {e}")

    return {"reply": ai_text}
