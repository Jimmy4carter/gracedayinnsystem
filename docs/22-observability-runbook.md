# Observability and Alerting Runbook

## Deployment contract

- Namecheap starts the WSGI application through `passenger_wsgi.py`. Keep application JSON logging enabled; use an OTLP collector only when the hosting plan provides a supported, supervised collector process.
- Configure an HTTPS `OTEL_EXPORTER_OTLP_ENDPOINT`, `http/protobuf`, the service name, immutable release, environment resource attribute and collector authentication from the secret manager.
- Preserve `X-Request-ID` at the proxy. Application JSON logs contain `request_id`, `trace_id`, `span_id` and `release`, allowing a request to be followed through Django, MariaDB and outbound Brevo/HTTP work.
- Collector failure must never block hotel requests. Buffer/retry at the collector or agent and retain JSON stdout independently.

## Release verification

1. Deploy to staging with the production telemetry wrapper and a synthetic release ID.
2. Request `/health/live/`, `/health/ready/`, public room search, one authenticated portal page and the Brevo sandbox flow.
3. Confirm each request returns `X-Request-ID`, its JSON log has a valid 32-character `trace_id`, and the collector contains a trace with matching service, release and environment.
4. Confirm MariaDB/client spans contain no passwords, tokens, email bodies, inquiry text or unapproved query parameters.
5. Trigger a controlled application exception and confirm the exception trace/log reaches the error view with the release and linked runbook.
6. Preserve screenshots/query links and timestamps as release evidence. Roll back telemetry configuration if it leaks data or materially affects request latency.

## Minimum actionable alerts

| Signal | Initial trigger | Owner | Response target | Runbook |
| --- | --- | --- | --- | --- |
| Readiness unavailable | 2 consecutive minutes | On-call administrator | 5 minutes | Incident response |
| HTTP 5xx rate | Above 2% for 5 minutes | Engineering/on-call | 10 minutes | Deployment rollback |
| p95 booking latency | Above 2 seconds for 10 minutes | Engineering/on-call | 15 minutes | Database saturation |
| Booking/inventory conflict anomaly | Any reconciliation failure | Front desk manager + engineering | Immediate | Booking conflict |
| Unledgered payment/refund overage | Any reconciliation failure | Finance manager | Immediate; stop settlement | Ledger mismatch |
| Brevo terminal failure or suppression spike | Above approved operational baseline | Reservations/marketing owner | 30 minutes | Brevo outage |
| Scheduler stale or failed jobs | Readiness stale or failure queue non-empty | System administrator | 15 minutes | Failed jobs |
| Backup missing/verification failed | Daily backup deadline missed | System administrator | 30 minutes | Backup/restore |

Thresholds are starting controls and require operational-owner approval using production baselines. Every alert must link to a named owner and runbook; disable unactionable duplicates instead of teaching staff to ignore them.
