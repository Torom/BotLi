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

def show_logo(text: str, version: str | None = None, _color_index=None, **kwargs):
    if _color_index is None:
        _color_index = [0]

    colors = ["magenta", "cyan", "green", "yellow", "blue", "red"]

    for line in text.splitlines():
        if line.strip():
            console.print(Text(line, style=colors[_color_index[0] % len(colors)]), **kwargs)
            _color_index[0] += 1
        else:
            console.print()

    tagline = Text("BotLi", style="bold magenta")
    if version:
        tagline.append(f" • {version}", style="cyan")
    console.print(tagline, **kwargs, justify="center")
