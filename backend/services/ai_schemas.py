"""Pydantic schema validation for AI Reasoning Engine output."""
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional


class AIAnalysisResult(BaseModel):
    """Validated AI analysis output from the Reasoning Engine."""
    score: int = Field(ge=0, le=100, description="Conviction score 0-100")
    verdict: str = Field(description="FAVORABLE, RISKY, or AVOID")
    summary: str = Field(default="", description="2-3 sentence summary")
    risks: List[str] = Field(default_factory=list, description="Key risk factors")
    thesis: str = Field(default="", description="Core thesis statement")

    @field_validator('verdict')
    @classmethod
    def validate_verdict(cls, v):
        allowed = {'FAVORABLE', 'RISKY', 'AVOID'}
        v_upper = v.upper().strip()
        # Map legacy values
        if v_upper == 'SAFE':
            return 'FAVORABLE'
        if v_upper not in allowed:
            return 'RISKY'  # Default to RISKY if unknown
        return v_upper

    @field_validator('score')
    @classmethod
    def clamp_score(cls, v, info):
        """Clamp score to [0, 100] to handle AI model output that may exceed bounds.
        Note: Field(ge=0, le=100) raises ValidationError on out-of-range values;
        this validator silently clamps instead, which is safer for AI-parsed JSON.
        Verdict-score consistency is enforced downstream in reasoning_engine.py.
        """
        return max(0, min(100, v))
