from itertools import cycle

from rich.console import Console
from rich.text import Text

console = Console()


def parse_time_control(time_control: str) -> tuple[int, int]:
    initial_time_str, increment_str = time_control.split("+")
    initial_time = int(float(initial_time_str) * 60)
    increment = int(increment_str)
    return initial_time, increment


GAME_COLORS = ["cyan", "yellow", "magenta", "green", "blue", "white"]
_color_cycle = cycle(GAME_COLORS)
_game_color_map: dict[str, str] = {}


def get_game_color(game_id: str) -> str:
    if game_id not in _game_color_map:
        _game_color_map[game_id] = next(_color_cycle)
    return _game_color_map[game_id]


def game_colour(game_id: str, message: str) -> Text:
    return Text(message, style=get_game_color(game_id))


def game_print(msg: str, game_id: str) -> None:
    console.print(game_colour(game_id, msg))
