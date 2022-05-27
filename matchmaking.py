import json
from datetime import datetime, timedelta
from typing import Iterable

from api import API
from enums import Challenge_Color, Perf_Type, Variant
from game import Game
from matchmaking_response import Matchmaking_Response
from opponents import Opponents
from pending_challenge import Pending_Challenge


class Matchmaking:
    def __init__(self, config: dict, api: API) -> None:
        self.config = config
        self.api = api
        self.is_running = True
        self.next_update = datetime.now()
        self.variant = Variant(self.config['matchmaking']['variant'])
        initial_time: int = self.config['matchmaking']['initial_time']
        increment: int = self.config['matchmaking']['increment']
        self.estimated_game_duration = timedelta(seconds=(initial_time + increment * 80) * 2)
        self.estimated_game_pair_duration = self.estimated_game_duration * 2

        self.perf_type = self._get_perf_type()
        self.opponents = Opponents(self.perf_type, self.estimated_game_pair_duration)
        self.opponent: dict | None = None
        self.previous_opponent: dict | None = None
        self.game_start_time: datetime | None = None
        self.white_game_duration: timedelta | None = None
        self.need_next_opponent = True

    def create_challenge(self, pending_challenge: Pending_Challenge) -> None:
        if self.need_next_opponent:
            self._call_update()
            self.opponent = self.opponents.next_opponent(self.online_bots)

            color = Challenge_Color.WHITE
        else:
            assert self.previous_opponent

            self.opponent = self.previous_opponent
            color = Challenge_Color.BLACK
            self.need_next_opponent = True

        opponent_username = self.opponent['username']

        print(f'challenging {opponent_username} ({self.opponent["rating_diff"]:+.1f}) as {color.value}')

        last_reponse: Matchmaking_Response | None = None
        for response in self._challenge_bot(opponent_username, color):
            last_reponse = response
            if response.challenge_id:
                pending_challenge.set_challenge_id(response.challenge_id)

        if last_reponse is None:
            raise Exception('"last_response" should not be None!')

        success = last_reponse.success

        if not success:
            self.need_next_opponent = True
            if color == Challenge_Color.WHITE:
                self.opponents.set_timeout(
                    opponent_username,
                    False,
                    self.estimated_game_pair_duration
                )
            else:
                assert self.white_game_duration
                self.opponents.set_timeout(
                    opponent_username,
                    True,
                    self.white_game_duration + self.estimated_game_duration
                )

        self.previous_opponent = self.opponent
        pending_challenge.set_final_state(success, last_reponse.has_reached_rate_limit)

    def on_game_started(self) -> None:
        self.game_start_time = datetime.now()

    def on_game_finished(self, game: Game, is_running: bool) -> None:
        assert self.previous_opponent
        assert self.game_start_time

        opponent_username = self.previous_opponent['username']

        if game.lichess_game.is_white:
            if game.was_aborted:
                self.need_next_opponent = True
                self.opponents.set_timeout(opponent_username, False, self.estimated_game_pair_duration)
                return
            else:
                self.need_next_opponent = False

            self.white_game_duration = datetime.now() - self.game_start_time
            if not is_running:
                # This is probably the last event this class will ever receive
                # because the program is shutting down.
                self.opponents.set_timeout(
                    opponent_username,
                    True,
                    self.white_game_duration
                )
            return

        assert self.white_game_duration
        black_game_duration = datetime.now() - self.game_start_time
        total_game_duration = self.white_game_duration + black_game_duration

        if game.was_aborted:
            total_game_duration += self.estimated_game_duration

        self.opponents.set_timeout(opponent_username, True, total_game_duration)

    def _challenge_bot(self, username: str, color: Challenge_Color) -> Iterable[Matchmaking_Response]:
        rated = self.config['matchmaking']['rated']
        initial_time = self.config['matchmaking']['initial_time']
        increment = self.config['matchmaking']['increment']
        timeout = self.config['matchmaking']['timeout']

        challenge_response = self.api.create_challenge(
            username, initial_time, increment, rated, color, self.variant, timeout)

        challenge_id = None

        for response in challenge_response:
            if response.challenge_id:
                challenge_id = response.challenge_id
                yield Matchmaking_Response(challenge_id=challenge_id)
            elif response.was_accepted:
                yield Matchmaking_Response(success=True)
            elif response.error:
                print(response.error)
                yield Matchmaking_Response(success=False)
            elif response.was_declined:
                print('challenge was declined.')
                yield Matchmaking_Response(success=False)
            elif response.has_timed_out:
                print('challenge timed out.')
                if challenge_id is None:
                    print('Could not cancel challenge because the challenge_id was not set in "_challenge_bot"!')
                    continue
                self.api.cancel_challenge(challenge_id)
                yield Matchmaking_Response(success=False)
            elif response.has_reached_rate_limit:
                yield Matchmaking_Response(success=False, has_reached_rate_limit=True)

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
