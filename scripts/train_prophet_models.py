import argparse, json, os
from pathlib import Path
from itertools import product
import pandas as pd, numpy as np
from prophet import Prophet
from prophet.diagnostics import cross_validation, performance_metrics
from prophet.plot import plot_cross_validation_metric
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import joblib

        
_hb = None
try:
    from app.monitor.heartbeat import start_heartbeat
    _hb = start_heartbeat("scripts/train_prophet_models.py", interval_s=30, version="cv-grid")
except Exception:
    _hb = None

# -------------------------
# Best-effort DB status hooks (no CLI arg)
# -------------------------
_DB_ENABLED = False
_SessionLocal = None
_Model = None

def _try_init_db():
    global _DB_ENABLED, _SessionLocal, _Model
    try:
        from app.db.session import SessionLocal
        from app.db.models.model import Model
        _SessionLocal = SessionLocal
        _Model = Model
        _DB_ENABLED = True
    except Exception:
        _DB_ENABLED = False

def _metric_to_model_name(metric: str) -> str:
    m = (metric or "").lower()
    if "cpu" in m:
        return "prophet-cpu"
    if "memory" in m or "mem" in m:
        return "prophet-memory"
    if any(k in m for k in ["filesystem", "disk", "fs", "storage"]):
        return "prophet-disk"
    return f"prophet-{m}".replace(" ", "-")

def _set_model_status(model_name: str, status: str, set_trained_at: bool = False):
    if not _DB_ENABLED:
        return
    db = _SessionLocal()
    try:
        model = (
            db.query(_Model)
              .filter(_Model.name == model_name, _Model.is_deleted == False)  # noqa: E712
              .first()
        )
        if not model:
            return
        model.last_training_status = status
        if set_trained_at:
            from datetime import datetime, timezone
            model.last_trained_at = datetime.now(timezone.utc)
        db.add(model)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

# -------------------------
# Your original training logic (unchanged)
# -------------------------
def find_csvs(data_root: Path):
    csvs_here = list(data_root.glob("*.csv"))
    if csvs_here:
        metric = data_root.name
        for csv_path in sorted(csvs_here):
            instance = csv_path.stem
            yield metric, instance, csv_path
        return
    for metric_dir in sorted(data_root.glob("*")):
        if not metric_dir.is_dir():
            continue
        for csv_path in sorted(metric_dir.glob("*.csv")):
            metric = metric_dir.name
            instance = csv_path.stem
            yield metric, instance, csv_path

def load_series(csv_path: Path):
    df = pd.read_csv(csv_path)
    need = {"ds","y"}
    if not need.issubset(df.columns):
        raise ValueError(f"{csv_path} must have columns ds,y,... ; got {df.columns.tolist()}")
    df["ds"] = pd.to_datetime(df["ds"], utc=True, errors="coerce").dt.tz_localize(None)
    df["y"]  = pd.to_numeric(df["y"], errors="coerce")
    df = df.dropna(subset=["ds","y"]).drop_duplicates(subset=["ds"]).sort_values("ds").reset_index(drop=True)
    return df

def train_and_cv_one(
    df, metric, instance, out_dir,
    initial, horizon, period,
    cps_values, sps_values,
    seasonality_mode, changepoint_range, interval_width,
    acceptance, rolling_window=0.0
):
    out_dir.mkdir(parents=True, exist_ok=True)
    results, best_key, best_score = [], None, np.inf
    def write_txt(name, text): (out_dir / name).write_text(text)

    for cps, sps in product(cps_values, sps_values):
        key = f"cps_{cps}_sps_{sps}"
        cand_dir = out_dir / f"cv_{key}"
        cand_dir.mkdir(parents=True, exist_ok=True)

        m = Prophet(
            changepoint_prior_scale=cps,
            seasonality_prior_scale=sps,
            seasonality_mode=seasonality_mode,
            changepoint_range=changepoint_range,
            interval_width=interval_width,
            daily_seasonality=True,
            weekly_seasonality=True,
            yearly_seasonality=False,
        )
        m.fit(df[["ds","y"]])

        try:
            df_cv = cross_validation(m, initial=initial, period=period, horizon=horizon, parallel=None)
        except Exception as e:
            write_txt(f"ERROR_{key}.txt", f"CV failed: {e}")
            continue

        df_p = performance_metrics(df_cv, rolling_window=rolling_window)
        df_cv.to_csv(cand_dir / "cv_predictions.csv", index=False)
        df_p.to_csv(cand_dir / "cv_metrics.csv",     index=False)

        for metric_name in ["mae","rmse","mape","smape","coverage"]:
            try:
                fig = plot_cross_validation_metric(df_cv, metric=metric_name)
                fig.savefig(cand_dir / f"plot_{metric_name}.png", bbox_inches="tight")
                plt.close(fig)
            except Exception:
                pass

        rmse_mean = df_p["rmse"].mean()
        results.append((key, rmse_mean))
        if rmse_mean < best_score:
            best_score = rmse_mean
            best_key   = key
            best_model = m
            best_cv    = df_cv.copy()
            best_metrics = df_p.copy()

    if results:
        pd.DataFrame(results, columns=["candidate","rmse_mean"]).sort_values("rmse_mean") \
          .to_csv(out_dir / "grid_summary.csv", index=False)

    if best_key is None:
        write_txt("SUMMARY.txt", "No successful candidate found during CV.\n")
        return

    model_path = out_dir / f"best_model_{best_key}.pkl"
    joblib.dump(best_model, model_path)
    best_cv.to_csv(out_dir / f"best_cv_predictions_{best_key}.csv", index=False)
    best_metrics.to_csv(out_dir / f"best_cv_metrics_{best_key}.csv", index=False)

    best_cv["error"] = best_cv["yhat"] - best_cv["y"]
    mean_error = float(best_cv["error"].mean())

    mae_ok   = best_metrics["mae"].mean()  <= acceptance["MAE"]
    rmse_ok  = best_metrics["rmse"].mean() <= acceptance["RMSE"]
    smape_ok = (best_metrics["smape"].mean()/100.0) <= acceptance["sMAPE"]
    cov_mean = float(best_metrics["coverage"].mean())
    cov_low, cov_high = acceptance["COVERAGE"]
    cov_ok = (cov_mean >= cov_low) and (cov_mean <= cov_high)

    passed = all([mae_ok, rmse_ok, smape_ok, cov_ok])
    summary = {
        "metric": metric,
        "instance": instance,
        "best_candidate": best_key,
        "model_path": str(model_path),
        "rmse_mean": float(best_metrics["rmse"].mean()),
        "mae_mean":  float(best_metrics["mae"].mean()),
        "mape_mean": float(best_metrics["mape"].mean()),
        "smape_mean_pct": float(best_metrics["smape"].mean()),
        "coverage_mean": cov_mean,
        "mean_error_bias": mean_error,
        "acceptance_thresholds": acceptance,
        "passed_acceptance": passed,
        "notes": "Thresholds assume utilization in [0,1]; adjust as needed."
    }
    (out_dir / "SUMMARY.json").write_text(json.dumps(summary, indent=2))
    write_txt("SUMMARY.txt",
        (f"[{metric} | {instance}] Best: {best_key}\n"
         f"  RMSE(mean): {summary['rmse_mean']:.4f}\n"
         f"  MAE(mean):  {summary['mae_mean']:.4f}\n"
         f"  sMAPE(%):   {summary['smape_mean_pct']:.2f}\n"
         f"  Coverage:   {summary['coverage_mean']:.3f}\n"
         f"  Bias (ME):  {summary['mean_error_bias']:.6f}\n"
         f"  Acceptance: {'PASS ✅' if passed else 'FAIL ❌'}\n")
    )

# -------------------------
# Main (status always attempted, no flag)
# -------------------------
def main():
    # Always try to init DB for status updates (no CLI arg)
    _try_init_db()

    p = argparse.ArgumentParser(description="Train Prophet with rolling CV on (ds,y,metric,instance) CSVs.")
    p.add_argument("--data_root", type=str, default="data/prophet_ready_csv")
    p.add_argument("--out_root",  type=str, default="models/prophet")
    p.add_argument("--initial",   type=str, default="7 days")
    p.add_argument("--horizon",   type=str, default="2 days")
    p.add_argument("--period",    type=str, default="12 hours")
    p.add_argument("--cps", type=str, default="0.01,0.05,0.1")
    p.add_argument("--sps", type=str, default="0.1,1.0,5.0")
    p.add_argument("--seasonality_mode", choices=["additive","multiplicative"], default="additive")
    p.add_argument("--changepoint_range", type=float, default=0.9)
    p.add_argument("--interval_width",    type=float, default=0.8)
    p.add_argument("--mae_thr",  type=float, default=0.05)
    p.add_argument("--rmse_thr", type=float, default=0.05)
    p.add_argument("--smape_thr",type=float, default=0.10)
    p.add_argument("--coverage_low",  type=float, default=0.75)
    p.add_argument("--coverage_high", type=float, default=0.90)
    args = p.parse_args()

    data_root = Path(args.data_root)
    out_root  = Path(args.out_root)
    cps_values = [float(x) for x in args.cps.split(",")]
    sps_values = [float(x) for x in args.sps.split(",")]
    acceptance = {
        "MAE": args.mae_thr,
        "RMSE": args.rmse_thr,
        "S MAPE".replace(" ",""): args.smape_thr,  # keep key as 'sMAPE'
        "COVERAGE": (args.coverage_low, args.coverage_high),
    }
    acceptance["sMAPE"] = acceptance.pop("SMAPE")

    any_found = False
    for metric, instance, csv_path in find_csvs(data_root):
        any_found = True
        print(f"\n=== Training [{metric}] on [{instance}] ===")
        print(f"CSV: {csv_path}")

        # Mark RUNNING before this metric family
        model_name = _metric_to_model_name(metric)
        _set_model_status(model_name, "running", set_trained_at=False)

        try:
            df = load_series(csv_path)
            if len(df) < 100:
                print(f"WARNING: only {len[df]} points; CV may be unstable.")
            safe_instance = instance.replace("/", "_")
            out_dir = out_root / metric / safe_instance

            train_and_cv_one(
                df=df, metric=metric, instance=instance, out_dir=out_dir,
                initial=args.initial, horizon=args.horizon, period=args.period,
                cps_values=cps_values, sps_values=sps_values,
                seasonality_mode=args.seasonality_mode,
                changepoint_range=args.changepoint_range,
                interval_width=args.interval_width,
                acceptance=acceptance, rolling_window=0.0
            )
            print(f"Artifacts saved in: {out_dir}")
            sj = out_dir / "SUMMARY.json"
            if sj.exists():
                print(sj.read_text())

            # Success → SUCCEEDED + last_trained_at
            _set_model_status(model_name, "succeeded", set_trained_at=True)

        except Exception as e:
            print(f"ERROR training {metric} / {instance}: {e}")
            # Failure → FAILED (no last_trained_at)
            _set_model_status(model_name, "failed", set_trained_at=False)

    if not any_found:
        print(f"No CSVs found under {data_root}. Expected: <metric>/<instance>.csv")

if __name__ == "__main__":
    main()
