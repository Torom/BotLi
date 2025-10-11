from enum import StrEnum


class ChallengeColor(StrEnum):
    WHITE = "white"
    BLACK = "black"
    RANDOM = "random"


class DeclineReason(StrEnum):
    GENERIC = "generic"
    LATER = "later"
    TOO_FAST = "tooFast"
    TOO_SLOW = "tooSlow"
    TIME_CONTROL = "timeControl"
    RATED = "rated"
    CASUAL = "casual"
    STANDARD = "standard"
    VARIANT = "variant"
    NO_BOT = "noBot"
    ONLY_BOT = "onlyBot"


class Variant(StrEnum):
    STANDARD = "standard"
    FROM_POSITION = "fromPosition"
    ANTICHESS = "antichess"
    ATOMIC = "atomic"
    CHESS960 = "chess960"
    CRAZYHOUSE = "crazyhouse"
    HORDE = "horde"
    KING_OF_THE_HILL = "kingOfTheHill"
    RACING_KINGS = "racingKings"
    THREE_CHECK = "threeCheck"


class PerfType(StrEnum):
    BULLET = "bullet"
    BLITZ = "blitz"
    RAPID = "rapid"
    CLASSICAL = "classical"
    ANTICHESS = "antichess"
    ATOMIC = "atomic"
    CHESS960 = "chess960"
    CRAZYHOUSE = "crazyhouse"
    HORDE = "horde"
    KING_OF_THE_HILL = "kingOfTheHill"
    RACING_KINGS = "racingKings"
    THREE_CHECK = "threeCheck"


class BusyReason(StrEnum):
    OFFLINE = "offline"
    PLAYING = "playing"
