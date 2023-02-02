import json
import os
import random
from datetime import datetime, timedelta

from aliases import As_White
from botli_dataclasses import Bot
from enums import Perf_Type


class Matchmaking_Data:
    def __init__(self, release_time: datetime = datetime.now(), multiplier: int = 1, as_white: bool = True) -> None:
        self.release_time = release_time
        self.multiplier = multiplier
        self.as_white = as_white

    def __dict__(self) -> dict:
        return {'release_time': self.release_time.isoformat(timespec='seconds'),
                'multiplier': self.multiplier}


class Opponent:
    def __init__(self, username: str, data: dict[Perf_Type, Matchmaking_Data]) -> None:
        self.username = username
        self.data = data

    @classmethod
    def from_dict(cls, dict_: dict) -> 'Opponent':
        username = dict_.pop('username')

        data: dict[Perf_Type, Matchmaking_Data] = {}
        for key, value in dict_.items():
            release_time = datetime.fromisoformat(value['release_time'])
            data[Perf_Type(key)] = Matchmaking_Data(release_time, value['multiplier'])

        return Opponent(username, data)

    def __dict__(self) -> dict:
        dict_ = {'username': self.username}
        dict_.update({perf_type.value: data.__dict__() for perf_type, data in self.data.items()})

        return dict_

    def __eq__(self, __o: object) -> bool:
        if isinstance(__o, Opponent):
            return __o.username == self.username

        return NotImplemented


class Opponents:
    def __init__(self, perf_types: list[Perf_Type], estimated_game_duration: timedelta, delay: int) -> None:
        self.perf_types = perf_types
        self.estimated_game_duration = estimated_game_duration
        self.delay = timedelta(seconds=delay)
        self.opponent_list = self._load()
        self.busy_bots: list[Bot] = []
        self.last_opponent: tuple[Bot, Perf_Type, As_White] | None = None

    def get_next_opponent(self, online_bots: dict[Perf_Type, list[Bot]]) -> tuple[Bot, Perf_Type, As_White]:
        perf_type = random.choice(self.perf_types)

        for bot in sorted(online_bots[perf_type], key=lambda bot: abs(bot.rating_diff)):
            opponent = self._find(perf_type, bot.username)
            opponent_data = opponent.data[perf_type]
            if bot in self.busy_bots:
                continue
            if not opponent_data.as_white or opponent_data.release_time <= datetime.now():
                self.last_opponent = (bot, perf_type, opponent_data.as_white)
                return (bot, perf_type, opponent_data.as_white)

        print('Resetting matchmaking ...')
        self.reset_release_time(perf_type)

        return self.get_next_opponent(online_bots)

    def add_timeout(self, success: bool, game_duration: timedelta) -> None:
        assert self.last_opponent

        bot, perf_type, as_white = self.last_opponent
        opponent = self._find(perf_type, bot.username)
        opponent_data = opponent.data[perf_type]

        if success and opponent_data.multiplier > 1:
            opponent_data.multiplier //= 2
        elif not success:
            opponent_data.multiplier += 1

        multiplier = opponent_data.multiplier if opponent_data.multiplier >= 5 else 1
        duration_ratio = game_duration / self.estimated_game_duration
        timeout = (duration_ratio ** 2 * self.estimated_game_duration + self.delay) * 10 * multiplier

        if opponent_data.release_time > datetime.now():
            timeout += opponent_data.release_time - datetime.now()

        opponent_data.release_time = datetime.now() + timeout
        release_str = opponent_data.release_time.isoformat(sep=" ", timespec="seconds")
        print(f'{bot.username} will not be challenged to a new game pair before {release_str}.')

        if success:
            opponent_data.as_white = not as_white
        else:
            opponent_data.as_white = True

        if opponent not in self.opponent_list:
            self.opponent_list.append(opponent)

        self.busy_bots.clear()
        self._save()

    def skip_bot(self) -> None:
        assert self.last_opponent

        self.busy_bots.append(self.last_opponent[0])

    def reset_release_time(self, perf_type: Perf_Type, full_reset: bool = False) -> None:
        for opponent in self.opponent_list:
            if perf_type in opponent.data:
                if full_reset or opponent.data[perf_type].multiplier < 5:
                    opponent.data[perf_type].release_time = datetime.now()

        self.busy_bots.clear()

    def _find(self, perf_type: Perf_Type, username: str) -> Opponent:
        try:
            opponent = self.opponent_list[self.opponent_list.index(Opponent(username, {}))]

            if perf_type in opponent.data:
                return opponent
            else:
                opponent.data[perf_type] = Matchmaking_Data()
                return opponent
        except ValueError:
            return Opponent(username, {perf_type: Matchmaking_Data()})

    def _load(self) -> list[Opponent]:
        if os.path.isfile('matchmaking.json'):
            with open('matchmaking.json', encoding='utf-8') as json_input:
                return [Opponent.from_dict(opponent) for opponent in json.load(json_input)]
        else:
            return []

    def _save(self) -> None:
        with open('matchmaking.json', 'w', encoding='utf-8') as json_output:
            json.dump([opponent.__dict__() for opponent in self.opponent_list], json_output, indent=4)
