"""Locust 50 users p95 <300ms — run: locust --headless -u 50 -r 10 --run-time 30s -H http://localhost:8000"""
from locust import HttpUser, task, between
import random

class InsightAgentUser(HttpUser):
    wait_time = between(0.2, 0.5)

    def on_start(self):
        # Upload a small CSV once per user, keep dataset_id
        import io, csv
        # Use existing sample if available, else create
        self.dataset_id = None
        try:
            # Try upload
            csv_body = "a,b\n1,2\n3,4\n"
            files = {"file": ("locust.csv", csv_body, "text/csv")}
            r = self.client.post("/api/datasets/upload", files=files)
            if r.status_code == 200:
                self.dataset_id = r.json().get("id")
        except:
            pass

    @task(3)
    def list_datasets(self):
        self.client.get("/api/datasets", name="GET /api/datasets")

    @task(2)
    def get_dataset(self):
        if self.dataset_id:
            self.client.get(f"/api/datasets/{self.dataset_id}", name="GET /api/datasets/{id}")

    @task(1)
    def chat(self):
        if self.dataset_id:
            self.client.post("/api/chat", json={"dataset_id": self.dataset_id, "query": "sum of a"}, name="POST /api/chat")

    @task(1)
    def health(self):
        self.client.get("/health", name="GET /health")
