import textwrap
from datetime import datetime, timedelta

from rich.console import Console  
from rich.style import Style  

from enums import Variant

ALIASES = {
    Variant.STANDARD: ["Standard", "Chess", "Classical", "Normal", "Std"],
    Variant.ANTICHESS: ["Antichess", "Anti"],
    Variant.ATOMIC: ["Atomic", "Atom"],
    Variant.CHESS960: ["Chess960", "960", "FRC"],
    Variant.CRAZYHOUSE: ["Crazyhouse", "House", "ZH"],
    Variant.HORDE: ["Horde"],
    Variant.KING_OF_THE_HILL: ["KOTH", "kingOfTheHill", "Hill"],
    Variant.RACING_KINGS: ["Racing", "Race", "racingkings"],
    Variant.THREE_CHECK: ["Three-check", "Threecheck", "3-check", "3check"],
}


def find_variant(name: str) -> Variant | None:
    for variant, aliases in ALIASES.items():
        if any(name.lower() == alias.lower() for alias in aliases):
            return variant


def get_future_timestamp(seconds: int) -> str:
    return (datetime.now() + timedelta(seconds=seconds)).isoformat(sep=" ", timespec="seconds")


def ml_print(prefix: str, suffix: str) -> None:
    if len(prefix) + len(suffix) <= 128:
        print(prefix + suffix)
        return

    width = 128 - len(prefix)
    indentation = " " * len(prefix)
    lines = textwrap.wrap(suffix, width=width, break_long_words=False, break_on_hyphens=False)
    print(prefix + lines[0])

    remaining_text = " ".join(lines[1:])
    subsequent_lines = textwrap.wrap(remaining_text, width=width, break_long_words=False, break_on_hyphens=False)
    for line in subsequent_lines:
        print(indentation + line)


def parse_time_control(time_control: str) -> tuple[int, int]:
    initial_time_str, increment_str = time_control.split("+")
    initial_time = int(float(initial_time_str) * 60)
    increment = int(increment_str)
    return initial_time, increment

class ColorLogger:  
    def __init__(self):  
        self.console = Console()  
        self.game_colors = {}  
        self.available_colors = [  
            "red", "green", "yellow", "blue", "magenta", "cyan",  
            "bright_red", "bright_green", "bright_yellow",   
            "bright_blue", "bright_magenta", "bright_cyan"  
        ]  
        self.color_index = 0  
      
    def assign_color(self, game_id: str) -> str:  
        if game_id not in self.game_colors:  
            self.game_colors[game_id] = self.available_colors[self.color_index % len(self.available_colors)]  
            self.color_index += 1  
        return self.game_colors[game_id]  
      
    def print(self, message: str, game_id: str | None = None):  
        if game_id:  
            color = self.assign_color(game_id)  
            self.console.print(message, style=Style(color=color))  
        else:  
            self.console.print(message)  
      
    def remove_color(self, game_id: str):  
        self.game_colors.pop(game_id, None)
