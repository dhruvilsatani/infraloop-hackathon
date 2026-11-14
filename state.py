from typing import TypedDict, List, Dict, Any


class InfraDesignerState(TypedDict):
    repo_path: str
    scan_result: Dict[str, Any]
    gaps: List[Dict[str, Any]]
    questionnaire_answers: Dict[str, Any]
    recommendation: Dict[str, Any]
    report: str
    confidence_level: str
    followup_questions_needed: List[str]
    followup_rounds: int
