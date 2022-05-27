from enums import Challenge_Color, Variant


class Challenge_Request:
    def __init__(
        self,
        opponent_username: str,
        initial_time: int,
        increment: int,
        rated: bool,
        color: Challenge_Color,
        variant: Variant,
        timeout: int
    ) -> None:
        self.opponent_username = opponent_username
        self.initial_time = initial_time
        self.increment = increment
        self.rated = rated
        self.color = color
        self.variant = variant
        self.timeout = timeout
