import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()


def get_db_connection():
    # Connect to PostgreSQL using DATABASE_URL environment variable.
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL is not set in environment or .env")
    return psycopg2.connect(database_url)


get_db = get_db_connection
