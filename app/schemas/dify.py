from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class AskRequest(BaseModel):
    # ⚡ Swagger에서 이상한 additionalProp 안 뜨게 하려면 default_factory만 쓰고 example도 비워둠
    inputs: Dict[str, Any] = Field(default_factory=dict, example={})
    query: str = Field(..., example="Shin Yab 남자, 국적 스리랑카, 생일 2000.07.12, 고등학교 졸업, 한국어능력시험 점수 없음, 제조업무 희망.")
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