# Production cost configuration

The API should use request-based Cloud Run billing with zero minimum instances.
Video analysis is awaited inside the HTTP request; it does not require CPU after
the response. Keep 1 vCPU and 2 GiB RAM for analysis.

After Firebase deployments, verify that `run.googleapis.com/cpu-throttling` is
`true` or absent (request-based), never `false` (instance-based), and that minimum
instances remain zero. If necessary, apply:

```powershell
gcloud run services update api --cpu-throttling --region=us-central1 --project=vidoraai-2bbce
```

Continuous external `/health` uptime checks were removed on 2026-09-13. The
monitoring setup script creates error alerts only. Page-load warm-up remains;
it is a normal billable request and does not guarantee instance retention or
provide outage detection. Cold starts may occur after inactivity.

Source ZIPs, retained source versions, and Artifact Registry images have storage
costs independent of request-based compute billing.
