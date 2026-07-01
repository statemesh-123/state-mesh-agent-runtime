from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter

_provider: TracerProvider | None = None


def _default_provider() -> TracerProvider:
    global _provider
    if _provider is None:
        _provider = TracerProvider()
        _provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        trace.set_tracer_provider(_provider)
    return _provider


def get_tracer(exporter=None):
    provider = _default_provider()
    if exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("RuntimeTracer")