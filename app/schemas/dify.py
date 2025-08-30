from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class AskRequest(BaseModel):
    # ⚡ Swagger에서 이상한 additionalProp 안 뜨게 하려면 default_factory만 쓰고 example도 비워둠
    inputs: Dict[str, Any] = Field(default_factory=dict, example={})
    query: str
    response_mode: str = Field(default="blocking", example="blocking")
    conversation_id: Optional[str] = Field(default="", example="")
    user: Optional[str] = Field(default=None, example="abc-123")
    files: List[str] = Field(default_factory=list, example=[])

class AskResponse(BaseModel):
    answer: str
    raw: Optional[Dict[str, Any]] = None
    
class AskSavedLog(BaseModel):
    log_id: int
    user_id: int
    answer: str
    usage: Optional[Dict[str, Any]] = None
    created_at: str