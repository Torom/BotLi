from dataclasses import dataclass

from aliases import Challenge_ID
from enums import Challenge_Color, Variant


@dataclass
class API_Challenge_Reponse:
    challenge_id: Challenge_ID | None = None
    was_accepted: bool = False
    error: str | None = None
    was_declined: bool = False
    has_timed_out: bool = False
    has_reached_rate_limit: bool = False


@dataclass
class Challenge_Request:
    opponent_username: str
    initial_time: int
    increment: int
    rated: bool
    color: Challenge_Color
    variant: Variant
    timeout: int

    def __eq__(self, __o: object) -> bool:
        if isinstance(__o, Challenge_Request):
            return __o.opponent_username == self.opponent_username

        raise NotImplemented


@dataclass
class Challenge_Response:
    challenge_id: Challenge_ID | None = None
    success: bool = False
    has_reached_rate_limit: bool = False
