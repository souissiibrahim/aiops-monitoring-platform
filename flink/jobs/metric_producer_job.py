import json
import requests
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.common.typeinfo import Types
from kafka import KafkaProducer
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PROMETHEUS_BASE_URL = "https://prometheus.u-cloudsolutions.xyz/api/v1"
VERIFY_SSL = False


def fetch_all_metrics():
    collected = []

    try:
        # Step 1: Get all metric names
        label_url = f"{PROMETHEUS_BASE_URL}/label/__name__/values"
        metric_names_resp = requests.get(label_url, verify=VERIFY_SSL, timeout=10)
        metric_names_resp.raise_for_status()
        metric_names = metric_names_resp.json().get("data", [])

        # Step 2: Query each metric
        for metric_name in metric_names:
            query_url = f"{PROMETHEUS_BASE_URL}/query"
            response = requests.get(query_url, params={'query': metric_name}, verify=VERIFY_SSL, timeout=10)
            response.raise_for_status()
            results = response.json().get("data", {}).get("result", [])
            for item in results:
                collected.append(json.dumps({
                    "metric_name": metric_name,
                    "data": item
                }))
    except Exception as e:
        collected.append(json.dumps({"error": str(e)}))

    return collected


def main():
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(1)

    # Pull data outside the Flink pipeline
    metric_data = fetch_all_metrics()

    # Inject as a collection source
    ds = env.from_collection(metric_data, type_info=Types.STRING())

    def send_to_kafka(record):
        producer = KafkaProducer(
            bootstrap_servers='kafka:9092',
            value_serializer=lambda v: json.dumps(v).encode("utf-8")
        )
        producer.send("prometheus-metrics", value=json.loads(record))
        producer.flush()
        producer.close()

    ds.map(send_to_kafka)
    env.execute("Prometheus to Kafka (Flink Python Job)")

if __name__ == "__main__":
    main()
