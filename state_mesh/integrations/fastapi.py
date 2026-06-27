from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel

from state_mesh.core.context import Context
from state_mesh.core.pipeline import Pipeline, PipelineResult

_STATUS_CODES: dict[str, int] = {
    "failed": 500,
    "timed_out": 504,
    "guarded": 422,
}


def mount_pipeline(
    app,
    pipeline: Pipeline,
    path: str,
    state_schema: type[BaseModel] | None = None,
) -> None:
    @app.post(path)
    async def _endpoint(body: dict[str, Any]) -> PipelineResult:
        state = state_schema(**body) if state_schema else body
        ctx = Context(state=state, pipeline_name=pipeline.name)
        result = await pipeline.run(ctx)
        if result.status != "success":
            raise HTTPException(
                status_code=_STATUS_CODES.get(result.status, 500),
                detail={"status": result.status, "run_id": result.run_id},
            )
        return result
