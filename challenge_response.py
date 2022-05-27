from aliases import Challenge_ID


class Challenge_Response:
    def __init__(
        self,
        challenge_id: Challenge_ID | None = None,
        success: bool = False,
        has_reached_rate_limit: bool = False
    ) -> None:
        self.challenge_id = challenge_id
        self.success = success
        self.has_reached_rate_limit = has_reached_rate_limit
