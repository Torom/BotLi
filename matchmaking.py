from datetime import datetime, timedelta

from api import API
from botli_dataclasses import Bot, Challenge_Request, Challenge_Response
from challenger import Challenger
from enums import Perf_Type, Variant
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
        matchmaking_delay = config['matchmaking'].get('delay', 10)
        matchmaking_multiplier = max(config['matchmaking'].get('multiplier', 15), 1)
        self.opponents = Opponents(self.perf_types, self.estimated_game_duration,
                                   matchmaking_delay, matchmaking_multiplier, self.api.username)
        self.challenger = Challenger(config, self.api)
        self.blacklist: list[str] = config.get('blacklist', [])

        self.game_start_time: datetime = datetime.now()
        self.online_bots: dict[Perf_Type, list[Bot]] = {}

    def create_challenge(self, pending_challenge: Pending_Challenge) -> None:
        self._call_update()

        opponent, perf_type, color = self.opponents.get_next_opponent(self.online_bots)

        while self._is_bot_busy(opponent):
            print(f'Skipping {opponent.username} ({opponent.rating_diff:+}) as {color.value} because it is playing a game ...')
            self.opponents.skip_bot()
            opponent, perf_type, color = self.opponents.get_next_opponent(self.online_bots)

        print(f'Challenging {opponent.username} ({opponent.rating_diff:+}) as {color.value} to {perf_type.value} ...')
        challenge_request = Challenge_Request(opponent.username, self.initial_time, self.increment,
                                              self.is_rated, color, self._perf_type_to_variant(perf_type), self.timeout)

        last_response: Challenge_Response | None = None
        for response in self.challenger.create(challenge_request):
            last_response = response
            if response.challenge_id:
                pending_challenge.set_challenge_id(response.challenge_id)

        assert last_response
        if not last_response.success and not (last_response.has_reached_rate_limit or last_response.is_misconfigured):
            self.opponents.add_timeout(False, self.estimated_game_duration)

        pending_challenge.set_final_state(last_response)

    def on_game_started(self) -> None:
        self.game_start_time = datetime.now()

    def on_game_finished(self, game: Game) -> None:
        game_duration = datetime.now() - self.game_start_time
        was_aborted = game.lichess_game.is_abortable if game.lichess_game else True

        if was_aborted:
            game_duration += self.estimated_game_duration

        self.opponents.add_timeout(not was_aborted, game_duration)

    def _call_update(self) -> None:
        if self.next_update <= datetime.now():
            print('Updating online bots and rankings ...')
            self.online_bots = self._get_online_bots()

    def _get_online_bots(self) -> dict[Perf_Type, list[Bot]]:
        user_ratings = self._get_user_ratings()

        online_bots: dict[Perf_Type, list[Bot]] = {perf_type: [] for perf_type in self.perf_types}
        for bot in self.api.get_online_bots_stream():
            is_ourselves = bot['username'] == self.api.username
            is_blacklisted = bot['id'] in self.blacklist
            is_disabled = 'disabled' in bot
            has_tosViolation = self.is_rated and 'tosViolation' in bot

            if is_ourselves or is_blacklisted or is_disabled or has_tosViolation:
                continue

            for perf_type in self.perf_types:
                bot_rating = bot['perfs'][perf_type.value]['rating'] if perf_type.value in bot['perfs'] else 1500
                rating_diff = bot_rating - user_ratings[perf_type]
                if abs(rating_diff) >= self.min_rating_diff and abs(rating_diff) <= self.max_rating_diff:
                    online_bots[perf_type].append(Bot(bot['username'], rating_diff))

        for perf_type, bots in online_bots.items():
            if not bots:
                raise RuntimeError(f'No bots for {perf_type} in configured rating range online!')

        self.next_update = datetime.now() + timedelta(minutes=30)
        return online_bots

    def _get_user_ratings(self) -> dict[Perf_Type, int]:
        user = self.api.get_account()

        performances: dict[Perf_Type, int] = {}
        for perf_type in self.perf_types:
            performances[perf_type] = user['perfs'][perf_type.value]['rating'] if perf_type.value in user['perfs'] else 2500

        return performances

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

    def _is_bot_busy(self, bot: Bot) -> bool:
        bot_status = self.api.get_user_status(bot.username)
        return 'online' not in bot_status or 'playing' in bot_status
