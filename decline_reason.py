from enum import Enum


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
