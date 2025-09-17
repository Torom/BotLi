from rich.text import Text
from itertools import cycle
from rich.console import Console

console = Console()

def parse_time_control(time_control: str) -> tuple[int, int]:
    initial_time_str, increment_str = time_control.split('+')
    initial_time = int(float(initial_time_str) * 60)
    increment = int(increment_str)
    return initial_time, increment

GAME_COLORS = ["cyan", "yellow", "magenta", "green", "blue", "white"]

_game_color_map: dict[str, str] = {}
_color_index = 0

def get_game_color(game_id: str) -> str:
    global _color_index
    if game_id not in _game_color_map:
        _game_color_map[game_id] = GAME_COLORS[_color_index % len(GAME_COLORS)]
        _color_index += 1
    return _game_color_map[game_id]

def game_colour(game_id: str, message: str) -> Text:
    return Text(message, style=get_game_color(game_id))

def game_print(msg: str, game_id: str) -> None:
    console.print(game_colour(game_id, msg))

COLORS = ["cyan", "magenta", "green", "yellow", "blue", "bright_white"]
_color_cycle = cycle(COLORS)

def cprint(msg: str) -> None:
    color = next(_color_cycle)
    console.print(f"[{color}]{msg}[/{color}]")
