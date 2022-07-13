import json
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
        self.config = config
        self.api = api
        self.next_update = datetime.now()
        self.variant = Variant(self.config['matchmaking']['variant'])
        initial_time: int = self.config['matchmaking']['initial_time']
        increment: int = self.config['matchmaking']['increment']
        self.estimated_game_duration = timedelta(seconds=(initial_time + increment * 80) * 2)

        self.perf_type = self._get_perf_type()
        self.opponents = Opponents(self.perf_type, self.estimated_game_duration)
        self.opponent: dict | None = None
        self.game_start_time: datetime | None = None
        self.need_next_opponent = True
        self.challenger = Challenger(self.config, self.api)

    def create_challenge(self, pending_challenge: Pending_Challenge) -> None:
        if self.need_next_opponent:
            self._call_update()
            self.opponent = self.opponents.next_opponent(self.online_bots)

            color = Challenge_Color.WHITE
            self.need_next_opponent = False
        else:
            assert self.opponent
            color = Challenge_Color.BLACK
            self.need_next_opponent = True

        opponent_username = self.opponent['username']

        print(f'challenging {opponent_username} ({self.opponent["rating_diff"]:+.1f}) as {color.value}')

        rated = self.config['matchmaking']['rated']
        initial_time = self.config['matchmaking']['initial_time']
        increment = self.config['matchmaking']['increment']
        timeout = max(self.config['matchmaking']['timeout'], 1)
        challenge_request = Challenge_Request(opponent_username, initial_time,
                                              increment, rated, color, self.variant, timeout)

        last_reponse: Challenge_Response | None = None
        for response in self.challenger.create(challenge_request):
            last_reponse = response
            if response.challenge_id:
                pending_challenge.set_challenge_id(response.challenge_id)

        assert last_reponse
        if not last_reponse.success and not last_reponse.has_reached_rate_limit:
            self.need_next_opponent = True
            self.opponents.add_timeout(opponent_username, False, self.estimated_game_duration)

        pending_challenge.set_final_state(last_reponse.success, last_reponse.has_reached_rate_limit)

    def on_game_started(self) -> None:
        self.game_start_time = datetime.now()

    def on_game_finished(self, game: Game) -> None:
        assert self.opponent
        assert self.game_start_time

        game_duration = datetime.now() - self.game_start_time

        if game.was_aborted:
            self.need_next_opponent = True
            game_duration += self.estimated_game_duration

        self.opponents.add_timeout(self.opponent['username'], not game.was_aborted, game_duration)

    def _call_update(self) -> None:
        if self.next_update <= datetime.now():
            print('updating online bots and rankings ...')
            self.player_rating = self._get_rating()
            self.online_bots = self._get_online_bots()

    def _get_online_bots(self) -> list[dict]:
        online_bots_stream = self.api.get_online_bots_stream()
        min_rating_diff = self.config['matchmaking'].get('min_rating_diff', 0)
        max_rating_diff = self.config['matchmaking'].get('max_rating_diff', float('inf'))

        online_bots: list[dict] = []
        for line in online_bots_stream:
            if line:
                bot = json.loads(line)
                if bot['username'] == self.api.user['username'] or 'disabled' in bot:
                    continue

                if self.perf_type.value in bot['perfs']:
                    bot_rating = bot['perfs'][self.perf_type.value]['rating']
                else:
                    bot_rating = 1500

                bot['rating_diff'] = bot_rating - self.player_rating
                if abs(bot['rating_diff']) >= min_rating_diff and abs(bot['rating_diff']) <= max_rating_diff:
                    online_bots.append(bot)

        if len(online_bots) == 0:
            raise RuntimeError('No online bots in rating range, check config!')

        online_bots.sort(key=lambda bot: abs(bot['rating_diff']))

        self.next_update = datetime.now() + timedelta(minutes=30)
        return online_bots

    def _get_rating(self) -> float:
        perfomance = self.api.get_perfomance(self.api.user['username'], self.perf_type)
        provisional: bool = perfomance['perf']['glicko']['provisional']
        rating: float = perfomance['perf']['glicko']['rating']
        deviation: float = perfomance['perf']['glicko']['deviation']

        return rating + deviation if provisional else rating

    def _get_perf_type(self) -> Perf_Type:
        if self.variant not in [Variant.STANDARD, Variant.FROM_POSITION]:
            return Perf_Type(self.variant.value)

        initial_time: int = self.config['matchmaking']['initial_time']
        increment: int = self.config['matchmaking']['increment']
        estimated_game_duration = initial_time + increment * 40

        if estimated_game_duration < 179:
            return Perf_Type.BULLET
        elif estimated_game_duration < 479:
            return Perf_Type.BLITZ
        elif estimated_game_duration < 1499:
            return Perf_Type.RAPID
        else:
            return Perf_Type.CLASSICAL
