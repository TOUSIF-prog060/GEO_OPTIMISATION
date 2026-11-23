"""Opportunity engine: turn diagnostics into ranked, evidence-linked gaps and recommendations."""

from src.opportunities.engine import find_opportunities
from src.opportunities.models import OpportunityInput, OpportunityOutput, OpportunityRules

__all__ = ["OpportunityInput", "OpportunityOutput", "OpportunityRules", "find_opportunities"]
