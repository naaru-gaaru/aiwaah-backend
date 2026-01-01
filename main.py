import os
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI

from prompt import AIWAAH_SYSTEM_PROMPT

load_dotenv()

# Create OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI()

class Question(BaseModel):
    message: str

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

        return {
            "reply": response.output_text
        }

    except Exception as e:
        return {
            "error": str(e)
        }
