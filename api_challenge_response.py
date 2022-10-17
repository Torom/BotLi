from dataclasses import dataclass

from aliases import Challenge_ID


@dataclass
class API_Challenge_Reponse:
    challenge_id: Challenge_ID | None = None
    was_accepted: bool = False
    error: str | None = None
    was_declined: bool = False
    has_timed_out: bool = False
    has_reached_rate_limit: bool = False
