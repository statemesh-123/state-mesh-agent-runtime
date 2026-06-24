from opentelemetry import trace




def get_tracer():
    
    """
        Provides a named OpenTelemetry tracer for the state-mesh runtime.

        All spans emitted by this library are created through `get_tracer()`, which
        returns a tracer scoped to the name "Tracer". Using a named tracer matters
        because OpenTelemetry uses the tracer name as the instrumentation scope —
        it appears in exported trace data and lets you distinguish spans produced by
        this library from spans produced by application code or other libraries.
    """
    
    return trace.get_tracer("RuntimeTracer")