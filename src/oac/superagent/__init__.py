"""Super-agent v0: a LangGraph state graph that combines contract outputs into a reviewed case card.

The report agent (a pinned LLM, run by ``oac.run_llm``) has already extracted findings. This graph does the
"rules decide, humans confirm" half:

    report output ──► stage (FIGO rules) ──► registry check ──► uncertainty triage ──┬──► case card
                                                                                     └──► clinician review
                                                                                          (interrupt) ──► case card

Every node is deterministic: no extra model calls, so the same inputs always give the same card.
"""

GRAPH_VERSION = "0.1.0"
