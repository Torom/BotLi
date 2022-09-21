import json
import os
from datetime import datetime, timedelta

from enums import Perf_Type


class Matchmaking_Value:
    def __init__(self, release_time: datetime = datetime.now(), multiplier: int = 1) -> None:
        self.release_time = release_time
        self.multiplier = multiplier

    def __dict__(self) -> dict:
        return {'release_time': self.release_time.isoformat(timespec='seconds'),
                'multiplier': self.multiplier}


class Opponent:
    def __init__(self, username: str, values: dict[Perf_Type, Matchmaking_Value]) -> None:
        self.username = username
        self.values = values

    @classmethod
    def from_dict(cls, dict_: dict) -> 'Opponent':
        username = dict_['username']

        categories: dict[Perf_Type, Matchmaking_Value] = {}
        for key, value in dict_.items():
            if key == 'username':
                continue

            categories[Perf_Type(key)] = Matchmaking_Value(
                release_time=datetime.fromisoformat(value['release_time']), multiplier=value['multiplier'])

        return Opponent(username, categories)

    def __dict__(self) -> dict:
        dict_ = {'username': self.username}
        dict_.update({category.value: value.__dict__() for category, value in self.values.items()})

        return dict_

    def __eq__(self, o: object) -> bool:
        if isinstance(o, Opponent):
            return self.username == o.username
        else:
            raise NotImplemented


class Opponents:
    def __init__(self, perf_type: Perf_Type, estimated_game_duration: timedelta, delay: int) -> None:
        self.perf_type = perf_type
        self.estimated_game_duration = estimated_game_duration
        self.delay = timedelta(seconds=delay)
        self.opponent_list = self._load()

    def next_opponent(self, online_bots: list[dict]) -> dict:
        for bot in online_bots:
            opponent = self._find(bot['username'])
            if opponent.values[self.perf_type].release_time <= datetime.now():
                return bot

        self.reset_release_time()
        print('matchmaking reseted')

        return self.next_opponent(online_bots)

    def add_timeout(self, username: str, success: bool, game_duration: timedelta, challenge_duration: timedelta) -> None:
        opponent = self._find(username)
        opponent_value = opponent.values[self.perf_type]

        if success and opponent_value.multiplier > 1:
            opponent_value.multiplier //= 2
        elif not success:
            opponent_value.multiplier += 1

        multiplier = opponent_value.multiplier if opponent_value.multiplier >= 5 else 1
        duration_ratio = game_duration / self.estimated_game_duration
        timeout = duration_ratio ** 2 * (self.estimated_game_duration + self.delay + challenge_duration) * 20 * multiplier

        if opponent_value.release_time > datetime.now():
            timeout += opponent_value.release_time - datetime.now()

        opponent_value.release_time = datetime.now() + timeout
        release_str = opponent_value.release_time.isoformat(sep=" ", timespec="seconds")
        print(f'{username} will not be challenged to a new game pair before {release_str}.')

        if opponent not in self.opponent_list:
            self.opponent_list.append(opponent)

        self._save()

    def reset_release_time(self, full_reset: bool = False) -> None:
        for opponent in self.opponent_list:
            if self.perf_type in opponent.values:
                if full_reset or opponent.values[self.perf_type].multiplier == 1:
                    opponent.values[self.perf_type].release_time = datetime.now()

    def _find(self, username: str) -> Opponent:
        try:
            opponent = self.opponent_list[self.opponent_list.index(Opponent(username, {}))]

            if self.perf_type in opponent.values:
                return opponent
            else:
                opponent.values[self.perf_type] = Matchmaking_Value()
                return opponent
        except ValueError:
            return Opponent(username, {self.perf_type: Matchmaking_Value()})

    def _load(self) -> list[Opponent]:
        if os.path.isfile('matchmaking.json'):
            with open('matchmaking.json', 'r') as input:
                return [Opponent.from_dict(opponent) for opponent in json.load(input)]
        else:
            return []

    def _save(self) -> None:
        with open('matchmaking.json', 'w') as output:
            json.dump([opponent.__dict__() for opponent in self.opponent_list], output, indent=4)
