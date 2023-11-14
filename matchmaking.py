import random
from collections import defaultdict
from datetime import datetime, timedelta

from api import API
from botli_dataclasses import Bot, Challenge_Request, Challenge_Response, Matchmaking_Type
from challenger import Challenger
from enums import Busy_Reason, Perf_Type, Variant
from game import Game
from opponents import NoOpponentException, Opponents
from pending_challenge import Pending_Challenge


class Matchmaking:
    def __init__(self, config: dict, api: API) -> None:
        self.api = api
        self.username: str = config['username']
        self.next_update = datetime.now()
        self.timeout = max(config['matchmaking']['timeout'], 1)
        self.types = self._get_types(config)
        self.opponents = Opponents(config['matchmaking'].get('delay', 10), self.username)
        self.challenger = Challenger(config, self.api)
        self.blacklist: list[str] = config.get('blacklist', [])

        self.game_start_time: datetime = datetime.now()
        self.online_bots: list[Bot] = []
        self.current_type: Matchmaking_Type | None = None

    def create_challenge(self, pending_challenge: Pending_Challenge) -> None:
        if self._call_update():
            pending_challenge.return_early()
            return

        if not self.current_type:
            self.current_type, = random.choices(self.types, [type.weight for type in self.types])
            print(f'Matchmaking type: {self.current_type.to_str}')

        try:
            next_opponent = self.opponents.get_opponent(self.online_bots, self.current_type)
        except NoOpponentException:
            print(f'Removing matchmaking type {self.current_type.name} because '
                  'no opponent is online in the configured rating range.')
            self.types.remove(self.current_type)
            if not self.types:
                print('No usable matchmaking type configured.')
                pending_challenge.set_final_state(Challenge_Response(is_misconfigured=True))
                return

            pending_challenge.set_final_state(Challenge_Response(no_opponent=True))
            return

        if next_opponent:
            opponent, color = next_opponent
        else:
            print(f'No opponent available for matchmaking type {self.current_type.name}.')
            self.current_type = None
            pending_challenge.set_final_state(Challenge_Response(no_opponent=True))
            return

        if busy_reason := self._get_busy_reason(opponent):
            if busy_reason == Busy_Reason.PLAYING:
                rating_diff = opponent.rating_diffs[self.current_type.perf_type]
                print(f'Skipping {opponent.username} ({rating_diff:+}) as {color.value} ...')
                self.opponents.skip_bot()
            elif busy_reason == Busy_Reason.OFFLINE:
                print(f'Removing {opponent.username} from online bots because it is offline ...')
                self.online_bots.remove(opponent)

            pending_challenge.return_early()
            return

        rating_diff = opponent.rating_diffs[self.current_type.perf_type]
        print(f'Challenging {opponent.username} ({rating_diff:+}) as {color.value} to {self.current_type.name} ...')
        challenge_request = Challenge_Request(opponent.username, self.current_type.initial_time,
                                              self.current_type.increment, self.current_type.rated, color,
                                              self.current_type.variant, self.timeout)

        last_response: Challenge_Response | None = None
        for response in self.challenger.create(challenge_request):
            last_response = response
            if response.challenge_id:
                pending_challenge.set_challenge_id(response.challenge_id)

        assert last_response
        if not last_response.success and not (last_response.has_reached_rate_limit or last_response.is_misconfigured):
            self.opponents.add_timeout(False, self.current_type.estimated_game_duration, self.current_type)

        pending_challenge.set_final_state(last_response)

    def on_game_started(self) -> None:
        self.game_start_time = datetime.now()

    def on_game_finished(self, game: Game) -> None:
        assert self.current_type

        game_duration = datetime.now() - self.game_start_time
        was_aborted = game.lichess_game.is_abortable if game.lichess_game else True

        if was_aborted:
            game_duration += self.current_type.estimated_game_duration

        self.opponents.add_timeout(not was_aborted, game_duration, self.current_type)
        self.current_type = None

    def _get_types(self, config: dict) -> list[Matchmaking_Type]:
        types: list[Matchmaking_Type] = []
        for name, options in config['matchmaking']['types'].items():
            initial_time, increment = options['tc'].split('+')
            initial_time = int(float(initial_time) * 60) if initial_time else 0
            increment = int(increment) if increment else 0
            rated = options.get('rated', True)
            variant = Variant(options.get('variant', 'standard'))
            perf_type = self._variant_to_perf_type(variant, initial_time, increment)
            multiplier = options.get('multiplier', 15)
            weight = options.get('weight', 100)
            min_rating_diff = options.get('min_rating_diff', 0)
            max_rating_diff = options.get('max_rating_diff', 10_000)

            types.append(Matchmaking_Type(name, initial_time, increment, rated, variant,
                         perf_type, multiplier, weight, min_rating_diff, max_rating_diff))

        return types

    def _call_update(self) -> bool:
        if self.next_update <= datetime.now():
            print('Updating online bots and rankings ...')
            self.online_bots = self._get_online_bots()
            return True

        return False

    def _get_online_bots(self) -> list[Bot]:
        user_ratings = self._get_user_ratings()

        online_bots: list[Bot] = []
        bot_counts: defaultdict[str, int] = defaultdict(int)
        for bot in self.api.get_online_bots_stream():
            bot_counts['online'] += 1

            tos_violation = False
            if 'tosViolation' in bot:
                tos_violation = True
                bot_counts['with tosViolation'] += 1

            if bot['username'] == self.username:
                continue

            if 'disabled' in bot:
                bot_counts['disabled'] += 1
                continue

            if bot['id'] in self.blacklist:
                bot_counts['blacklisted'] += 1
                continue

            rating_diffs: dict[Perf_Type, int] = {}
            for perf_type in Perf_Type:
                bot_rating = bot['perfs'][perf_type.value]['rating'] if perf_type.value in bot['perfs'] else 1500
                rating_diffs[perf_type] = bot_rating - user_ratings[perf_type]

            online_bots.append(Bot(bot['username'], tos_violation, rating_diffs))

        for category, count in bot_counts.items():
            if count:
                print(f'{count:3} bots {category}')

        self.next_update = datetime.now() + timedelta(minutes=30.0)
        return online_bots

    def _get_user_ratings(self) -> dict[Perf_Type, int]:
        user = self.api.get_account()

        performances: dict[Perf_Type, int] = {}
        for perf_type in Perf_Type:
            if perf_type.value in user['perfs']:
                performances[perf_type] = user['perfs'][perf_type.value]['rating']
            else:
                performances[perf_type] = 2500

        return performances

    def _variant_to_perf_type(self, variant: Variant, initial_time: int, increment: int) -> Perf_Type:
        if variant != Variant.STANDARD:
            return Perf_Type(variant.value)

        estimated_game_duration = initial_time + increment * 40
        if estimated_game_duration < 179:
            return Perf_Type.BULLET

        if estimated_game_duration < 479:
            return Perf_Type.BLITZ

        if estimated_game_duration < 1499:
            return Perf_Type.RAPID

        return Perf_Type.CLASSICAL

    def _perf_type_to_variant(self, perf_type: Perf_Type) -> Variant:
        if perf_type in [Perf_Type.BULLET, Perf_Type.BLITZ, Perf_Type.RAPID, Perf_Type.CLASSICAL]:
            return Variant.STANDARD

        return Variant(perf_type.value)

    def _get_busy_reason(self, bot: Bot) -> Busy_Reason | None:
        bot_status = self.api.get_user_status(bot.username)
        if 'online' not in bot_status:
            return Busy_Reason.OFFLINE

        if 'playing' in bot_status:
            return Busy_Reason.PLAYING
