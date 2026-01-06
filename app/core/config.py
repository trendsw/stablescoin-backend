import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@192.168.31.49:5432/truth_engine"
)

#REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

SCRAPE_INTERVAL_MINUTES = 2