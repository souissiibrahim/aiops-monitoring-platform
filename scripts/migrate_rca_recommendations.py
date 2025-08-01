# scripts/migrate_rca_recommendations.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.db.session import SessionLocal
from app.db.models.rca_analysis import RCAAnalysis

def migrate_old_rca_recommendations():
    db = SessionLocal()
    try:
        outdated_rcas = db.query(RCAAnalysis).filter(
            RCAAnalysis.recommendations != None
        ).all()

        updated_count = 0

        for rca in outdated_rcas:
            if (
                isinstance(rca.recommendations, list) and
                rca.recommendations and
                isinstance(rca.recommendations[0], str)
            ):
                print(f"📌 Migrating RCA {rca.rca_id}")
                rca.recommendations = [
                    {"text": r, "confidence": rca.confidence_score or 0.0}
                    for r in rca.recommendations
                ]
                updated_count += 1

        db.commit()
        print(f"✅ Migrated {updated_count} RCA record(s).")
    except Exception as e:
        db.rollback()
        print(f"❌ Migration failed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    migrate_old_rca_recommendations()
