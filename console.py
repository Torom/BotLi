from itertools import cycle
from rich.console import Console

console = Console()

COLORS = ["cyan", "magenta", "green", "yellow", "blue", "bright_white"]
_color_cycle = cycle(COLORS)

def cprint(msg: str) -> None:
    color = next(_color_cycle)
    console.print(f"[{color}]{msg}[/{color}]")
