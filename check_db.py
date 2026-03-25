# check_db.py — test de connexion PostgreSQL SANS passer par app.database

import os
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy import create_engine

# Charge le .env depuis le dossier courant
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
print("DATABASE_URL vue par check_db.py :", DATABASE_URL)

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL n'est pas définie dans le .env")

engine = create_engine(DATABASE_URL)

def main():
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            print("✅ Connexion PostgreSQL OK —", result.fetchone())
    except Exception as e:
        print("❌ Connexion échouée :", e)

if __name__ == "__main__":
    main()
