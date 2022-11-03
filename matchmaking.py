import json
import random
from datetime import datetime, timedelta

from api import API
from challenge_request import Challenge_Request
from challenge_response import Challenge_Response
from challenger import Challenger
from enums import Challenge_Color, Perf_Type, Variant
from game import Game
from opponents import Opponents
from pending_challenge import Pending_Challenge


class Matchmaking:
    def __init__(self, config: dict, api: API) -> None:
        self.api = api
        self.next_update = datetime.now()
        self.initial_time: int = config['matchmaking']['initial_time']
        self.increment: int = config['matchmaking']['increment']
        self.is_rated: bool = config['matchmaking']['rated']
        self.timeout = max(config['matchmaking']['timeout'], 1)
        self.min_rating_diff: int = config['matchmaking'].get('min_rating_diff', 0)
        self.max_rating_diff: int = config['matchmaking'].get('max_rating_diff', float('inf'))
        self.estimated_game_duration = timedelta(seconds=(self.initial_time + self.increment * 80) * 2)
        self.perf_types = [self._variant_to_perf_type(variant) for variant in config['matchmaking']['variants']]
        self.opponents = Opponents(self.estimated_game_duration, config['matchmaking']['delay'])
        self.need_next_opponent = True

        self.perf_type: Perf_Type | None = None
        self.opponent: dict | None = None
        self.game_start_time: datetime | None = None
        self.challenge_duration: timedelta | None = None
        self.online_bots: list[dict] | None = None

        self.challenger = Challenger(config, self.api)

    def create_challenge(self, pending_challenge: Pending_Challenge) -> None:
        if self.need_next_opponent:
            self._call_update()
            assert self.online_bots

            self.perf_type = random.choice(self.perf_types)
            self.opponent = self.opponents.next_opponent(self.perf_type, self._filter_bot_list(
                self.perf_type, self.online_bots))

            color = Challenge_Color.WHITE
            self.need_next_opponent = False
        else:
            assert self.perf_type
            assert self.opponent

            color = Challenge_Color.BLACK
            self.need_next_opponent = True

        opponent_username = self.opponent['username']

        print(
            f'Challenging {opponent_username} ({self.opponent[self.perf_type]:+.1f}) as {color.value} to {self.perf_type.value} ...')

        challenge_request = Challenge_Request(
            opponent_username, self.initial_time, self.increment, self.is_rated, color, self._perf_type_to_variant(
                self.perf_type),
            self.timeout)

        last_reponse: Challenge_Response | None = None
        challenge_start_time = datetime.now()
        for response in self.challenger.create(challenge_request):
            last_reponse = response
            if response.challenge_id:
                pending_challenge.set_challenge_id(response.challenge_id)
        self.challenge_duration = datetime.now() - challenge_start_time

        assert last_reponse
        if not last_reponse.success and not last_reponse.has_reached_rate_limit:
            self.need_next_opponent = True
            self.opponents.add_timeout(self.perf_type, opponent_username, False,
                                       self.estimated_game_duration, self.challenge_duration)

        pending_challenge.set_final_state(last_reponse.success, last_reponse.has_reached_rate_limit)

    def on_game_started(self) -> None:
        self.game_start_time = datetime.now()

    def on_game_finished(self, game: Game) -> None:
        assert self.perf_type
        assert self.opponent
        assert self.game_start_time
        assert self.challenge_duration

        game_duration = datetime.now() - self.game_start_time
        was_aborted = game.lichess_game.is_abortable()

        if was_aborted:
            self.need_next_opponent = True
            game_duration += self.estimated_game_duration

        self.opponents.add_timeout(
            self.perf_type, self.opponent['username'],
            not was_aborted, game_duration, self.challenge_duration)

    def _call_update(self) -> None:
        if self.next_update <= datetime.now():
            print('Updating online bots and rankings ...')
            self.online_bots = self._get_online_bots()

    def _get_online_bots(self) -> list[dict]:
        user_ratings = {perf_type: self._get_rating(perf_type) for perf_type in self.perf_types}

        online_bots: list[dict] = []
        online_bots_stream = self.api.get_online_bots_stream()
        for line in online_bots_stream:
            if line:
                bot = json.loads(line)

                is_ourselves = bot['username'] == self.api.user['username']
                is_disabled = 'disabled' in bot
                has_tosViolation = 'tosViolation' in bot if self.is_rated else False

                if is_ourselves or is_disabled or has_tosViolation:
                    continue

                for perf_type in self.perf_types:
                    if perf_type.value in bot['perfs']:
                        bot_rating = bot['perfs'][perf_type.value]['rating']
                    else:
                        bot_rating = 1500

                    bot[perf_type] = bot_rating - user_ratings[perf_type]

                online_bots.append(bot)

        self.next_update = datetime.now() + timedelta(minutes=30)
        return online_bots

    def _get_rating(self, perf_type: Perf_Type) -> float:
        perfomance = self.api.get_perfomance(self.api.user['username'], perf_type)
        provisional: bool = perfomance['perf']['glicko']['provisional']
        rating: float = perfomance['perf']['glicko']['rating']
        deviation: float = perfomance['perf']['glicko']['deviation']

        return rating + deviation if provisional else rating

    def _variant_to_perf_type(self, matchmaking_variant: str) -> Perf_Type:
        variant = Variant(matchmaking_variant)

        if variant != Variant.STANDARD:
            return Perf_Type(variant.value)

        estimated_game_duration = self.initial_time + self.increment * 40
        if estimated_game_duration < 179:
            return Perf_Type.BULLET
        elif estimated_game_duration < 479:
            return Perf_Type.BLITZ
        elif estimated_game_duration < 1499:
            return Perf_Type.RAPID
        else:
            return Perf_Type.CLASSICAL

    def _perf_type_to_variant(self, perf_type: Perf_Type) -> Variant:
        if perf_type in [Perf_Type.BULLET, Perf_Type.BLITZ, Perf_Type.RAPID, Perf_Type.CLASSICAL]:
            return Variant.STANDARD
        else:
            return Variant(perf_type.value)

    def _filter_bot_list(self, perf_type: Perf_Type, online_bots: list[dict]) -> list[dict]:
        bot_list = [bot for bot in online_bots if abs(
            bot[perf_type]) >= self.min_rating_diff and abs(bot[perf_type]) <= self.max_rating_diff]
        return sorted(bot_list, key=lambda bot: abs(bot[perf_type]))
