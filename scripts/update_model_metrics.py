import argparse, json
from pathlib import Path

from app.db.session import SessionLocal
from app.db.repositories.model_repository import ModelRepository
from app.db.models.model import Model

class _NoopRedis:
    def delete(self, *args, **kwargs): pass

def load_metrics(summary_path: str):
    data = json.loads(Path(summary_path).read_text())
    return {
        "mae": float(data.get("mae_mean", 0.0)),
        "rmse": float(data.get("rmse_mean", 0.0)),
        "smape": float(data.get("smape_mean_pct", 0.0)),
        "coverage": float(data.get("coverage_mean", 0.0)),
        "bias": float(data.get("mean_error_bias", 0.0)),
        "passed_acceptance": bool(data.get("passed_acceptance", False)),
        "best_candidate": data.get("best_candidate"),
    }

def main():
    ap = argparse.ArgumentParser(description="Update Model.metrics by model name")
    ap.add_argument("--model-name", required=True, help="e.g., prophet-cpu")
    ap.add_argument("--summary", required=True, help="Path to SUMMARY.json")
    args = ap.parse_args()

    metrics = load_metrics(args.summary)

    db = SessionLocal()
    try:
        repo = ModelRepository(db=db, redis=_NoopRedis())
        model = db.query(Model).filter_by(name=args.model_name, is_deleted=False).first()
        if not model:
            raise SystemExit(f"❌ Model {args.model_name} not found")

        repo.update(str(model.model_id), {"metrics": metrics})
        print(f"✅ Updated metrics for {args.model_name}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
