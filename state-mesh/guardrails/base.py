from __future__ import annotations
from dataclasses import dataclass
from typing import Any,  Literal
from abc import ABC , abstractmethod
from core.context import Context

@dataclass
class GuardResult:
    passed:bool
    reason: str
    severity: Literal["warn", "block"]="warn"
    
  
class Guard(ABC):
    @abstractmethod
    async def check(self,ctx:Context,data:Any) -> GuardResult:
        pass
   
 