from enum import Enum


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
