import textwrap
from datetime import datetime, timedelta

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
