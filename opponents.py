import json
import os
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from botli_dataclasses import Bot, Matchmaking_Data, Matchmaking_Type
from enums import Challenge_Color, Perf_Type
from exceptions import NoOpponentException


class Opponents:
    def __init__(self, delay: int, username: str) -> None:
        self.delay = timedelta(seconds=delay)
        self.matchmaking_file = f'{username}_matchmaking.json'
        self.opponent_dict = self._load(self.matchmaking_file)
        self.busy_bots: list[Bot] = []
        self.last_opponent: tuple[str, Challenge_Color, Matchmaking_Type]

    def get_opponent(self,
                     online_bots: list[Bot],
                     matchmaking_type: Matchmaking_Type) -> tuple[Bot, Challenge_Color] | None:
        for bot in self._filter_bots(online_bots, matchmaking_type):
            if bot in self.busy_bots:
                continue

            data = self.opponent_dict[bot.username][matchmaking_type.perf_type]
            if data.color == Challenge_Color.BLACK or data.release_time <= datetime.now():
                self.last_opponent = (bot.username, data.color, matchmaking_type)
                return bot, data.color

        self.busy_bots.clear()

    def add_timeout(self, success: bool, game_duration: timedelta) -> None:
        username, color, matchmaking_type = self.last_opponent
        data = self.opponent_dict[username][matchmaking_type.perf_type]

        data.multiplier = 1 if success else data.multiplier * 2
        timeout = (game_duration + self.delay) * matchmaking_type.multiplier * data.multiplier

        if data.release_time > datetime.now():
            data.release_time += timeout
        else:
            data.release_time = datetime.now() + timeout

        release_str = data.release_time.isoformat(sep=' ', timespec='seconds')
        print(f'{username} will not be challenged to a new game pair before {release_str}.')

        if success and color == Challenge_Color.WHITE:
            data.color = Challenge_Color.BLACK
        else:
            data.color = Challenge_Color.WHITE

        self.busy_bots.clear()
        self._save(self.matchmaking_file)

    def reset_release_time(self, perf_type: Perf_Type) -> None:
        for perf_types in self.opponent_dict.values():
            perf_types[perf_type].release_time = datetime.now()

        self.busy_bots.clear()

    def _filter_bots(self, bots: list[Bot], matchmaking_type: Matchmaking_Type) -> list[Bot]:
        def bot_filter(bot: Bot) -> bool:
            if matchmaking_type.perf_type not in bot.rating_diffs:
                return False

            if matchmaking_type.max_rating_diff:
                if abs(bot.rating_diffs[matchmaking_type.perf_type]) > matchmaking_type.max_rating_diff:
                    return False

            if matchmaking_type.min_rating_diff:
                if abs(bot.rating_diffs[matchmaking_type.perf_type]) < matchmaking_type.min_rating_diff:
                    return False

            return True

        bots = sorted(filter(bot_filter, bots), key=lambda bot: abs(bot.rating_diffs[matchmaking_type.perf_type]))
        if not bots:
            raise NoOpponentException

        return bots

    def _load(self, matchmaking_file: str) -> defaultdict[str, defaultdict[Perf_Type, Matchmaking_Data]]:
        if not os.path.isfile(matchmaking_file):
            return defaultdict(lambda: defaultdict(Matchmaking_Data))

        with open(matchmaking_file, encoding='utf-8') as file:
            try:
                dict_ = json.load(file)
                if isinstance(dict_, list):
                    return self._update_format(dict_)

            except json.JSONDecodeError as e:
                print(f'Error while processing the file "{matchmaking_file}": {e}')
                return defaultdict(lambda: defaultdict(Matchmaking_Data))

            except PermissionError:
                print('Loading the matchmaking file failed due to missing read permissions.')
                return defaultdict(lambda: defaultdict(Matchmaking_Data))

            return defaultdict(lambda: defaultdict(Matchmaking_Data),
                               {username:
                                defaultdict(Matchmaking_Data,
                                            {Perf_Type(perf_type):
                                             Matchmaking_Data.from_dict(matchmaking_dict)
                                             for perf_type,
                                             matchmaking_dict in perf_types.items()})
                                for username,
                                perf_types in dict_.items()})

    def _min_opponent_dict(self) -> dict[str, dict[Perf_Type, dict[str, Any]]]:
        return {username: user_dict
                for username, perf_types
                in self.opponent_dict.items()
                if (user_dict := {perf_type: matchmaking_dict
                                  for perf_type, matchmaking_data
                                  in perf_types.items()
                                  if (matchmaking_dict := matchmaking_data.to_dict())})}

    def _save(self, matchmaking_file: str) -> None:
        min_opponent_dict = self._min_opponent_dict()
        if not min_opponent_dict:
            return

        try:
            with open(matchmaking_file, 'w', encoding='utf-8') as json_output:
                json.dump(min_opponent_dict, json_output)
        except PermissionError:
            print('Saving the matchmaking file failed due to missing write permissions.')

    def _update_format(self,
                       list_format: list[dict[str, Any]]
                       ) -> defaultdict[str, defaultdict[Perf_Type, Matchmaking_Data]]:
        dict_format: defaultdict[str,
                                 defaultdict[Perf_Type,
                                             Matchmaking_Data]] = defaultdict(lambda: defaultdict(Matchmaking_Data))
        for old_dict in list_format:
            username = old_dict.pop('username')

            perf_types: defaultdict[Perf_Type, Matchmaking_Data] = defaultdict(Matchmaking_Data)
            for perf_type, value in old_dict.items():
                release_time = (datetime.fromisoformat(value['release_time'])
                                if 'release_time' in value
                                else datetime.now())
                multiplier = value.get('multiplier', 1)
                color = Challenge_Color(value['color']) if 'color' in value else Challenge_Color.WHITE

                perf_types[Perf_Type(perf_type)] = Matchmaking_Data(release_time, multiplier, color)

            dict_format[username] = perf_types

        return dict_format
