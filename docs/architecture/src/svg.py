"""Shared native-vector vocabulary for BARIA's light architecture diagrams."""

from html import escape

INK, MUTED = "#122a46", "#47617a"
BLUE, CYAN, PURPLE = "#365d83", "#387b9b", "#62628c"
GREEN, AMBER, RED = "#378468", "#bc8b31", "#d87378"
BG, SURFACE, BORDER = "#fcfdff", "#f5f8fc", "#b9cbdc"
WIDTH, HEIGHT = 1920, 840
COLORS = {"blue": BLUE, "cyan": CYAN, "purple": PURPLE, "green": GREEN, "amber": AMBER}


class SVG:
    def __init__(self, heading, description):
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title description">',
            f'<title id="title">{escape("BARIA — AI Restaurant Booker · " + heading)}</title>',
            f'<desc id="description">{escape(description)}</desc>',
            '<defs><style>text{font-family:"Segoe UI",Arial,sans-serif}</style>',
        ]
        for name, first, last in [
            ("blue-card", "#eef6ff", "#e0efff"),
            ("green-card", "#eaf5e8", "#dcefdc"),
            ("amber-card", "#fff8e6", "#fff0cf"),
            ("brand", "#507fa4", "#234867"),
        ]:
            self.parts.append(
                f'<linearGradient id="{name}" x2="0" y2="1"><stop stop-color="{first}"/><stop offset="1" stop-color="{last}"/></linearGradient>'
            )
        for name, color in COLORS.items():
            self.parts.append(
                f'<marker id="{name}" viewBox="0 0 12 12" refX="10" refY="6" markerWidth="10" markerHeight="10" orient="auto-start-reverse" markerUnits="userSpaceOnUse"><path d="M 2 2 L 10 6 L 2 10 Z" fill="{color}"/></marker>'
            )
        self.parts.append("</defs>")
        self.rect(0, 0, WIDTH, HEIGHT, fill=BG, stroke="none", radius=0)
        self.rect(48, 28, 64, 64, fill="url(#brand)", stroke="none", radius=16)
        self.icon(64, 43, "cutlery", "#ffffff")
        self.text(
            134, 45, "BARIA — AI Restaurant Booker", size=25, weight=600, max_width=650
        )
        self.text(132, 104, heading, size=46, weight=700, max_width=900)

    def rect(self, x, y, w, h, *, fill=SURFACE, stroke=BORDER, radius=17):
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
        )

    def text(
        self,
        x,
        y,
        value,
        *,
        size=26,
        color=INK,
        weight=400,
        anchor="start",
        max_width=1792,
    ):
        self.parts.append(
            f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}" text-anchor="{anchor}" data-max-width="{max_width}">{escape(value)}</text>'
        )

    def group(self, x, y, w, h, title, *, fill=SURFACE, color=BLUE, icon=None, size=29):
        self.rect(x, y, w, h, fill=fill, radius=22)
        inset = 28
        if icon:
            self.icon(x + 24, y + 20, icon, color)
            inset = 72
        self.text(
            x + inset, y + 43, title, size=size, weight=650, max_width=w - inset - 24
        )

    def card(
        self,
        x,
        y,
        w,
        h,
        title,
        subtitle,
        *,
        icon=None,
        color=BLUE,
        fill="url(#blue-card)",
        size=30,
        body=25,
    ):
        self.parts.append(
            f'<g data-card="{escape(title, quote=True)}" data-x="{x}" data-y="{y}" data-width="{w}" data-height="{h}">'
        )
        self.rect(x, y, w, h, fill=fill, stroke=color, radius=16)
        inset = 24
        if icon:
            self.icon(x + 20, y + (h - 32) / 2, icon, BLUE)
            inset = 64
        title_y, subtitle_y = (
            (y + 46, y + h - 22) if h > 95 else (y + size + 7, y + h - 10)
        )
        self.text(
            x + inset, title_y, title, size=size, weight=650, max_width=w - inset - 18
        )
        self.text(
            x + inset,
            subtitle_y,
            subtitle,
            size=body,
            color=MUTED,
            max_width=w - inset - 18,
        )
        self.parts.append("</g>")

    def edge(self, points, *, color="blue", conditional=False, both=False, arrow=True):
        path = "M " + " L ".join(f"{x} {y}" for x, y in points)
        dash = ' stroke-dasharray="8 7"' if conditional else ""
        start = f' marker-start="url(#{color})"' if both else ""
        end = f' marker-end="url(#{color})"' if arrow else ""
        self.parts.append(
            f'<path data-connector="true" d="{path}" fill="none" stroke="{COLORS[color]}" stroke-width="2.3" stroke-linejoin="round" stroke-linecap="round"{end}{start}{dash}/>'
        )

    def dot(self, x, y, color=BLUE, radius=6):
        self.parts.append(f'<circle cx="{x}" cy="{y}" r="{radius}" fill="{color}"/>')

    def pill(self, x, y, w, label, icon):
        self.rect(x, y, w, 46, fill="#f4f7fb", stroke="#d5dfea", radius=15)
        self.icon(x + 15, y + 8, icon, BLUE, scale=0.9)
        self.text(x + 57, y + 30, label, size=24, max_width=w - 71)

    def icon(self, x, y, name, color=BLUE, scale=1):
        """Original editable line icons, with no third-party image assets."""
        paths = {
            "cutlery": '<path d="M 3 2 V 10 Q 3 16 9 16 V 30 M 9 2 V 12 M 15 2 V 10 Q 15 16 9 16 M 27 2 Q 20 8 23 18 H 29 M 29 2 V 30"/>',
            "desktop": '<path d="M 5 3 H 27 V 22 H 5 Z M 1 27 H 31 L 27 22 H 5 Z"/>',
            "browser": '<rect x="2" y="3" width="28" height="25" rx="3"/><path d="M 2 10 H 30 M 7 6 H 8 M 12 6 H 13"/>',
            "code": '<path d="M 10 6 L 2 16 L 10 26 M 22 6 L 30 16 L 22 26 M 19 3 L 13 29"/>',
            "graph": '<circle cx="16" cy="5" r="4"/><circle cx="5" cy="27" r="4"/><circle cx="27" cy="27" r="4"/><path d="M 16 9 V 17 M 5 23 V 17 H 27 V 23"/>',
            "layers": '<path d="M 2 9 L 16 2 L 30 9 L 16 16 Z M 2 16 L 16 23 L 30 16 M 2 23 L 16 30 L 30 23"/>',
            "database": '<ellipse cx="16" cy="6" rx="14" ry="5"/><path d="M 2 6 V 25 C 2 32 30 32 30 25 V 6 M 2 15 C 2 22 30 22 30 15"/>',
            "phone": '<path d="M 8 2 L 3 6 C 1 15 17 31 26 29 L 30 24 L 22 18 L 18 22 C 13 20 10 17 8 12 L 12 8 Z M 20 3 Q 29 3 29 12 M 20 8 Q 24 8 24 12"/>',
            "history": '<path d="M 3 12 A 14 14 0 1 1 4 24 M 3 3 V 12 H 12 M 17 8 V 17 L 23 21"/>',
            "calendar": '<rect x="2" y="6" width="28" height="24" rx="3"/><path d="M 2 13 H 30 M 9 2 V 10 M 23 2 V 10"/>',
            "search": '<circle cx="13" cy="13" r="10"/><path d="M 21 21 L 30 30"/>',
            "human": '<circle cx="16" cy="8" r="6"/><path d="M 3 30 V 25 C 3 13 29 13 29 25 V 30 Z"/>',
            "message": '<path d="M 6 3 H 26 Q 30 3 30 7 V 21 Q 30 25 26 25 H 15 L 7 31 V 25 H 6 Q 2 25 2 21 V 7 Q 2 3 6 3 Z M 9 13 H 10 M 15 13 H 16 M 21 13 H 22"/>',
            "shield": '<path d="M 16 2 L 29 7 V 17 Q 29 26 16 31 Q 3 26 3 17 V 7 Z M 9 16 L 14 21 L 24 11"/>',
            "clipboard": '<rect x="4" y="5" width="24" height="25" rx="3"/><rect x="10" y="1" width="12" height="8" rx="2"/><path d="M 10 16 H 22 M 10 22 H 22"/>',
            "check": '<rect x="4" y="5" width="24" height="25" rx="3"/><rect x="10" y="1" width="12" height="8" rx="2"/><path d="M 10 19 L 14 23 L 23 14"/>',
            "chart": '<path d="M 4 29 V 18 H 9 V 29 Z M 14 29 V 10 H 19 V 29 Z M 24 29 V 2 H 29 V 29 Z"/>',
            "wave": '<path d="M 1 17 H 7 L 11 7 L 16 26 L 21 3 L 25 17 H 31"/>',
            "gear": '<path d="M 12 2 H 20 L 21 7 L 26 8 L 30 14 L 26 18 L 26 24 L 19 27 L 16 31 L 12 27 L 6 26 L 3 19 L 1 15 L 6 11 L 7 6 Z"/><circle cx="16" cy="16" r="5"/>',
            "link": '<path d="M 12 21 L 21 12 M 10 15 L 6 19 A 6 6 0 0 0 14 28 L 20 22 M 13 10 L 19 4 A 6 6 0 0 1 28 13 L 23 18"/>',
            "pin": '<path d="M 16 31 Q 3 17 3 12 A 13 11 0 0 1 29 12 Q 29 17 16 31 Z"/><circle cx="16" cy="12" r="4"/>',
            "atom": '<ellipse cx="16" cy="16" rx="15" ry="6"/><ellipse cx="16" cy="16" rx="15" ry="6" transform="rotate(60 16 16)"/><ellipse cx="16" cy="16" rx="15" ry="6" transform="rotate(120 16 16)"/><circle cx="16" cy="16" r="2"/>',
            "bolt": '<path d="M 18 1 L 5 18 H 15 L 13 31 L 28 12 H 18 Z"/>',
        }
        self.parts.append(
            f'<g transform="translate({x} {y}) scale({scale})" fill="none" stroke="{color}" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round">{paths[name]}</g>'
        )

    def finish(self):
        return "\n".join(self.parts + ["</svg>", ""])
