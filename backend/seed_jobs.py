"""Seed a few demo jobs. Run once: python seed_jobs.py"""
import asyncio, os, uuid
from datetime import datetime, timezone
from dotenv import load_dotenv
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(Path(__file__).parent / ".env")
client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

JOBS = [
    {"title": "Développeur Full-Stack React", "company": "TechNova", "location": "Paris, France", "type": "Temps plein", "category": "Tech", "salary": "45-60k€", "description": "Rejoignez notre équipe produit pour construire des interfaces modernes en React et des APIs performantes.", "requirements": "3+ ans en React/Node, maîtrise de REST, esprit d'équipe."},
    {"title": "Chargé(e) de recrutement", "company": "TalentBridge", "location": "Lyon, France", "type": "Temps plein", "category": "RH", "salary": "35-42k€", "description": "Gérez le sourcing et l'entretien des candidats pour nos clients grands comptes.", "requirements": "Expérience en recrutement, excellent relationnel."},
    {"title": "Designer UI/UX", "company": "PixelForge", "location": "Télétravail", "type": "Freelance", "category": "Design", "salary": "TJM 400€", "description": "Concevez des expériences utilisateur élégantes pour des applications web et mobiles.", "requirements": "Portfolio solide, maîtrise de Figma, sens du détail."},
    {"title": "Data Analyst", "company": "InsightLab", "location": "Marseille, France", "type": "Temps plein", "category": "Data", "salary": "40-50k€", "description": "Analysez les données métier et produisez des tableaux de bord décisionnels.", "requirements": "SQL, Python, Power BI ou Tableau."},
]

async def main():
    for j in JOBS:
        if await db.jobs.find_one({"title": j["title"], "company": j["company"]}):
            continue
        j.update({"id": str(uuid.uuid4()), "is_active": True, "created_at": datetime.now(timezone.utc).isoformat()})
        await db.jobs.insert_one(j)
        print("Inserted:", j["title"])
    print("Done")

asyncio.run(main())
