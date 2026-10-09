import os

from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

DATABASE_URL = os.getenv("DATABASE_URL")

MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4.1")

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 500))

CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 100))

TEMPERATURE = float(os.getenv("TEMPERATURE", 0.2))
