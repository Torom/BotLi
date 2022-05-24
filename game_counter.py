class Game_Counter:
    def __init__(self, max_games: int, initial: int = 0) -> None:
        self.max_games = max_games
        self.counter = initial

    def increment(self) -> bool:
        if self.is_max():
            return False
        self.counter += 1
        return True

    def decrement(self) -> None:
        self.counter -= 1
        if self.counter < 0:
            raise RuntimeError

    def is_max(self, additional_count: int = 0) -> bool:
        return self.counter + additional_count >= self.max_games
