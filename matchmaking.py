import json
import os
from datetime import datetime, timedelta
from threading import Thread

from api import API
from enums import Challenge_Color, Variant
from game_api import Game_api
from opponent import Opponent


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

        self.tc = self._get_tc()
        self.opponents = self._load()
        self.player = self.api.get_account()
        self.bots = self._get_bots()

    def start(self):
        Thread.start(self)

    def stop(self):
        self.is_running = False

    def run(self) -> None:
        while self.is_running:
            self._call_update()
            opponent = self._next_opponent()

            challenge_id = self._challenge_opponent(opponent, Challenge_Color.WHITE)

            if challenge_id is not None:
                start_time = datetime.now()
                game = Game_api(self.config, self.api, self.player['username'], challenge_id)
                game.run_game()
                game_duration = datetime.now() - start_time
            else:
                self._set_timeout(opponent, False, self.estimated_game_duration * 2)
                continue

            if not self.is_running:
                self._set_timeout(opponent, True, game_duration)
                break

            challenge_id = self._challenge_opponent(opponent, Challenge_Color.BLACK)

            if challenge_id is not None:
                start_time = datetime.now()
                game = Game_api(self.config, self.api, self.player['username'], challenge_id)
                game.run_game()
                game_duration += datetime.now() - start_time
            else:
                game_duration += self.estimated_game_duration

            self._set_timeout(opponent, challenge_id is not None, game_duration)

    @classmethod
    def reset_matchmaking(cls) -> None:
        if not os.path.isfile('matchmaking.json'):
            return

        with open('matchmaking.json', 'r') as input:
            opponents = [Opponent.from_dict(opponent) for opponent in json.load(input)]

        for opponent in opponents:
            opponent.release_time = datetime.now()

        with open('matchmaking.json', 'w') as output:
            json.dump([opponent.__dict__() for opponent in opponents], output, indent=4)

    def _challenge_opponent(self, opponent: dict, color: Challenge_Color) -> None | str:
        rated = self.config['matchmaking']['rated']
        initial_time = self.config['matchmaking']['initial_time']
        increment = self.config['matchmaking']['increment']
        timeout = self.config['matchmaking']['timeout']

        print(f'challenging {opponent["username"]} ({opponent["rating_diff"]}) as {color.value}')

        return self.api.create_challenge(
            opponent['username'],
            initial_time, increment, rated, color, Variant.STANDARD, timeout)

    def _load(self) -> list[Opponent]:
        if os.path.isfile('matchmaking.json'):
            with open('matchmaking.json', 'r') as input:
                return [Opponent.from_dict(opponent) for opponent in json.load(input)]
        else:
            return []

    def _save(self) -> None:
        with open('matchmaking.json', 'w') as output:
            json.dump([opponent.__dict__() for opponent in self.opponents], output, indent=4)

    def _call_update(self) -> None:
        if self.next_update <= datetime.now():
            self.player = self.api.get_account()
            self.bots = self._get_bots()
            print('updated online bots and rankings')

    def _get_bots(self) -> list[dict]:
        online_bots_stream = self.api.get_online_bots_stream()
        min_rating_diff = self.config['matchmaking'].get('min_rating_diff', 0)
        max_rating_diff = self.config['matchmaking'].get('max_rating_diff', float('inf'))

        if self.tc in self.player['perfs']:
            player_rating = self.player['perfs'][self.tc]['rating']
        else:
            player_rating = 1500

        bots: list[dict] = []
        for line in online_bots_stream:
            if line:
                bot = json.loads(line)
                if bot['username'] == self.player['username'] or 'disabled' in bot:
                    continue

                if self.tc in bot['perfs']:
                    bot_rating = bot['perfs'][self.tc]['rating']
                else:
                    bot_rating = 1500

                bot['rating_diff'] = bot_rating - player_rating
                if abs(bot['rating_diff']) >= min_rating_diff and abs(bot['rating_diff']) <= max_rating_diff:
                    bots.append(bot)

        if len(bots) == 0:
            raise RuntimeError('No online bots in rating range, check config!')

        bots.sort(key=lambda bot: abs(bot['rating_diff']))

        self.next_update = datetime.now() + timedelta(minutes=30)
        return bots

    def _get_tc(self) -> str:
        if self.variant != Variant.STANDARD and self.variant != Variant.FROM_POSITION:
            return self.variant.value

        estimated_game_duration = self.config['matchmaking']['initial_time'] + \
            self.config['matchmaking']['increment'] * 40

        if estimated_game_duration < 179:
            return 'bullet'
        elif estimated_game_duration < 479:
            return 'blitz'
        elif estimated_game_duration < 1499:
            return 'rapid'
        else:
            return 'classical'

    def _find(self, username: str) -> Opponent:
        try:
            return self.opponents[self.opponents.index(Opponent(username))]
        except ValueError:
            return Opponent(username)

    def _next_opponent(self) -> dict:
        for bot in self.bots:
            opponent = self._find(bot['username'])
            if opponent.release_time <= datetime.now():
                return bot

        for opponent in self.opponents:
            if opponent.multiplier == 1:
                opponent.release_time = datetime.now()

        print('matchmaking reseted')
        return self._next_opponent()

    def _set_timeout(self, bot: dict, success: bool, game_duration: timedelta) -> None:
        opponent = self._find(bot['username'])
        if success and opponent.multiplier > 1:
            opponent.multiplier //= 2
        elif not success:
            opponent.multiplier += 1
        timeout = game_duration * 25 * opponent.multiplier
        opponent.release_time = datetime.now() + timeout
        if not opponent in self.opponents:
            self.opponents.append(opponent)
        self._save()
