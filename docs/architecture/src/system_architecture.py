"""Light architecture with a central backend and two physical SQLite files."""

from .svg import BLUE, CYAN, GREEN, MUTED, PURPLE, SVG


def draw():
    s = SVG(
        "System architecture",
        "BARIA Electron desktop uses React and TypeScript. Electron Main connects through authenticated REST and WebSocket to FastAPI. LangGraph coordinates scoped tools; BookingExecutionService owns booking state. Observability records events in application SQLite, with a separate SQLite checkpoint file. A separate FastAPI voice gateway shares a SQLite mailbox with the booking backend and integrates OpenAI Live and Twilio. Manual Overpass imports supply cached OpenStreetMap restaurant data. Application DB and Event Store are logical groups within one physical file.",
    )
    s.group(48, 150, 340, 670, "Tech stack")
    for y, title, detail, icon, color in [
        (224, "React · TypeScript", "Desktop · Electron", "atom", CYAN),
        (360, "FastAPI · Python", "Backend & services", "bolt", GREEN),
        (496, "LangGraph", "Agent orchestration", "graph", PURPLE),
        (632, "SQLite", "State & checkpoints", "database", BLUE),
    ]:
        s.icon(78, y + 5, icon, color, scale=1.25)
        s.text(138, y + 24, title, size=26, weight=650, max_width=230)
        s.text(138, y + 61, detail, size=24, color=MUTED, max_width=230)
    s.text(78, 783, "Local-first desktop", size=25, color=MUTED, max_width=280)

    s.group(
        440,
        150,
        990,
        164,
        "Desktop Application",
        icon="desktop",
        fill="url(#blue-card)",
    )
    s.card(
        466,
        218,
        448,
        84,
        "Booking Application",
        "Discovery & booking setup",
        icon="browser",
        size=29,
        body=24,
        fill="#f7fbff",
    )
    s.card(
        944,
        218,
        460,
        84,
        "AI Control Center",
        "Calls, traces & analytics",
        icon="chart",
        size=29,
        body=24,
        fill="#f7fbff",
    )
    s.edge([(630, 314), (630, 382)], both=True)
    s.edge([(1190, 314), (1190, 382)], both=True)
    s.text(930, 358, "REST / WebSocket", size=25, anchor="middle", max_width=320)

    s.group(
        440, 382, 990, 230, "Backend Core", icon="gear", fill="#eef6ed", color=GREEN
    )
    s.card(
        466,
        439,
        260,
        80,
        "FastAPI API",
        "REST · WS · Auth",
        icon="code",
        size=25,
        body=24,
        color="#a6c5ac",
        fill="#f9fcf8",
    )
    s.card(
        758,
        439,
        286,
        80,
        "LangGraph",
        "Supervisor & agents",
        icon="graph",
        size=28,
        body=22,
        color="#a6c5ac",
        fill="#f9fcf8",
    )
    s.card(
        1076,
        439,
        328,
        80,
        "Booking Execution",
        "Service · booking policies",
        icon="layers",
        size=25,
        body=22,
        color="#a6c5ac",
        fill="#f9fcf8",
    )
    s.edge([(726, 479), (758, 479)], both=True)
    s.edge([(1044, 479), (1076, 479)], both=True)
    s.rect(478, 548, 914, 42, fill="#e0efdf", stroke="#a6c5ac", radius=14)
    s.icon(682, 554, "wave", BLUE, scale=0.9)
    s.text(730, 578, "Observability", size=26, weight=650, max_width=210)
    s.text(945, 578, "Events · traces · replay", size=25, color=MUTED, max_width=390)
    for x in (596, 901, 1240):
        s.edge([(x, 519), (x, 548)], color="green")

    s.group(
        440,
        678,
        990,
        142,
        "Data & Persistence",
        icon="database",
        fill="#f0effa",
        color=PURPLE,
    )
    s.card(
        466,
        736,
        290,
        76,
        "Application DB",
        "Bookings · state",
        icon="database",
        size=26,
        body=23,
        fill="#faf9ff",
        color="#b7b5d7",
    )
    s.card(
        780,
        736,
        290,
        76,
        "Event Store",
        "Same SQLite file",
        icon="layers",
        size=26,
        body=23,
        fill="#faf9ff",
        color="#b7b5d7",
    )
    s.card(
        1094,
        736,
        310,
        76,
        "Checkpoints",
        "Separate SQLite file",
        icon="clipboard",
        size=26,
        body=23,
        fill="#faf9ff",
        color="#b7b5d7",
    )
    s.edge([(630, 612), (630, 678)], both=True)
    s.edge([(1240, 612), (1240, 678)], both=True)
    s.text(930, 654, "SQL · SQLite", size=25, anchor="middle", max_width=250)

    s.group(1518, 150, 354, 670, "External Integrations", icon="link", size=26)
    s.rect(1538, 218, 314, 355, fill="#e9eff6", stroke="#d0dce8", radius=18)
    s.icon(1554, 232, "phone", BLUE, scale=0.8)
    s.text(1594, 254, "Voice & Telephony", size=26, weight=650, max_width=235)
    s.card(
        1554,
        276,
        282,
        76,
        "FastAPI gateway",
        "Voice adapter",
        icon="phone",
        size=25,
        body=23,
        fill="#f9fbfd",
    )
    s.card(
        1554,
        363,
        282,
        80,
        "OpenAI Live",
        "Live voice",
        icon="wave",
        size=27,
        body=23,
        fill="#f9fbfd",
    )
    s.card(
        1554,
        457,
        282,
        80,
        "Twilio",
        "Calls · media",
        icon="phone",
        size=27,
        body=23,
        fill="#f9fbfd",
    )
    s.edge([(1360, 439), (1360, 350), (1480, 350), (1480, 308), (1554, 308)], both=True)
    s.text(1380, 338, "SQLite mailbox", size=24, anchor="middle", max_width=230)
    s.edge([(1836, 308), (1844, 308), (1844, 399), (1836, 399)], both=True)
    s.edge([(1836, 308), (1849, 308), (1849, 493), (1836, 493)], both=True)

    s.rect(1538, 600, 314, 214, fill="#e9eff6", stroke="#d0dce8", radius=18)
    s.icon(1554, 608, "pin", BLUE, scale=0.75)
    s.text(1594, 630, "Restaurant Data", size=26, weight=650, max_width=235)
    s.card(
        1554,
        640,
        282,
        76,
        "OpenStreetMap",
        "Restaurant data",
        icon="pin",
        size=25,
        body=23,
        fill="#f9fbfd",
    )
    s.card(
        1554,
        728,
        282,
        76,
        "Overpass API",
        "Import · caching",
        icon="layers",
        size=25,
        body=23,
        fill="#f9fbfd",
    )
    s.edge([(1554, 752), (1488, 752), (1488, 532), (1430, 532)])
    s.text(1390, 645, "HTTPS import", size=24, anchor="middle", max_width=190)
    return s.finish()
