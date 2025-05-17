import random
from datetime import datetime, timedelta

from api import API
from botli_dataclasses import Bot, Challenge_Request, Challenge_Response, Matchmaking_Type
from challenger import Challenger
from config import Config
from enums import Busy_Reason, Perf_Type, Variant
from exceptions import NoOpponentException
from opponents import Opponents


class Matchmaking:
    def __init__(self, api: API, config: Config, username: str) -> None:
        self.api = api
        self.config = config
        self.username = username
        self.next_update = datetime.now()
        self.timeout = max(config.matchmaking.timeout, 1)
        self.types = self._get_matchmaking_types()
        self.suspended_types: list[Matchmaking_Type] = []
        self.opponents = Opponents(config.matchmaking.delay, username)
        self.challenger = Challenger(api)

        self.game_start_time: datetime = datetime.now()
        self.online_bots: list[Bot] = []
        self.current_type: Matchmaking_Type | None = None

    async def create_challenge(self) -> Challenge_Response | None:
        if await self._call_update():
            return

        if self.current_type is None:
            if self.config.matchmaking.selection == 'weighted_random':
                self.current_type, = random.choices(self.types, [type.weight for type in self.types])
            else:
                self.current_type = self.types[0]

            print(f'Matchmaking type: {self.current_type}')

        try:
            next_opponent = self.opponents.get_opponent(self.online_bots, self.current_type)
        except NoOpponentException:
            print(f'Suspending matchmaking type {self.current_type.name} because no suitable opponent is available.')
            self.suspended_types.append(self.current_type)
            self.types.remove(self.current_type)
            self.current_type = None
            if not self.types:
                print('No usable matchmaking type configured.')
                return Challenge_Response(is_misconfigured=True)

            return Challenge_Response(no_opponent=True)

        if next_opponent is None:
            print(f'No opponent available for matchmaking type {self.current_type.name}.')
            if self.config.matchmaking.selection == 'weighted_random':
                self.current_type = None
            else:
                self.current_type = self._get_next_type()

            if self.current_type is None:
                return Challenge_Response(no_opponent=True)

            return

        opponent, color = next_opponent

        match await self._get_busy_reason(opponent):
            case Busy_Reason.PLAYING:
                rating_diff = opponent.rating_diffs[self.current_type.perf_type]
                print(f'Skipping {opponent.username} ({rating_diff:+}) as {color} ...')
                self.opponents.busy_bots.append(opponent)
                return

            case Busy_Reason.OFFLINE:
                print(f'Removing {opponent.username} from online bots ...')
                self.online_bots.remove(opponent)
                return

        rating_diff = opponent.rating_diffs[self.current_type.perf_type]
        print(f'Challenging {opponent.username} ({rating_diff:+}) as {color} to {self.current_type.name} ...')
        challenge_request = Challenge_Request(opponent.username, self.current_type.initial_time,
                                              self.current_type.increment, self.current_type.rated, color,
                                              self.current_type.variant, self.timeout)

        response = await self.challenger.create(challenge_request)
        if response.success:
            self.game_start_time = datetime.now()
        elif not (response.has_reached_rate_limit or response.is_misconfigured):
            self.opponents.add_timeout(False, self.current_type.estimated_game_duration)
        else:
            self.current_type = None

        return response

    def on_game_finished(self, was_aborted: bool) -> None:
        assert self.current_type

        game_duration = datetime.now() - self.game_start_time
        if was_aborted:
            game_duration += self.current_type.estimated_game_duration

        self.opponents.add_timeout(not was_aborted, game_duration)

        if self.config.matchmaking.selection == 'cyclic':
            self.current_type = self._get_next_type()
        else:
            self.current_type = None

    def _get_next_type(self) -> Matchmaking_Type | None:
        last_type = self.types[-1]
        for i, matchmaking_type in enumerate(self.types):
            if matchmaking_type == last_type:
                return

            if matchmaking_type == self.current_type:
                print(f'Matchmaking type: {self.types[i + 1]}')
                return self.types[i + 1]

    def _get_matchmaking_types(self) -> list[Matchmaking_Type]:
        matchmaking_types: list[Matchmaking_Type] = []
        for name, type_config in self.config.matchmaking.types.items():
            initial_time, increment = type_config.tc.split('+')
            initial_time = int(float(initial_time) * 60) if initial_time else 0
            increment = int(increment) if increment else 0
            rated = True if type_config.rated is None else type_config.rated
            variant = Variant.STANDARD if type_config.variant is None else Variant(type_config.variant)
            perf_type = self._variant_to_perf_type(variant, initial_time, increment)
            weight = 1.0 if type_config.weight is None else type_config.weight

            matchmaking_types.append(Matchmaking_Type(name, initial_time, increment, rated, variant,
                                                      perf_type, type_config.multiplier, -1, weight,
                                                      type_config.min_rating_diff, type_config.max_rating_diff))

        for matchmaking_type, type_config in zip(matchmaking_types, self.config.matchmaking.types.values()):
            if type_config.weight is None:
                matchmaking_type.weight /= matchmaking_type.estimated_game_duration.total_seconds()

        matchmaking_types.sort(key=lambda matchmaking_type: matchmaking_type.weight, reverse=True)

        return matchmaking_types

    async def _call_update(self) -> bool:
        if self.next_update > datetime.now():
            return False

        print('Updating online bots and rankings ...')
        self.types.extend(self.suspended_types)
        self.suspended_types.clear()
        self.online_bots = await self._get_online_bots()
        self._set_multiplier()
        return True

    async def _get_online_bots(self) -> list[Bot]:
        user_ratings = await self._get_user_ratings()

        online_bots: list[Bot] = []
        blacklisted_bot_count = 0
        for bot in await self.api.get_online_bots():
            if bot['username'] == self.username:
                continue

            if bot['id'] in self.config.blacklist:
                blacklisted_bot_count += 1
                continue

            rating_diffs: dict[Perf_Type, int] = {}
            for perf_type in Perf_Type:
                if perf_type not in bot['perfs']:
                    continue

                rating_diffs[perf_type] = bot['perfs'][perf_type]['rating'] - user_ratings[perf_type]

            online_bots.append(Bot(bot['username'], rating_diffs))

        print(f'{len(online_bots) + blacklisted_bot_count + 1:3} bots online')
        print(f'{blacklisted_bot_count:3} bots blacklisted')

        self.next_update = datetime.now() + timedelta(minutes=30.0)
        return online_bots

    async def _get_user_ratings(self) -> dict[Perf_Type, int]:
        user = await self.api.get_account()

        performances: dict[Perf_Type, int] = {}
        for perf_type in Perf_Type:
            if perf_type in user['perfs']:
                performances[perf_type] = user['perfs'][perf_type]['rating']
            else:
                performances[perf_type] = 2500

        return performances

    def _set_multiplier(self) -> None:
        for matchmaking_type in self.types:
            if matchmaking_type.config_multiplier:
                matchmaking_type.multiplier = matchmaking_type.config_multiplier
            else:
                min_rating_diff = matchmaking_type.min_rating_diff if matchmaking_type.min_rating_diff else 0
                max_rating_diff = matchmaking_type.max_rating_diff if matchmaking_type.max_rating_diff else 600

                bot_count = self._get_bot_count(matchmaking_type.perf_type, min_rating_diff, max_rating_diff)
                perf_type_count = len({matchmaking_type.perf_type for matchmaking_type in self.types})
                matchmaking_type.multiplier = bot_count * perf_type_count

    def _get_bot_count(self, perf_type: Perf_Type, min_rating_diff: int, max_rating_diff: int) -> int:
        def bot_filter(bot: Bot) -> bool:
            if perf_type not in bot.rating_diffs:
                return False

            if abs(bot.rating_diffs[perf_type]) > max_rating_diff:
                return False

            if abs(bot.rating_diffs[perf_type]) < min_rating_diff:
                return False

            if self.opponents.opponent_dict[bot.username][perf_type].multiplier > 1:
                return False

            return True

        return sum(map(bot_filter, self.online_bots))

    def _variant_to_perf_type(self, variant: Variant, initial_time: int, increment: int) -> Perf_Type:
        if variant != Variant.STANDARD:
            return Perf_Type(variant)

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

        return Variant(perf_type)

    async def _get_busy_reason(self, bot: Bot) -> Busy_Reason | None:
        bot_status = await self.api.get_user_status(bot.username)
        if 'online' not in bot_status:
            return Busy_Reason.OFFLINE

        if 'playing' in bot_status:
            return Busy_Reason.PLAYING
