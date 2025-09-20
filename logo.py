from itertools import cycle
from rich.console import Console
from rich.text import Text

console = Console()

LOGO = r"""
______       _   _     _
| ___ \     | | | |   (_)
| |_/ / ___ | |_| |    _
| ___ \/ _ \| __| |   | |
| |_/ / (_) | |_| |___| |
\____/ \___/ \__\_____/_|"""

_COLORS = ["magenta", "cyan", "green", "yellow", "blue", "red"]
_color_cycle = cycle(_COLORS)

def show_logo(text: str, version: str | None = None, **kwargs):
    for line in text.splitlines():
        if line.strip():
            console.print(Text(line, style=next(_color_cycle)), **kwargs)
        else:
            console.print()
    tagline = Text("BotLi", style="bold magenta")
    if version:
        tagline.append(f" • {version}", style="cyan")
    console.print(tagline, **kwargs, justify="center")
