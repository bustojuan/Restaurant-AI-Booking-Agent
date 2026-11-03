"""Reference-inspired four-section workflow grounded in the implemented graph."""

from .svg import AMBER, BLUE, GREEN, MUTED, PURPLE, RED, SVG


def draw():
    s = SVG(
        "Multi-agent workflow",
        "Configured BARIA booking workflow. Planning feeds Supervisor. Its conditional contact branch runs Research and Voice Session, then stored Offer Review and Confirmation Review return to Supervisor. During contact, the voice service can delegate decisions to Negotiation or Verification and receive their results. Simulation performs direct checks. Human approval and pause resume Supervisor. Its finish branch leads to Memory and Summary, then Evaluation. Backend outcomes are persisted decisions, not additional graph nodes.",
    )
    s.pill(964, 30, 312, "Multi-agent workflow", "layers")
    s.pill(1294, 30, 290, "Voice calls (external)", "phone")
    s.pill(1602, 30, 270, "Human in the loop", "human")

    s.text(70, 147, "01 / PREPARATION", size=26, color=BLUE, weight=650, max_width=360)
    s.card(
        70,
        158,
        310,
        86,
        "Planning",
        "Requirements → plan",
        icon="calendar",
        size=31,
        body=24,
    )
    s.card(
        480,
        158,
        330,
        86,
        "Supervisor",
        "Routes on saved state",
        icon="graph",
        size=31,
        body=24,
    )
    s.card(972, 158, 360, 86, "Research", "Restaurant context", icon="search", size=31)
    s.edge([(380, 201), (480, 201)])
    s.edge([(810, 201), (972, 201)], color="purple", conditional=True)
    s.text(892, 187, "call", size=25, anchor="middle", max_width=100)

    s.card(
        70,
        326,
        350,
        90,
        "Human decision",
        "Approve · pause · resume",
        icon="human",
        color=AMBER,
        fill="url(#amber-card)",
        size=29,
        body=23,
    )
    s.edge(
        [(480, 219), (430, 219), (430, 371), (420, 371)],
        color="purple",
        conditional=True,
        both=True,
    )
    s.text(70, 304, "approval / pause", size=25, color=PURPLE, max_width=310)

    s.group(930, 278, 900, 252, "02 / CONTACT", fill="#eef6f0", color=GREEN, size=26)
    s.edge([(1152, 244), (1152, 346)])
    s.text(1412, 312, "Voice delegation", size=25, color=PURPLE, max_width=390)
    s.card(
        952,
        346,
        400,
        108,
        "Voice Session",
        "Restaurant contact",
        icon="phone",
        size=36,
        body=27,
        fill="url(#green-card)",
        color=GREEN,
    )
    s.card(
        1412,
        332,
        390,
        82,
        "Negotiation",
        "Alternative offer",
        icon="message",
        size=31,
        body=25,
        fill="#f7faff",
    )
    s.card(
        1412,
        432,
        390,
        82,
        "Verification",
        "Confirmation evidence",
        icon="shield",
        size=31,
        body=25,
        fill="#f7faff",
    )
    s.edge([(1352, 373), (1412, 373)], color="purple", conditional=True, both=True)
    s.edge(
        [(1352, 442), (1380, 442), (1380, 473), (1412, 473)],
        color="purple",
        conditional=True,
        both=True,
    )
    s.text(976, 504, "Simulation: direct checks", size=25, color=MUTED, max_width=380)

    s.card(
        972,
        562,
        360,
        82,
        "Offer Review",
        "After contact · offer",
        icon="clipboard",
        size=30,
        body=25,
        fill="#f2f6fb",
    )
    s.card(
        1432,
        562,
        390,
        82,
        "Confirmation Review",
        "After contact · evidence",
        icon="check",
        size=28,
        body=24,
        fill="#f2f6fb",
    )
    s.edge([(1316, 454), (1316, 546), (1152, 546), (1152, 562)])
    s.edge([(1332, 603), (1432, 603)])
    s.edge([(1822, 603), (1860, 603), (1860, 124), (645, 124), (645, 158)])
    s.text(1510, 109, "Return saved result", size=24, anchor="middle", max_width=400)

    s.text(
        70, 474, "03 / BACKEND DECISION", size=25, color=BLUE, weight=650, max_width=360
    )
    s.rect(70, 494, 310, 274, fill="#f4f7fa")
    for baseline, label, color in [
        (539, "Next restaurant", GREEN),
        (590, "Human approval", AMBER),
        (641, "Confirmed", GREEN),
        (692, "Failed / stopped", RED),
    ]:
        s.dot(103, baseline - 10, color, radius=7)
        s.text(126, baseline, label, size=28, max_width=232)
    s.text(126, 740, "Uncertain → reconcile", size=24, color=MUTED, max_width=240)

    s.edge([(645, 244), (645, 634)], color="purple", conditional=True, arrow=False)
    s.edge([(645, 680), (645, 686)], color="purple", conditional=True)
    s.text(669, 538, "finish", size=25, color=PURPLE, max_width=120)
    s.text(
        480, 670, "04 / POST-EXECUTION", size=25, color=BLUE, weight=650, max_width=400
    )
    s.card(
        480,
        686,
        330,
        82,
        "Memory & Summary",
        "Persist outcomes",
        icon="database",
        size=25,
        body=25,
    )
    s.card(
        972,
        686,
        360,
        82,
        "Evaluation",
        "Objective checks → END",
        icon="chart",
        size=31,
        body=24,
    )
    s.edge([(810, 727), (972, 727)])

    s.rect(48, 791, 1824, 38, fill="#f1f5f9", stroke="none", radius=12)
    s.icon(70, 799, "history", BLUE, scale=0.7)
    s.text(108, 817, "Events → Control Center replay", size=24, max_width=650)
    s.edge([(1010, 810), (1080, 810)], color="purple", conditional=True, arrow=False)
    s.text(1096, 817, "Dashed = conditional", size=24, color=MUTED, max_width=400)
    return s.finish()
