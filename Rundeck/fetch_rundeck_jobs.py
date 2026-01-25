    import requests
    import json

    # === Config ===
    RUNDECK_API_TOKEN = "LPqUO7vloCLtAGAWoRJ6GfNfyDhLhrmq"
    RUNDECK_BASE_URL = "http://adress_loc:4440"
    PROJECT_NAME = "AutoRemediation"
    API_VERSION = "45"
    OUTPUT_PATH = "runbook_catalog.jsonl"

headers = {
    "X-Rundeck-Auth-Token": RUNDECK_API_TOKEN,
    "Content-Type": "application/json",
    "Accept": "application/json"
}

def fetch_jobs(project):
    url = f"{RUNDECK_BASE_URL}/api/{API_VERSION}/project/{project}/jobs"
    print(f"🔍 Sending GET request to: {url}")

    try:
        res = requests.get(url, headers=headers)
        print(f"📡 Status Code: {res.status_code}")

        if res.status_code != 200:
            print(f"❌ Failed to fetch jobs: {res.status_code} — {res.text}")
            return []

        try:
            jobs = res.json()
            print(f"✅ Retrieved {len(jobs)} jobs.")
            return jobs
        except json.JSONDecodeError:
            print("❌ Error decoding JSON response. Raw response:")
            print(res.text)
            return []

    except requests.RequestException as e:
        print(f"❌ Request failed: {e}")
        return []

def save_jobs_to_jsonl(jobs, filepath):
    try:
        with open(filepath, "w") as f:
            for job in jobs:
                job_entry = {
                    "job_id": job["id"],
                    "name": job["name"],
                    "description": job.get("description", "").strip()
                }
                f.write(json.dumps(job_entry) + "\n")

        print(f"✅ Saved {len(jobs)} jobs to {filepath}")

    except Exception as e:
        print(f"❌ Failed to write jobs to file: {e}")

if __name__ == "__main__":
    print(f"📡 Fetching Rundeck jobs from project '{PROJECT_NAME}'...")
    jobs = fetch_jobs(PROJECT_NAME)
    if jobs:
        save_jobs_to_jsonl(jobs, OUTPUT_PATH)
