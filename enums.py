from enum import Enum


class Challenge_Color(Enum):
    WHITE = 'white'
    BLACK = 'black'
    RANDOM = 'random'


class Decline_Reason(Enum):
    GENERIC = 'generic'
    LATER = 'later'
    TOO_FAST = 'tooFast'
    TOO_SLOW = 'tooSlow'
    TIME_CONTROL = 'timeControl'
    RATED = 'rated'
    CASUAL = 'casual'
    STANDARD = 'standard'
    VARIANT = 'variant'
    NO_BOT = 'noBot'
    ONYL_BOT = 'onlyBot'


class Variant(Enum):
    STANDARD = 'standard'
    FROM_POSITION = 'fromPosition'
    ANTICHESS = 'antichess'
    ATOMIC = 'atomic'
    CHESS960 = 'chess960'
    CRAZYHOUSE = 'crazyhouse'
    HORDE = 'horde'
    KING_OF_THE_HILL = 'kingOfTheHill'
    RACING_KINGS = 'racingKings'
    THREE_CHECK = 'threeCheck'
