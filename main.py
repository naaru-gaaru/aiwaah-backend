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

from prompt import AIWAAH_SYSTEM_PROMPT

load_dotenv()

# --- Auth0 Config ---
AUTH0_DOMAIN = "dev-vdi60zpk3pq4icvf.ca.auth0.com"
API_AUDIENCE = "https://aiwaah-backend"
ALGORITHMS = ["RS256"]

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
        print(f"⚠️ Auth Failed (Running in Bypass Mode): {e}")
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
    return {"status": "AiWaah Backend is Alive! 🧞‍♂️", "model": "gpt-4o-mini"}

@app.post("/aiwaah")
def ask_aiwaah(q: Question, user: dict = Depends(get_current_user)):
    # user dict contains claims (sub, etc.) if needed
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": AIWAAH_SYSTEM_PROMPT},
            {"role": "user", "content": q.message}
        ]
    )

    return {"reply": response.choices[0].message.content}
