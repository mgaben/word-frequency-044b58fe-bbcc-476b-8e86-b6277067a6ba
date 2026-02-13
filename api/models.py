from pydantic import BaseModel
from typing import Dict


class KeywordsRequest(BaseModel):
    article: str
    depth: int
    ignore_list: list[str]
    percentile: int


class KeywordFrequencyResponse(BaseModel):
    word_count: Dict[str, int]
    word_percentage: Dict[str, float]
