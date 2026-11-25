import json
import logging
import sys
import time

from fastapi import FastAPI, Request
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import get_settings

SCAN_RESULTS = Counter("dlp_scan_results_total", "Scan results received from the worker", ["status"])
DOWNLOADS = Counter("dlp_downloads_total", "Download attempts", ["outcome"])

_RESERVED = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
            "service": get_settings().service_name,
        }
        out.update({k: v for k, v in record.__dict__.items() if k not in _RESERVED})
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
    logging.getLogger("uvicorn.access").disabled = True  # replaced by the middleware below
    logging.getLogger("botocore").setLevel(logging.WARNING)


def setup_metrics(app: FastAPI) -> None:
    Instrumentator(excluded_handlers=["/metrics", "/healthz"]).instrument(app).expose(
        app, include_in_schema=False
    )


def setup_tracing(app: FastAPI) -> None:
    s = get_settings()
    if not s.otel_exporter_otlp_endpoint:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": s.service_name}))
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{s.otel_exporter_otlp_endpoint.rstrip('/')}/v1/traces"))
    )
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,metrics")


def add_request_logging(app: FastAPI) -> None:
    log = logging.getLogger("http")

    @app.middleware("http")
    async def _log(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        if request.url.path not in ("/healthz", "/metrics"):
            log.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "ms": round((time.perf_counter() - start) * 1000, 1),
                },
            )
        return response
