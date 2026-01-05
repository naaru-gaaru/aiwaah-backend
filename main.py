import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI

from prompt import AIWAAH_SYSTEM_PROMPT

# =====================================================
# ENV SETUP
# =====================================================

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

# =====================================================
# FASTAPI APP
# =====================================================

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://aiwaah-website.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================
# MODELS
# =====================================================

class Question(BaseModel):
    message: str

# =====================================================
# CHAT ENDPOINT (NO AUTH)
# =====================================================

@app.post("/aiwaah")
def ask_aiwaah(q: Question):
    """
    Stable, unauthenticated chat endpoint.
    This is the last known-good working version.
    """

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

    return {
        "reply": response.output_text
    }
