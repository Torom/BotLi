from aliases import Challenge_ID


class Challenge_Reponse:
    def __init__(
        self,
        challenge_id: Challenge_ID | None = None,
        was_accepted: bool = False,
        error: str | None = None,
        was_declined: bool = False,
        has_timed_out: bool = False,
        has_reached_rate_limit: bool = False
    ) -> None:
        self.challenge_id = challenge_id
        self.was_accepted = was_accepted
        self.error = error
        self.was_declined = was_declined
        self.has_timed_out = has_timed_out
        self.has_reached_rate_limit = has_reached_rate_limit
