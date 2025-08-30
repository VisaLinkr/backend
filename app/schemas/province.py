from typing import List, Optional
from pydantic import BaseModel

class ProvinceIndustryCount(BaseModel):
    industry: str
    count: int

class ProvinceSummary(BaseModel):
    province_id: int
    province_name: str
    population_total: int
    major_industries: List[str] 