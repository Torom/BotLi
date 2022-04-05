import json
from datetime import datetime, timedelta
from threading import Thread

from api import API
from enums import Challenge_Color, Perf_Type, Variant
from game_api import Game_api
from opponents import Opponents


class Matchmaking(Thread):
    def __init__(self, config: dict, api: API, variant: Variant) -> None:
        Thread.__init__(self)
        self.config = config
        self.api = api
        self.is_running = True
        self.next_update = datetime.now()
        self.variant = variant
        initial_time: int = self.config['matchmaking']['initial_time']
        increment: int = self.config['matchmaking']['increment']
        self.estimated_game_duration = timedelta(seconds=(initial_time + increment * 80) * 2)
        self.estimated_game_pair_duration = self.estimated_game_duration * 2

        self.perf_type = self._get_perf_type()
        self.opponents = Opponents(self.perf_type)
        self.player_rating = self._get_rating()
        self.online_bots = self._get_online_bots()

    def start(self):
        Thread.start(self)

    def stop(self):
        self.is_running = False

    def run(self) -> None:
        while self.is_running:
            self._call_update()
            bot = self.opponents.next_opponent(self.online_bots)

            challenge_id = self._challenge_bot(bot, Challenge_Color.WHITE)

            if challenge_id is not None:
                start_time = datetime.now()
                game = Game_api(self.config, self.api, challenge_id)
                game.run_game()
                game_duration = datetime.now() - start_time

                if game.was_aborted:
                    game_duration += self.estimated_game_duration
            else:
                self.opponents.set_timeout(
                    bot['username'],
                    False, self.estimated_game_pair_duration, self.estimated_game_pair_duration)
                continue

            if not self.is_running:
                self.opponents.set_timeout(bot['username'], True, game_duration, self.estimated_game_pair_duration)
                break

            challenge_id = self._challenge_bot(bot, Challenge_Color.BLACK)

            if challenge_id is not None:
                start_time = datetime.now()
                game = Game_api(self.config, self.api, challenge_id)
                game.run_game()
                game_duration += datetime.now() - start_time

                if game.was_aborted:
                    game_duration += self.estimated_game_duration
            else:
                game_duration += self.estimated_game_duration

            self.opponents.set_timeout(bot['username'], True, game_duration, self.estimated_game_pair_duration)

    def _challenge_bot(self, bot: dict, color: Challenge_Color) -> str | None:
        rated = self.config['matchmaking']['rated']
        initial_time = self.config['matchmaking']['initial_time']
        increment = self.config['matchmaking']['increment']
        timeout = self.config['matchmaking']['timeout']

        print(f'challenging {bot["username"]} ({bot["rating_diff"]:+.1f}) as {color.value}')

        challenge_lines = self.api.create_challenge(
            bot['username'],
            initial_time, increment, rated, color, self.variant, timeout)

        line = challenge_lines[0]
        if 'challenge' in line and 'id' in line['challenge']:
            challenge_id = line['challenge']['id']
        elif 'error' in line:
            print(line['error'])
            return
        else:
            print(line)
            return

        line = challenge_lines[1]
        if 'done' in line and line['done'] == 'accepted':
            return challenge_id
        elif 'done' in line and line['done'] == 'timeout':
            print('challenge timed out.')
            self.api.cancel_challenge(challenge_id)
        elif 'done' in line and line['done'] == 'declined':
            print('challenge was declined.')

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
