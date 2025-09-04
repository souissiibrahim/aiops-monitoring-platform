from pyflink.datastream import StreamExecutionEnvironment
import requests
import json



PROM_URL = "https://prometheus.u-cloudsolutions.xyz/api/v1/query"
METRIC_QUERY = 'node_cpu_seconds_total'  # change to a valid metric on your setup

def fetch_metrics():
    response = requests.get(PROM_URL, params={'query': METRIC_QUERY}, verify=False)
    result = response.json()
    return result['data']['result']

def main():
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(1)

    metrics = fetch_metrics()
    for entry in metrics:
        print(json.dumps(entry, indent=2))

    env.execute("Metric Anomaly Detection Job")

if __name__ == '__main__':
    main()
