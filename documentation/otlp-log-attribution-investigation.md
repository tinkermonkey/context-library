# OTLP Log Attribution Investigation (2026-07-03)

## Summary

Logs from context-library appeared to be "missing" from SigNoz — every query filtered by `service.name = context-library` returned nothing, and logs showed up only with `service = null`. A methodical proof-of-concept proved the **application, the OTLP export, the collector, and ClickHouse storage are all correct**. The log records are ingested and stored **with `service.name = context-library`** — the "null service" was a **query/UI projection artifact**, not a data-loss bug.

**Bottom line: OTLP logs work. No pipeline change is required for correctness.**

## How we got here (fixes shipped along the way)

While chasing this, several *real but latent* telemetry bugs were found and fixed on `redesign/filesystem-ingestion`. These improved the telemetry code but were **not** the cause of the "missing logs":

- `39b53f6` — consolidated telemetry package; OTEL spans/metrics across pipeline, routes, scheduler; OTLP config baked into docker-compose.
- `118813a` — fixed a pyproject extra name mismatch (`telemetry` → `otel`) that silently prevented `opentelemetry-instrumentation-*` packages from installing (root symptom: "No module named 'opentelemetry.instrumentation'"); wired `set_logger_provider()`.
- `f4db3da` — removed an unsupported `insecure=True` kwarg from the gRPC log exporter.
- `fd801ef` — replaced the deprecated `opentelemetry.sdk._logs.LoggingHandler` with the supported `opentelemetry.instrumentation.logging` handler and guarded it against `dictConfig` eviction.

Keep these — they are correct improvements. They just weren't the root cause.

## The proof-of-concept (what finally settled it)

Built inside the deployed container (exact installed package versions: `opentelemetry-sdk==1.43.0`, `opentelemetry-exporter-otlp-proto-grpc==1.43.0`, `opentelemetry-instrumentation-logging==0.64b0`), with a **faux OTLP gRPC collector** that wrote every received record (body, severity, resource attributes) to disk. The sender stack was assembled layer by layer, each pointed at the faux collector:

| Phase | Stack | Result |
|---|---|---|
| 1 | Bare OTel SDK → OTLP gRPC exporter → LoggingHandler | PASS — `service.name` delivered |
| 2 | The app's actual `setup_telemetry()` | PASS — `service.name=context-library` delivered |
| 3 | + FastAPI + uvicorn (`log_config=None`) | PASS |
| 3b | + FastAPI + uvicorn with the real uvicorn `log_config` | PASS (after the ~5s BatchLogRecordProcessor flush) |
| direct | App → real SigNoz collector (100.104.222.123:4317) | `LogRecordExportResult.SUCCESS` in ~7ms |
| storage | Query `signoz_logs.logs_v2` in ClickHouse | Records present WITH `service.name=context-library` |

Every layer delivered correctly. The application is exonerated.

## Root cause: ClickHouse schema asymmetry (traces vs logs)

The records land in ClickHouse correctly. Sample `resources_string` from a real context-library log row in `signoz_logs.logs_v2`:

```
{'service.instance.id':'93eb6133...','service.name':'context-library',
 'service.version':'0.1.0','deployment.environment':'production',
 'telemetry.sdk.language':'python','telemetry.sdk.name':'opentelemetry',
 'telemetry.sdk.version':'1.43.0'}
```

The asymmetry that causes the "null service" appearance:

- **Traces** (`signoz_traces.signoz_index_v3`) have a **materialized column**:
  `resource_string_service$$name LowCardinality(String) DEFAULT resources_string['service.name']`
  plus a `serviceName` ALIAS. So trace tooling/UI can filter and group by service directly.
- **Logs** (`signoz_logs.logs_v2`) store `service.name` **only as a key inside the `resources_string` Map** — there is **no materialized column and no `serviceName` alias**.

Any tool/query that projects a top-level `service` field (as the homelab-data `signoz_query_logs` proxy does) therefore returns `null` for logs, even though the resource attribute is present in the map. This is the entire "missing logs" phenomenon.

The SigNoz collector logs pipeline is `receivers: [otlp] → processors: [batch] → exporters: [clickhouselogsexporter, signozmeter]`. There is **no filelog receiver**, so there is a single, correct ingestion path (OTLP). Duplicate log lines observed earlier were the app emitting each record through both the root logger and the uvicorn loggers (harmless app-side logging config), not a second ingestion path.

## Solution / how to work with context-library logs

1. **Correctness: nothing to fix in the app or the collector.** Logs are exported, received, stored, and attributed with `service.name=context-library`.
2. **To view/query the logs:** in the SigNoz Logs Explorer, filter by the **resource attribute** `service.name = context-library` (this reads `resources_string` and works). In raw ClickHouse: `WHERE resources_string['service.name'] = 'context-library'`.
3. **Optional tooling improvement (outside this repo):** update the homelab-data `signoz_query_logs` MCP proxy to project `resources_string['service.name']` into its `service` field for logs, so verification tooling stops reporting `null`. This is a proxy/tooling change, not a SigNoz or context-library change.
4. **Do NOT** add per-attribute materialized columns to `logs_v2` or otherwise mutate the SigNoz log schema — SigNoz's Logs Explorer natively filters resource attributes from the map; schema surgery is unnecessary and risky on the shared observability stack.

## Key takeaway

`force_flush()` returning success and traces working did not imply logs were failing — the logs were succeeding too. The false signal came entirely from a tool projecting a trace-shaped `service` field onto log rows that store service identity in a resource map. When telemetry "disappears," verify at the storage layer (ClickHouse `resources_string`) before assuming an app or collector bug.
