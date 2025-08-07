import pandas as pd
import random

# Define base metric patterns
base_patterns = [
    {"metric_name": "node_cpu_usage_percent", "incident_type_name": "HighCPUUsage", "description": "CPU usage above threshold", "category": "Performance"},
    {"metric_name": "node_memory_utilization", "incident_type_name": "MemoryPressure", "description": "High memory pressure detected", "category": "Performance"},
    {"metric_name": "node_disk_read_time_seconds", "incident_type_name": "DiskLatency", "description": "Disk read time anomaly", "category": "Performance"},
    {"metric_name": "network_rx_dropped_total", "incident_type_name": "NetworkPacketLoss", "description": "High packet drop rate", "category": "Network"},
    {"metric_name": "node_network_latency_seconds", "incident_type_name": "NetworkLatency", "description": "High network latency", "category": "Network"},
    {"metric_name": "cpu_throttling_seconds", "incident_type_name": "CPULimitThrottling", "description": "CPU throttling detected", "category": "Performance"},
    {"metric_name": "memory_oom_kills_total", "incident_type_name": "MemoryOOM", "description": "OOM kills observed", "category": "Stability"},
    {"metric_name": "disk_io_utilization", "incident_type_name": "DiskSaturation", "description": "High disk IO utilization", "category": "Performance"}
]

# Generate synthetic data
rows = []
for _ in range(1000): 
    p = random.choice(base_patterns)
    rows.append({
        "metric_name": p["metric_name"],
        "value": round(random.uniform(0.7, 1.0) * random.randint(10, 1000), 2),
        "confidence": round(random.uniform(0.75, 0.99), 2),
        "anomaly_score": round(random.uniform(0.01, 0.04), 4),
        "incident_type_name": p["incident_type_name"],
        "description": p["description"],
        "category": p["category"]
    })

# Save as CSV
df = pd.DataFrame(rows)
df.to_csv("incident_type_training_data_large.csv", index=False)
print("✅ CSV file saved: incident_type_training_data_large.csv")
