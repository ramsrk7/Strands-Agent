import os
from dotenv import load_dotenv

load_dotenv()

# AWS / Bedrock
AWS_PROFILE = os.getenv("AWS_PROFILE", "personal")
AWS_REGION = os.getenv("AWS_REGION", "us-west-2")
BEDROCK_MEMORY_NAME = os.getenv("BEDROCK_MEMORY_NAME", "ProjectNamerMemory")
BEDROCK_MEMORY_ID = os.getenv("BEDROCK_MEMORY_ID")  # optional fast-path

# Model (OpenAI via Strands)
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
OPENAI_MODEL_ID = os.getenv("OPENAI_MODEL_ID", "gpt-4o")
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "1000"))
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))

# App defaults
APP_DEBUG = os.getenv("APP_DEBUG", "1") == "1"
