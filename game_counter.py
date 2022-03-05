from threading import RLock
from time import sleep


class Game_Counter:
    def __init__(self, max_games: int, initial: int = 0) -> None:
        self.max_games = max_games
        self.counter = initial
        self.lock = RLock()

    def increment(self) -> bool:
        with self.lock:
            if self.is_max():
                return False
            self.counter += 1
            return True

    def decrement(self) -> None:
        with self.lock:
            self.counter -= 1
            if self.counter < 0:
                raise RuntimeError

    def is_max(self) -> bool:
        with self.lock:
            return self.counter >= self.max_games

    def wait_for_increment(self) -> None:
        while not self.increment():
            sleep(2)
