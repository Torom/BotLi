from rich.console import Console

console = Console()

COLORS = ["cyan", "magenta", "green", "yellow", "blue", "bright_white"]
_color_index = 0

def cprint(msg: str) -> None:
    global _color_index
    color = COLORS[_color_index]
    console.print(f"[{color}]{msg}[/{color}]")
    _color_index = (_color_index + 1) % len(COLORS)
