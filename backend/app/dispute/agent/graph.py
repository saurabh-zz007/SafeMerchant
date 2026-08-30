"""
LangGraph StateGraph definition for the dispute-resolution agent.

Wires together the 3 nodes (retrieve → triage → draft) and the
conditional gate edge. Supports interrupt-based Human-in-the-Loop
for cases that require manual review.

Graph topology:
    START → retrieve_evidence → triage_and_score → draft_response
          → gate_decision (conditional edge)
              ├── "auto_submit"   → auto_submit_node   → END
              ├── "human_review"  → human_review_node   → END  (interrupt_before)
              ├── "accept_loss"   → accept_loss_node    → END
              ├── "auto_refund"   → auto_refund_node    → END
              └── "refund_review" → refund_review_node  → END  (interrupt_before)

NOTE: The compiled graph is created at app startup in ``app.main.lifespan``
using ``compile_graph_with_checkpointer()`` from ``app.core.checkpointer``.
Do NOT instantiate a compiled graph at module level — the checkpointer
requires an async connection that is only available during the lifespan.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.dispute.agent.nodes import (
    accept_loss_node,
    auto_refund_node,
    auto_submit_node,
    draft_response,
    gate_decision,
    human_review_node,
    refund_review_node,
    retrieve_evidence,
    triage_and_score,
)
from app.dispute.agent.state import DisputeAgentState


def build_dispute_graph() -> StateGraph:
    """
    Construct the dispute-resolution LangGraph (uncompiled).

    Graph topology:
        START → retrieve_evidence → triage_and_score → draft_response
              → gate_decision (conditional edge)
                  ├── "auto_submit"   → auto_submit_node → END
                  ├── "human_review"  → human_review_node → END
                  ├── "accept_loss"   → accept_loss_node → END
                  ├── "auto_refund"   → auto_refund_node → END
                  └── "refund_review" → refund_review_node → END

    Returns the uncompiled StateGraph. Use
    ``app.core.checkpointer.compile_graph_with_checkpointer()``
    to compile with checkpointing and interrupt breakpoints.
    """
    graph = StateGraph(DisputeAgentState)

    # ── Register Nodes ──
    graph.add_node("retrieve_evidence", retrieve_evidence)
    graph.add_node("triage_and_score", triage_and_score)
    graph.add_node("draft_response", draft_response)
    graph.add_node("auto_submit", auto_submit_node)
    graph.add_node("human_review", human_review_node)
    graph.add_node("accept_loss", accept_loss_node)
    graph.add_node("auto_refund", auto_refund_node)
    graph.add_node("refund_review", refund_review_node)

    # ── Wire Edges ──
    graph.set_entry_point("retrieve_evidence")
    graph.add_edge("retrieve_evidence", "triage_and_score")
    graph.add_edge("triage_and_score", "draft_response")

    # Conditional gate after drafting
    graph.add_conditional_edges(
        "draft_response",
        gate_decision,
        {
            "auto_submit": "auto_submit",
            "human_review": "human_review",
            "accept_loss": "accept_loss",
            "auto_refund": "auto_refund",
            "refund_review": "refund_review",
        },
    )

    # Terminal edges
    graph.add_edge("auto_submit", END)
    graph.add_edge("human_review", END)
    graph.add_edge("accept_loss", END)
    graph.add_edge("auto_refund", END)
    graph.add_edge("refund_review", END)

    return graph
