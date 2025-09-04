
"""
Expire old Pending predictions whose forecast time has passed.

- Looks for predictions with:
    status = 'Pending'
    AND (input_features->>'forecast_for')::timestamptz < now_utc - grace
- Sets status = 'Expired' and updates updated_at.
- Safe to run repeatedly (idempotent).
- Exit code 0 on success.

Usage examples:
    python -m scripts.expire_predictions
    python -m scripts.expire_predictions --grace-min 5
    PREDICTION_STATUS_PENDING=Pending PREDICTION_STATUS_EXPIRED=Expired \
        python -m scripts.expire_predictions
"""

import os
import sys
import argparse
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from app.db.session import SessionLocal
from app.monitor.heartbeat import start_heartbeat

hb = start_heartbeat("scripts/expire_predictions.py", interval_s=30, version="dev")
DEFAULT_GRACE_MIN = int(os.getenv("EXPIRE_PREDICTIONS_GRACE_MIN", "5"))
STATUS_PENDING = os.getenv("PREDICTION_STATUS_PENDING", "Pending")
STATUS_EXPIRED = os.getenv("PREDICTION_STATUS_EXPIRED", "Expired")


def expire_predictions(grace_min: int, dry_run: bool = False) -> int:
    """Expire Pending predictions older than now - grace."""
    db = SessionLocal()
    try:
        now_utc = datetime.now(timezone.utc)
        cutoff = now_utc - timedelta(minutes=grace_min)

        # Use a single UPDATE … RETURNING for efficiency and atomicity
        sql = text(f"""
            UPDATE predictions
            SET status = :expired,
                updated_at = NOW()
            WHERE is_deleted = FALSE
              AND status = :pending
              AND ((input_features->>'forecast_for')::timestamptz) < :cutoff
            RETURNING prediction_id
        """)

        if dry_run:
            # Preview: count how many would be expired
            preview_sql = text(f"""
                SELECT COUNT(*) AS n
                FROM predictions
                WHERE is_deleted = FALSE
                  AND status = :pending
                  AND ((input_features->>'forecast_for')::timestamptz) < :cutoff
            """)
            n = db.execute(preview_sql, {
                "pending": STATUS_PENDING,
                "cutoff": cutoff
            }).scalar() or 0
            print(f"[DRY-RUN] Would expire {n} predictions (status='{STATUS_PENDING}', cutoff={cutoff.isoformat()})")
            return 0

        rows = db.execute(sql, {
            "expired": STATUS_EXPIRED,
            "pending": STATUS_PENDING,
            "cutoff": cutoff
        }).fetchall()
        db.commit()

        n = len(rows)
        if n:
            print(f"🕒 Expired {n} predictions (status '{STATUS_PENDING}' → '{STATUS_EXPIRED}'; cutoff={cutoff.isoformat()})")
        else:
            print("✅ Nothing to expire.")
        return 0
    except Exception as e:
        print(f"❌ expire_predictions failed: {e}", file=sys.stderr)
        db.rollback()
        return 1
    finally:
        db.close()


def parse_args():
    ap = argparse.ArgumentParser("Expire old Pending predictions")
    ap.add_argument("--grace-min", type=int, default=DEFAULT_GRACE_MIN,
                    help=f"Minutes after forecast_for before expiring (default {DEFAULT_GRACE_MIN})")
    ap.add_argument("--dry-run", action="store_true",
                    help="Do not update; just print how many would change")
    return ap.parse_args()


def main():
    args = parse_args()
    rc = expire_predictions(grace_min=args.grace_min, dry_run=args.dry_run)
    sys.exit(rc)


if __name__ == "__main__":
    main()
