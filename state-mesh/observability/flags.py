from opentelemetry import trace

from core.context import Flag


def attach_flags_to_span(flags: list[Flag]) -> None:
    span = trace.get_current_span()
    for i, flag in enumerate(flags):
        span.set_attribute(f"flag.{i}.type", flag.flag_type)
        span.set_attribute(f"flag.{i}.reason", flag.reason)
        span.set_attribute(f"flag.{i}.severity", flag.severity)
