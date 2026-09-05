# Vidora AI risk management

This implementation supports the voluntary [NIST AI RMF Core](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/) and [Generative AI Profile](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf). It is not certification or a determination of worldwide legal compliance. The four functions are **Govern, Map, Measure, Manage**; monitoring spans Measure and Manage.

## Govern: accountable deployment

`functions/app/governance/policy.json` is a versioned, Pydantic-validated policy. All four model entry points enforce model inventory membership before inference. In production, an owner, explicit approval, and an approved deployment region are required. The shipped policy is deliberately unapproved. The additional [ISO/IEC 42001 AIMS release gate](iso-42001-aims.md) requires current reviews and verified evidence in production. Development calls remain possible. Unknown/malformed policy files fail closed.

Set `AI_POLICY_PATH` to a reviewed JSON policy (otherwise the bundled policy is used). Set `ENVIRONMENT=production`, `AI_DEPLOYMENT_REGION` to the actual backend region, and `AI_ENABLED=true`. Policy changes require process restart/redeployment because policy is cached. Protect policy files and deployment permissions; approval is an operator-controlled configuration, not an independent approval workflow or digital signature. A reviewer must approve the change in source control after inspecting evaluation evidence and provider arrangements. Do not set approval merely to bypass the gate.

Assign a named service owner responsible for releases and incidents, a privacy reviewer responsible for processing/retention, and an evaluation reviewer responsible for language and model quality. Record review date, approver, policy version, artifact links, exceptions, and next review date in the release record. Re-review model, provider, purpose, region, and retention changes.

## Map: system inventory and affected users

| Operation | Model / runtime | Data flow | Principal risks |
|---|---|---|---|
| Transcription | Groq whisper-large-v3 | Temporary downloaded audio goes to Groq; text returns | Third-party disclosure, transcription errors, language/accent disparities |
| Embedding | sentence-transformers all-MiniLM-L6-v2, local CPU | Transcript and question vectors go to PostgreSQL/pgvector | Weak multilingual retrieval, sensitive text encoded in vectors |
| Summary | Groq openai/gpt-oss-20b | First 20,000 transcript characters go to Groq | Incomplete coverage, invented claims, embedded instructions |
| Answer | Groq openai/gpt-oss-20b | Question and retrieved excerpts go to Groq | Unsupported answers, prompt injection, retrieval omissions |

Intended use is video understanding with human verification against the source, not autonomous consequential decisions. Affected people include viewers, speakers, people mentioned in recordings, and rights holders. Q&A text, transcripts, summaries, and embeddings may contain personal data. Existing database retention and scheduled cleanup remain in place; verify deletion and backup retention in the actual deployment.

`deployment_regions` is a backend deployment allowlist, **not** proof of provider/database residency or a user-country restriction. Before enabling a region, record actual audio/LLM processing locations, database and backup locations, lawful use of source media, notices, transfer arrangements, and local requirements. Do not infer these from user IP or browser locale. Routing or local inference must be implemented if a region requires it.

`evaluated_languages` is a release-record field, not automatic language detection or a language access gate. The bundled list is empty because no language evaluation evidence has been supplied. Do not advertise global quality: MiniLM retrieval requires language-specific validation. A multilingual embedding replacement requires re-embedding stored chunks and potentially a vector schema migration; changing the model name alone is insufficient.

## Measure: observable behavior and evaluation evidence

Open-source components: [Pydantic](https://docs.pydantic.dev/latest/) validates policy, [Prometheus Python client](https://prometheus.github.io/client_python/) instruments inference, and Python unittest exercises controls without provider calls. Existing SQLAlchemy and pgvector remain the data stack.

Metrics:
- `vidora_ai_calls_total{operation,outcome}`: success, error, blocked, cancelled.
- `vidora_ai_duration_seconds{operation}`: latency distribution including blocked calls.
- `vidora_ai_quality_events_total{signal}`: no-context answers and summary truncation.

These are operational signals, **not** hallucination, fairness, accuracy, or semantic grounding scores. Prompt delimiting escapes XML-like tags and instructs the model to treat content as data; this is defense in depth, not a prompt-injection guarantee.

Before approval, create a consented/licensed evaluation corpus per supported language and accent with expected transcript, relevant chunk IDs, supported answer facts, and adversarial instructions. Include silence/no-context, misinformation in sources, long transcripts, and sensitive-data cases. Record transcription word error rate, retrieval recall@k, reviewer-scored groundedness, unsupported-claim rate, refusal correctness, and summary coverage, grouped by language. Choose and record thresholds before evaluating; block releases that fail any required slice. Never average away an unsupported language. Repeat on model/prompt/retrieval changes and investigate production complaints. No provider-based quality evaluation has been performed by this refactor.

## Manage: monitoring and incident response

Set `AI_METRICS_TOKEN` to a secret. `/metrics` returns 404 without it and requires `Authorization: Bearer <token>` otherwise. Scrape over TLS using Prometheus `authorization.credentials_file`; do not expose the token in a committed config. Configure the rules in `monitoring/ai-alerts.yml` and route alerts to the named owner using Alertmanager. Rules are starting thresholds to calibrate against traffic.

Metrics are process-local. On Firebase/serverless, a load-balanced scrape does not reliably collect all replicas and instances may disappear before scraping. Use the structured `vidora.governance` audit events through the platform log collector for fleet-wide evidence, or deploy a collector/observable service topology before treating Prometheus as fleet-wide monitoring. No monitoring service is deployed by this change.

Audit events contain a random event ID, operation, model, policy version, AIMS snapshot digest (production), outcome, and duration only. They exclude prompts, answers, audio, user IDs, and exception messages. Configure access control, retention, and durable export in the hosting platform; stdout is not a tamper-proof audit store. Existing application database records still retain Q&A content.

For incidents: disable AI using `AI_ENABLED=false` (or `AI_EMERGENCY_STOP=true`) and restart/redeploy **all** instances. Gates stop new model calls; already running calls are not cancelled. Preserve restricted audit/evaluation evidence, assess affected regions and outputs, correct or delete affected records as appropriate, record incident severity/owner/actions, and obtain a new reviewed policy before re-enabling. Track user complaints through the product's support process; this refactor does not create a support service.

## Control verification

From `functions`, with backend dependencies installed:

```sh
python -m unittest discover -s tests -v
```

No live providers, model downloads, or database are needed by the governance tests. These verify runtime policy enforcement, blocked calls, output/error preservation, metadata-only auditing, and instrumentation. They do not substitute for the release evaluations above.


## Frontend transparency and user review

The submission form explains Groq processing, temporary app storage, provider retention uncertainty, and language limitations before analysis. The workspace labels AI answers and summaries, displays the server-provided expiry in local time, and links to the original YouTube video. Long-summary coverage limitations are always visible because the current API does not persist a truncation flag.

New Q&A responses include `sources` with the actual retrieved text and timestamps used during generation. These are context, not independently verified evidence. Sources are response-only and are not persisted in Q&A history: `null`/absent means unavailable history, while `[]` means retrieval found no context. The frontend distinguishes these states and never creates citations from generated text. No database migration is required.

Questions use the backend's 2,000-character limit, support automatic text direction, and are preserved on failure. HTTP 503 shows an unavailable-service notice without exposing policy configuration. Incomplete/failed analysis cannot open the question composer. Arbitrary API error payloads are no longer logged to the browser console or rendered as UI text.

Users can flag an answer or summary by downloading a JSON issue report with IDs, category, and an optional note. No transcript, answer, or question is included automatically. The interface explicitly says the report has **not** been sent; a real intake/review workflow still needs an operator-owned support service. This download does not establish incident handling or guarantee review.
