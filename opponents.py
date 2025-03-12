import json
import os
from datetime import datetime, timedelta

from botli_dataclasses import Bot, Matchmaking_Type
from enums import Challenge_Color, Perf_Type


class NoOpponentException(Exception):
    pass


class Matchmaking_Data:
    def __init__(self,
                 release_time: datetime = datetime.now(),
                 multiplier: int = 1,
                 color: Challenge_Color = Challenge_Color.WHITE
                 ) -> None:
        self.release_time = release_time
        self.multiplier = multiplier
        self.color = color

    def to_dict(self) -> dict:
        dict_ = {}
        if self.release_time > datetime.now():
            dict_['release_time'] = self.release_time.isoformat(timespec='seconds')

        if self.multiplier > 1:
            dict_['multiplier'] = self.multiplier

        if self.color == Challenge_Color.BLACK:
            dict_['color'] = Challenge_Color.BLACK.value

        return dict_


class Opponent:
    def __init__(self, username: str, data: dict[Perf_Type, Matchmaking_Data]) -> None:
        self.username = username
        self.data = data

    @classmethod
    def from_dict(cls, dict_: dict) -> 'Opponent':
        username = dict_.pop('username')

        data: dict[Perf_Type, Matchmaking_Data] = {}
        for key, value in dict_.items():
            release_time = datetime.fromisoformat(value['release_time']) if 'release_time' in value else datetime.now()
            multiplier = value.get('multiplier', 1)
            color = Challenge_Color(value['color']) if 'color' in value else Challenge_Color.WHITE

            data[Perf_Type(key)] = Matchmaking_Data(release_time, multiplier, color)

        return cls(username, data)

    def to_dict(self) -> dict:
        dict_: dict[str, str | dict] = {'username': self.username}
        for perf_type, matchmaking_data in self.data.items():
            if matchmaking_data_dict := matchmaking_data.to_dict():
                dict_[perf_type.value] = matchmaking_data_dict

        return dict_ if len(dict_) > 1 else {}

    def __eq__(self, __o: object) -> bool:
        if isinstance(__o, Opponent):
            return __o.username == self.username

        return NotImplemented


class Opponents:
    def __init__(self, delay: int, username: str) -> None:
        self.delay = timedelta(seconds=delay)
        self.matchmaking_file = f'{username}_matchmaking.json'
        self.opponent_list = self._load(self.matchmaking_file)
        self.busy_bots: list[Bot] = []
        self.last_opponent: tuple[Bot, Challenge_Color]

    def get_opponent(self,
                     online_bots: list[Bot],
                     matchmaking_type: Matchmaking_Type
                     ) -> tuple[Bot, Challenge_Color] | None:
        bots = self._filter_bots(online_bots, matchmaking_type)
        if not bots:
            raise NoOpponentException

        for bot in bots:
            if bot in self.busy_bots:
                continue

            opponent = self._find(matchmaking_type.perf_type, bot.username)
            opponent_data = opponent.data[matchmaking_type.perf_type]
            if opponent_data.color == Challenge_Color.BLACK or opponent_data.release_time <= datetime.now():
                self.last_opponent = (bot, opponent_data.color)
                return bot, opponent_data.color

        self.busy_bots.clear()

    def add_timeout(self, success: bool, game_duration: timedelta, matchmaking_type: Matchmaking_Type) -> None:
        bot, color = self.last_opponent
        opponent = self._find(matchmaking_type.perf_type, bot.username)
        opponent_data = opponent.data[matchmaking_type.perf_type]

        if success and opponent_data.multiplier > 1:
            opponent_data.multiplier //= 2
        elif not success:
            opponent_data.multiplier += 1

        timeout = (game_duration + self.delay) * matchmaking_type.multiplier * opponent_data.multiplier

        if opponent_data.release_time > datetime.now():
            opponent_data.release_time += timeout
        else:
            opponent_data.release_time = datetime.now() + timeout

        release_str = opponent_data.release_time.isoformat(sep=' ', timespec='seconds')
        print(f'{bot.username} will not be challenged to a new game pair before {release_str}.')

        if success and color == Challenge_Color.WHITE:
            opponent_data.color = Challenge_Color.BLACK
        else:
            opponent_data.color = Challenge_Color.WHITE

        if opponent not in self.opponent_list:
            self.opponent_list.append(opponent)

        self.busy_bots.clear()
        self._save(self.matchmaking_file)

    def skip_bot(self) -> None:
        self.busy_bots.append(self.last_opponent[0])

    def reset_release_time(self, perf_type: Perf_Type) -> None:
        for opponent in self.opponent_list:
            if perf_type in opponent.data:
                opponent.data[perf_type].release_time = datetime.now()

        self.busy_bots.clear()

    def _filter_bots(self, bots: list[Bot], matchmaking_type: Matchmaking_Type) -> list[Bot]:
        def bot_filter(bot: Bot) -> bool:
            if matchmaking_type.rated and bot.tos_violation:
                return False

            if abs(bot.rating_diffs[matchmaking_type.perf_type]) > matchmaking_type.max_rating_diff:
                return False

            if abs(bot.rating_diffs[matchmaking_type.perf_type]) < matchmaking_type.min_rating_diff:
                return False

            return True

        return sorted(filter(bot_filter, bots), key=lambda bot: abs(bot.rating_diffs[matchmaking_type.perf_type]))

    def _find(self, perf_type: Perf_Type, username: str) -> Opponent:
        try:
            opponent = self.opponent_list[self.opponent_list.index(Opponent(username, {}))]
        except ValueError:
            return Opponent(username, {perf_type: Matchmaking_Data()})

        if perf_type not in opponent.data:
            opponent.data[perf_type] = Matchmaking_Data()

        return opponent

    def _load(self, matchmaking_file: str) -> list[Opponent]:
        if not os.path.isfile(matchmaking_file):
            return []
            
        with open(matchmaking_file, encoding='utf-8') as file:
            try:
                data = json.load(file)
            except json.JSONDecodeError as e:
                print (f'Error while processing the file \'{matchmaking_file}\': {e}.')
                return []
            
        return [Opponent.from_dict(item) for item in data]

    def _save(self, matchmaking_file: str) -> None:
        try:
            with open(matchmaking_file, 'w', encoding='utf-8') as json_output:
                json.dump([opponent_dict
                           for opponent in self.opponent_list
                           if (opponent_dict := opponent.to_dict())], json_output)
        except PermissionError:
            print('Saving the matchmaking file failed due to missing write permissions.')
