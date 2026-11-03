from inspect import isawaitable

from app.observability.recorder import bind, context, observed_span, record, tool_io


def instrument_node(db, name, method, graph, agent=None):
    async def invoke(state):
        async def execute():
            result = method(state)
            return await result if isawaitable(result) else result

        execution_id = state.get("execution_id") or context.get().get("execution_id")
        if execution_id is None:
            return await execute()
        with bind(call_attempt_id=state.get("active_call_attempt_id", context.get().get("call_attempt_id"))):
            with observed_span(db, execution_id, "graph.node", node=name) as observation:
                if agent:
                    with observed_span(db, execution_id, "agent", agent=agent) as activity:
                        result = await execute()
                        activity.output = tool_io(name, result, output=True)
                else:
                    result = await execute()
                observation.output = tool_io(name, result, output=True)
                edges = [edge for edge in graph().get_graph().edges if edge.source == name]
                selected = (
                    edges[0]
                    if len(edges) == 1
                    else next(
                        (edge for edge in edges if result.get("route") in {edge.data, edge.target}), None
                    )
                )
                if selected:
                    record(
                        db,
                        execution_id,
                        "graph.transition",
                        "selected",
                        data={
                            "from_node": name,
                            "to_node": selected.target,
                            "conditional": selected.conditional,
                        },
                    )
            return result

    return invoke
