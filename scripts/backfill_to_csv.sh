#!/usr/bin/env bash
set -euo pipefail

# === CONFIG ===
PROM_URL="${PROM_URL:-http://localhost:9090}"   # change si besoin
STEP="${STEP:-300}"                              # 300s = 5 min (mets 60/120 si tu veux plus fin)
DAYS="${DAYS:-7}"                                # fenêtre à backfiller (7 = tout ce que tu as vraiment)
OUT="${OUT:-flink/cleanCSV/cleaned_historical_metrics.csv}"

# métriques BRUTES dynamiques (pas de *_utilization, on reste compatible avec l’existant)
METRICS=(
  "node_cpu_seconds_total"
  "node_memory_MemAvailable_bytes"
  "node_memory_MemTotal_bytes"
  "node_filesystem_free_bytes"
  "node_filesystem_size_bytes"
  "node_network_receive_bytes_total"
  "node_network_transmit_bytes_total"
)

# valeur par défaut pour ces colonnes (ton entraînement ne lit pas confidence, mais on reste homogène)
DEFAULT_CONFIDENCE="0.6"
DEFAULT_DELAY="0"   # backfill historique => pas de délai runtime

# === PREP ===
mkdir -p "$(dirname "$OUT")"
echo "timestamp,metric_name,value,collection_delay,confidence" > "$OUT"

START_EPOCH=$(date -d "${DAYS} days ago" +%s)
END_EPOCH=$(date +%s)

echo "[INFO] Backfill window: $(date -d @$START_EPOCH)  -->  $(date -d @$END_EPOCH)"
echo "[INFO] Prometheus: $PROM_URL  | STEP=${STEP}s  | OUT=$OUT"
echo "[INFO] Metrics: ${METRICS[*]}"

# Fonction d’export d’une métrique sur toute la fenêtre, par pas STEP
export_metric() {
  local metric="$1"
  local start="$2"
  local end="$3"
  local step="$4"

  echo "[INFO] Exporting: $metric"

  # Récupère la réponse
  local resp
  resp=$(curl -sS --fail "${PROM_URL}/api/v1/query_range?query=${metric}&start=${start}&end=${end}&step=${step}") || {
    echo "[ERROR] HTTP failure for metric ${metric} (curl)"; return 1;
  }

  # Vérifie le status Prometheus sans halt_error (compatible jq 1.6)
  local status
  status=$(printf '%s' "$resp" | jq -r '.status // "error"') || status="error"

  if [ "$status" != "success" ]; then
    echo "[WARN] Prometheus returned non-success for ${metric}. Skipping."
    return 0
  fi

  # Transforme la matrix en CSV (ignore NaN)
  printf '%s' "$resp" \
  | jq -r --arg m "$metric" --arg cd "$DEFAULT_DELAY" --arg cf "$DEFAULT_CONFIDENCE" '
      .data.result[]? as $s
      | $s.values[]
      | select((.[0]|type=="number") and (.[1]|tostring != "NaN"))
      | "\(. [0]),\($m),\(. [1]),\($cd),\($cf)"
    ' >> "$OUT"
}

# === EXPORT ===
for MET in "${METRICS[@]}"; do
  export_metric "$MET" "$START_EPOCH" "$END_EPOCH" "$STEP"
  # petite pause pour être gentil avec Prometheus si instance modeste
  sleep 0.3
done

# === SANITY CHECKS LÉGERS (optionnels) ===
LINES=$(wc -l < "$OUT" | tr -d ' ')
echo "[INFO] CSV lines (including header): $LINES"

if [ "$LINES" -le 2 ]; then
  echo "[WARN] Très peu de données exportées. Vérifie PROM_URL / droits / métriques / période."
fi

echo "[OK] Fichier prêt: $OUT"
