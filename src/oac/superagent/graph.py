"""The LangGraph wiring: nodes, the conditional review edge and the human-in-the-loop interrupt."""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from oac.superagent.nodes import (
    CaseState,
    card_node,
    needs_review,
    registry_node,
    stage_node,
    uncertainty_node,
    validate_decision,
)


def review_node(state: CaseState) -> dict[str, Any]:
    """Pause the graph and hand the issues to a clinician. Execution resumes with ``Command(resume=...)``."""
    answer = interrupt({
        "case_id": state["case_id"], "stage": state["stage"],
        "conflicts": state.get("conflicts", []), "flags": state.get("flags", []),
        "options": ["accept_report", "accept_registry", "defer"],
    })
    return {"review": validate_decision(answer)}


def build_graph(checkpointer: Any | None = None):
    g = StateGraph(CaseState)
    g.add_node("stage", stage_node)
    g.add_node("registry", registry_node)
    g.add_node("uncertainty", uncertainty_node)
    g.add_node("review", review_node)
    g.add_node("card", card_node)
    g.add_edge(START, "stage")
    g.add_edge("stage", "registry")
    g.add_edge("registry", "uncertainty")
    g.add_conditional_edges("uncertainty", needs_review, {"review": "review", "card": "card"})
    g.add_edge("review", "card")
    g.add_edge("card", END)
    return g.compile(checkpointer=checkpointer or InMemorySaver())


def run_case(graph, case: CaseState, reviewer=None) -> tuple[dict, dict | None]:
    """Run one case. ``reviewer(payload) -> {"decision", "note"}`` answers an interrupt; without one, the case
    stops at the interrupt and the returned card is None. Returns (final state, interrupt payload or None)."""
    config = {"configurable": {"thread_id": case["case_id"]}}
    state = graph.invoke(case, config)
    pending = state.get("__interrupt__")
    if pending:
        payload = pending[0].value
        if reviewer is None:
            return state, payload
        state = graph.invoke(Command(resume=reviewer(payload)), config)
        return state, payload
    return state, None
