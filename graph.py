from langgraph.graph import StateGraph, END

from state import InfraDesignerState
from scanner.scan import scan_repo
from nodes.gap_identifier import identify_gaps
from nodes.questionnaire import build_questionnaire
from nodes.architecture_reasoner import reason_about_architecture,assess_confidence

MAX_FOLLOWUP_ROUND = 1

def confidence_check_node(state: InfraDesignerState) -> dict:
    from nodes.architecture_reasoner import offline_mode
    import os
    # One model call per report: the confidence check is skipped unless INFRALOOP_AI_CONFIDENCE=1 (free model tiers have tight request limits)
    if offline_mode() or os.environ.get("INFRALOOP_AI_CONFIDENCE") != "1":
        return {"confidence_level": "high", "followup_questions_needed": []}
    triage = assess_confidence(state["scan_result"], state["gaps"], state["questionnaire_answers"])
    return {"confidence_level": triage["level"], "followup_questions_needed": triage["questions"]}

def confidence_router(state: InfraDesignerState) -> str:
    rounds = state.get("followup_rounds", 0)
    if state["confidence_level"] == "low" and state["followup_questions_needed"] and rounds < MAX_FOLLOWUP_ROUND:
        return "need_more"
    return "write_report"

def scan_node(state: InfraDesignerState) -> dict:
    return {"scan_result": scan_repo(state["repo_path"])}


def gap_identifier_node(state: InfraDesignerState) -> dict:
    return {"gaps": identify_gaps(state["scan_result"])}


def questionnaire_node(state: InfraDesignerState) -> dict:
    questions = build_questionnaire(state["scan_result"])
    answers = {}
    for q in questions:
        answers[q["question"]] = input(f"{q['question']} ")
    return {"questionnaire_answers": answers}


def architecture_reasoner_node(state: InfraDesignerState) -> dict:
    report = reason_about_architecture(
        state["scan_result"],
        state["questionnaire_answers"],
        state.get("gaps", []),
    )
    return {"report": report}


def build_scan_graph():
    """Scan + gap identification only."""
    builder = StateGraph(InfraDesignerState)
    builder.add_node("scan", scan_node)
    builder.add_node("gap_identifier", gap_identifier_node)
    builder.set_entry_point("scan")
    builder.add_edge("scan", "gap_identifier")
    builder.add_edge("gap_identifier", END)
    return builder.compile()


def build_report_graph():
    builder = StateGraph(InfraDesignerState)
    builder.add_node("confidence_check", confidence_check_node)
    builder.add_node("architecture_reasoner", architecture_reasoner_node)
    builder.set_entry_point("confidence_check")
    builder.add_conditional_edges(
        "confidence_check",
        confidence_router,
        {
            "need_more": END,
            "write_report": "architecture_reasoner"},
    )
    builder.add_edge("architecture_reasoner", END)
    return builder.compile()

def build_graph():
    """Full CLI chain -- scan, gaps, blocking questionnaire, then straight to the
    report (no confidence loop here; that's only wired into build_report_graph()
    for the web UI so far)."""
    builder = StateGraph(InfraDesignerState)
    builder.add_node("scan", scan_node)
    builder.add_node("gap_identifier", gap_identifier_node)
    builder.add_node("questionnaire", questionnaire_node)
    builder.add_node("architecture_reasoner", architecture_reasoner_node)

    builder.set_entry_point("scan")
    builder.add_edge("scan", "gap_identifier")
    builder.add_edge("gap_identifier", "questionnaire")
    builder.add_edge("questionnaire", "architecture_reasoner")
    builder.add_edge("architecture_reasoner", END)

    return builder.compile()


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "."
    graph = build_graph()
    final_state = graph.invoke({"repo_path": path})
    print("\n=== FINAL REPORT ===\n")
    print(final_state["report"])