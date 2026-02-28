"""Pydantic schema validation for AI Reasoning Engine output."""
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional


class AIAnalysisResult(BaseModel):
    """Validated AI analysis output from the Reasoning Engine."""
    score: int = Field(description="Conviction score 0-100")  # bounds enforced by clamp_score validator below
    verdict: str = Field(description="FAVORABLE, RISKY, or AVOID")
    summary: str = Field(default="", description="2-3 sentence summary")
    risks: List[str] = Field(default_factory=list, description="Key risk factors")
    thesis: str = Field(default="", description="Core thesis statement")

    @field_validator('verdict')
    @classmethod
    def validate_verdict(cls, v):
        allowed = {'FAVORABLE', 'RISKY', 'AVOID'}
        v_upper = v.upper().strip()
        if v_upper == 'SAFE':
            return 'FAVORABLE'
        if v_upper not in allowed:
            return 'RISKY'
        return v_upper

    @field_validator('score', mode='before')
    @classmethod
    def clamp_score(cls, v):
        """Clamp score to [0, 100] to handle AI model output that may exceed bounds.
        Running with mode='before' ensures the clamp fires before Pydantic's int
        coercion, so out-of-range values (e.g. 105) are silently clamped rather
        than causing a ValidationError.
        Verdict-score consistency is enforced downstream in reasoning_engine.py.
        """
        try:
            return max(0, min(100, int(v)))
        except (TypeError, ValueError):
            return 0
