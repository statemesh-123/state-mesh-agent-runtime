from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar, Literal, List

from pydantic import BaseModel,Field

StateSchema = TypeVar("StateSchema", bound=BaseModel)


class Flag(BaseModel):
    step_name:str 
    severity: Literal["info","warn","error"]
    timestamp:datetime=Field(default_factory=lambda:datetime.now(timezone.utc))
    flag_type: str
    reason:str
    payload:dict[str,Any]=Field(default_factory=dict)

class ContextMutationError(Exception):
    pass
    
class Context(Generic[StateSchema]):
    """
    Context is the main object that is passed to all steps.
    It contains the state, run_id, trace_id, pipeline_name and flags.
    """
    def __init__(self,state,run_id=None,trace_id=None,pipeline_name="unnamed"):
        self._state = state
        self._run_id = run_id or str(uuid.uuid4())
        self._trace_id = trace_id or str(uuid.uuid4())
        self._pipeline_name = pipeline_name
        self._flags:list[Flag] = []
        self._extras:dict[str,Any]={}
        self._step_name=None
       
    @property
    def state(self) -> StateSchema:
        return self._state
        
    @property
    def run_id(self) -> str:
        return self._run_id
    
    @property
    def trace_id(self) -> str:
        return self._trace_id
    
    @property
    def pipeline_name(self) -> str:
        return self._pipeline_name 

    @property
    def flags(self) -> list[Flag]:
        flag=self._flags.copy() # sp the user wont be able directly modify this
        return flag
    
    def set(self,key:str,value:Any)->None:
        if key in self._extras:
            raise ContextMutationError(f"Key {key} already exists in extras")
        self._extras[key]=value
    
    def get(self,key:str,default:Any=None)->Any:
        return self._extras.get(key,default)
    
    def emit_flag(self,flag_type:str,reason:str,severity:Literal["info","warn","error"]="warn",payload:dict[str,Any]|None=None)->None:
        self._flags.append(Flag(
            step_name=self._step_name,
            severity=severity,
            flag_type=flag_type,
            reason=reason,
            payload=payload or {}
        ))
        
    def _set_current_step(self, step_name: str) -> None:
        self._step_name = step_name

    def _replace_state(self, new_state: StateSchema) -> None:
        self._state = new_state
    
    def __repr__(self) -> str:
        return (
        f"Context(run_id={self._run_id!r}, "
        f"step={self._step_name!r}, "
        f"flags={len(self._flags)})"
    )
        
        

        
