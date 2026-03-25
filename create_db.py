# create_db.py — création des tables sur PostgreSQL

from dotenv import load_dotenv
from app.database import engine, Base

# Charge le .env
load_dotenv()

def main():
    print("➡️ Création des tables sur PostgreSQL...")
    Base.metadata.create_all(bind=engine)
    print("✅ Tables créées (ou déjà présentes).")

if __name__ == "__main__":
    main()
