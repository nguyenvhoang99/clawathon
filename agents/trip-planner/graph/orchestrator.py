from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from graph.nodes.budget_node import budget_node
from graph.nodes.intake import intake_node
from graph.nodes.itinerary import itinerary_node
from graph.nodes.specialists import specialists_node
from models.state import TripState


def _route_after_intake(state: TripState) -> str:
    if state.get("phase") == "intake":
        return "end_intake"
    return "specialists"


def build_graph(llm):
    graph_builder = StateGraph(TripState)

    graph_builder.add_node("intake", lambda s: intake_node(s, llm))
    graph_builder.add_node("specialists", specialists_node)
    graph_builder.add_node("budget", budget_node)
    graph_builder.add_node("itinerary", lambda s: itinerary_node(s, llm))
    graph_builder.add_node(
        "end_intake",
        lambda s: {
            "response": s.get("response", ""),
            "phase": "intake",
            "intake_field": s.get("intake_field"),
            "location_prompt": s.get("location_prompt"),
        },
    )

    graph_builder.add_edge(START, "intake")
    graph_builder.add_conditional_edges(
        "intake",
        _route_after_intake,
        {"specialists": "specialists", "end_intake": "end_intake"},
    )
    graph_builder.add_edge("specialists", "budget")
    graph_builder.add_edge("budget", "itinerary")
    graph_builder.add_edge("itinerary", END)
    graph_builder.add_edge("end_intake", END)

    return graph_builder.compile()
