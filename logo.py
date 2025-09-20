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

def show_logo(logo_text: str, version: str | None = None):
    colors = ["magenta", "cyan", "green", "yellow", "blue", "red"]
    for i, line in enumerate(logo_text.splitlines()):
        if line.strip():
            console.print(Text(line, style=colors[i % len(colors)]))
        else:
            console.print()

    tagline = Text("BotLi", style="bold magenta")
    if version:
        tagline.append(f" • {version}", style="cyan")
    console.print(tagline, justify="center")
