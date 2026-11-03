"""Regenerate both genuine vector SVGs without application imports or dependencies."""

import ast
import json
from pathlib import Path
from xml.etree import ElementTree

from src.agent_workflow import draw as workflow
from src.system_architecture import draw as architecture

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def graph_value(node):
    """Read only literal names/collections from source; never import the app."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name) and node.id in {"START", "END"}:
        return node.id
    if isinstance(node, (ast.List, ast.Tuple)):
        return [graph_value(item) for item in node.elts]
    raise ValueError("Graph structure changed; review the diagram before exporting")


def main():
    runtime = ast.parse(
        (ROOT / "backend/app/ai/runtime.py").read_text(encoding="utf-8")
    )
    build = next(
        n
        for n in ast.walk(runtime)
        if isinstance(n, ast.FunctionDef) and n.name == "_build"
    )
    nodes = next(
        n
        for n in ast.walk(build)
        if isinstance(n, ast.Dict)
        and any(isinstance(k, ast.Constant) and k.value == "load" for k in n.keys)
    )
    actual = [key.value for key in nodes.keys]
    expected = [
        "load",
        "planning",
        "supervisor",
        "research",
        "prepare_call",
        "voice_session",
        "negotiation",
        "verification",
        "human_approval",
        "pause",
        "memory",
        "evaluation",
    ]
    assert actual == expected, (
        "Graph changed: review the editable diagrams before exporting"
    )
    routes = next(
        n
        for n in ast.walk(build)
        if isinstance(n, ast.Dict)
        and any(isinstance(k, ast.Constant) and k.value == "call" for k in n.keys)
    )
    actual_routes = {k.value: v.value for k, v in zip(routes.keys, routes.values)}
    assert actual_routes == {
        "call": "research",
        "approval": "human_approval",
        "pause": "pause",
        "finish": "memory",
    }
    direct_edges = [
        [graph_value(arg) for arg in n.args]
        for n in ast.walk(build)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "add_edge"
        and not any(
            isinstance(arg, ast.Name) and arg.id in {"a", "b"} for arg in n.args
        )
    ]
    assert direct_edges == [
        ["START", "load"],
        ["load", "planning"],
        ["planning", "supervisor"],
    ]
    edge_loop = next(
        n
        for n in ast.walk(build)
        if isinstance(n, ast.For) and isinstance(n.iter, ast.List)
    )
    contact_edges = graph_value(edge_loop.iter)
    assert contact_edges == [
        ["research", "prepare_call"],
        ["prepare_call", "voice_session"],
        ["voice_session", "negotiation"],
        ["negotiation", "verification"],
        ["verification", "supervisor"],
        ["human_approval", "supervisor"],
        ["pause", "supervisor"],
        ["memory", "evaluation"],
        ["evaluation", "END"],
    ]
    voice = ast.parse(
        (ROOT / "backend/app/voice/delegation.py").read_text(encoding="utf-8")
    )
    voice_route = next(
        n
        for n in ast.walk(voice)
        if isinstance(n, ast.DictComp)
        and isinstance(n.key, ast.Name)
        and n.key.id == "k"
    )
    voice_targets = graph_value(voice_route.generators[0].iter)
    assert voice_targets == [
        "negotiate",
        "verify",
        "requirements",
        "decline",
        "clarify",
    ]
    contracts = ast.parse(
        (ROOT / "backend/app/ai/contracts.py").read_text(encoding="utf-8")
    )
    evaluation = next(
        n.value
        for n in contracts.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "Evaluation" for t in n.targets)
    )
    decisions = graph_value(evaluation.slice)
    assert decisions == [
        "ACCEPTABLE",
        "UNACCEPTABLE",
        "REQUIRES_USER_APPROVAL",
        "INSUFFICIENT_INFORMATION",
    ]
    verification = next(
        n
        for n in contracts.body
        if isinstance(n, ast.ClassDef) and n.name == "VerificationResult"
    )
    status = next(
        n.annotation
        for n in verification.body
        if isinstance(n, ast.AnnAssign) and n.target.id == "status"
    )
    statuses = graph_value(status.slice)
    assert statuses == [
        "CONFIRMED",
        "REJECTED",
        "PENDING",
        "AMBIGUOUS",
        "NEEDS_USER_ACTION",
    ]
    for name, draw in [
        ("system-architecture", architecture),
        ("agent-workflow", workflow),
    ]:
        contents = draw()
        xml = ElementTree.fromstring(contents)
        assert xml.attrib["viewBox"] == "0 0 1920 840"
        assert not xml.findall(".//{http://www.w3.org/2000/svg}image"), (
            "SVGs must remain vector diagrams"
        )
        (HERE / f"{name}.svg").write_text(contents, encoding="utf-8")
        print(f"Generated {name}.svg (true vector, 1920 × 840)")
    (HERE / "source-check.json").write_text(
        json.dumps(
            {
                "booking_graph_nodes": actual,
                "supervisor_routes": actual_routes,
                "booking_fixed_edges": direct_edges + contact_edges,
                "voice_delegation_targets": voice_targets,
                "negotiation_decisions": decisions,
                "verification_statuses": statuses,
                "sources": [
                    "backend/app/ai/runtime.py::_build",
                    "backend/app/voice/delegation.py",
                    "backend/app/ai/contracts.py",
                ],
                "scope": "Source structure check; does not claim external provider acceptance",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
