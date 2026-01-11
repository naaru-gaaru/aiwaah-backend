import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI

from prompt import AIWAAH_SYSTEM_PROMPT

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Question(BaseModel):
    message: str

@app.get("/")
def health_check():
    return {"status": "AiWaah Backend is Alive! 🧞‍♂️", "model": "gpt-4o-mini"}

@app.post("/aiwaah")
def ask_aiwaah(q: Question):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": AIWAAH_SYSTEM_PROMPT},
            {"role": "user", "content": q.message}
        ]
    )

    return {"reply": response.choices[0].message.content}
