from asyncio import Event, Task, create_task, timeout
from collections import deque
from datetime import datetime, timedelta

from api import API
from botli_dataclasses import Challenge, Challenge_Request
from challenger import Challenger
from config import Config
from enums import Decline_Reason
from game import Game
from matchmaking import Matchmaking


class Game_Manager:
    def __init__(self, api: API, config: Config, username: str) -> None:
        self.config = config
        self.username = username
        self.api = api
        self.is_running = True
        self.games: dict[Game, Task[None]] = {}
        self.open_challenges: deque[Challenge] = deque()
        self.reserved_game_spots = 0
        self.started_game_ids: deque[str] = deque()
        self.challenge_requests: deque[Challenge_Request] = deque()
        self.changed_event = Event()
        self.matchmaking = Matchmaking(api, config, username)
        self.current_matchmaking_game_id: str | None = None
        self.challenger = Challenger(api)
        self.is_rate_limited = False
        self.next_matchmaking = datetime.max
        self.matchmaking_delay = timedelta(seconds=config.matchmaking.delay)

    def stop(self):
        self.is_running = False
        self.changed_event.set()

    async def run(self) -> None:
        while self.is_running:
            try:
                async with timeout(1.0):
                    await self.changed_event.wait()
            except TimeoutError:
                await self._check_matchmaking()
                continue

            self.changed_event.clear()

            await self._check_for_finished_games()

            while self.started_game_ids:
                await self._start_game(self.started_game_ids.popleft())

            while challenge_request := self._get_next_challenge_request():
                await self._create_challenge(challenge_request)

            while challenge := self._get_next_challenge():
                await self._accept_challenge(challenge)

        for game, task in self.games.items():
            await task

            if game.game_id == self.current_matchmaking_game_id:
                self.matchmaking.on_game_finished(game.lichess_game.is_abortable)

    def add_challenge(self, challenge: Challenge) -> None:
        if challenge not in self.open_challenges:
            self.open_challenges.append(challenge)
            self.changed_event.set()

    def request_challenge(self, *challenge_requests: Challenge_Request) -> None:
        self.challenge_requests.extend(challenge_requests)
        self.changed_event.set()

    def remove_challenge(self, challenge: Challenge) -> None:
        if challenge in self.open_challenges:
            self.open_challenges.remove(challenge)
            self.changed_event.set()

    def on_game_started(self, game_id: str) -> None:
        self.started_game_ids.append(game_id)
        self.changed_event.set()

    def start_matchmaking(self) -> None:
        self.next_matchmaking = datetime.now()

    def stop_matchmaking(self) -> bool:
        if self.next_matchmaking != datetime.max:
            self.next_matchmaking = datetime.max
            return True

        return False

    def _delay_matchmaking(self, delay: timedelta) -> None:
        if self.next_matchmaking == datetime.max:
            return

        if self.is_rate_limited:
            return

        self.next_matchmaking = datetime.now() + delay

    async def _check_for_finished_games(self) -> None:
        for game, task in list(self.games.items()):
            if not task.done():
                continue

            if game.game_id == self.current_matchmaking_game_id:
                self.matchmaking.on_game_finished(game.lichess_game.is_abortable)
                self.current_matchmaking_game_id = None

            if game.has_timed_out:
                await self._decline_challenges(game.info.black_name
                                               if game.lichess_game.is_white
                                               else game.info.white_name)

            self._delay_matchmaking(self.matchmaking_delay)

            del self.games[game]

    async def _start_game(self, game_id: str) -> None:
        if game_id in {game.game_id for game in self.games}:
            return

        if self.reserved_game_spots > 0:
            # Remove reserved spot, if it exists:
            self.reserved_game_spots -= 1

        if len(self.games) >= self.config.challenge.concurrency:
            print(f'Max number of concurrent games exceeded. Aborting already started game {game_id}.')
            await self.api.abort_game(game_id)
            return

        game = await Game.acreate(self.api, self.config, self.username, game_id, self.changed_event)
        self.games[game] = create_task(game.run())

    def _get_next_challenge(self) -> Challenge | None:
        if not self.open_challenges:
            return

        if len(self.games) + self.reserved_game_spots >= self.config.challenge.concurrency:
            return

        return self.open_challenges.popleft()

    async def _accept_challenge(self, challenge: Challenge) -> None:
        if await self.api.accept_challenge(challenge.challenge_id):
            # Reserve a spot for this game
            self.reserved_game_spots += 1
        else:
            print(f'Challenge "{challenge.challenge_id}" could not be accepted!')

    async def _check_matchmaking(self) -> None:
        if self.current_matchmaking_game_id:
            # There is already a matchmaking game running
            return

        if len(self.games) + self.reserved_game_spots >= self.config.challenge.concurrency:
            return

        if self.next_matchmaking > datetime.now():
            return

        challenge_response = await self.matchmaking.create_challenge()
        if challenge_response is None:
            return

        self.is_rate_limited = False
        if challenge_response.success:
            # Reserve a spot for this game
            self.reserved_game_spots += 1
            self.current_matchmaking_game_id = challenge_response.challenge_id
            return

        if challenge_response.no_opponent:
            self._delay_matchmaking(self.matchmaking_delay)

        if challenge_response.has_reached_rate_limit:
            self._delay_matchmaking(timedelta(hours=1.0))
            next_matchmaking_str = self.next_matchmaking.isoformat(sep=' ', timespec='seconds')
            print(f'Matchmaking has reached rate limit, next attempt at {next_matchmaking_str}.')
            self.is_rate_limited = True

        if challenge_response.is_misconfigured:
            print('Matchmaking stopped due to misconfiguration.')
            self.stop_matchmaking()

    def _get_next_challenge_request(self) -> Challenge_Request | None:
        if not self.challenge_requests:
            return

        if len(self.games) + self.reserved_game_spots >= self.config.challenge.concurrency:
            return

        return self.challenge_requests.popleft()

    async def _create_challenge(self, challenge_request: Challenge_Request) -> None:
        print(f'Challenging {challenge_request.opponent_username} ...')
        response = await self.challenger.create(challenge_request)

        if response.success:
            # Reserve a spot for this game
            self.reserved_game_spots += 1
        elif response.has_reached_rate_limit and self.challenge_requests:
            print('Challenge queue cleared due to rate limiting.')
            self.challenge_requests.clear()
        elif challenge_request in self.challenge_requests:
            print(f'Challenges against {challenge_request.opponent_username} removed from queue.')
            while challenge_request in self.challenge_requests:
                self.challenge_requests.remove(challenge_request)

    async def _decline_challenges(self, opponent_username: str) -> None:
        for challenge in list(self.open_challenges):
            if opponent_username == challenge.opponent_username:
                print(f'Declining challenge "{challenge.challenge_id}" due to inactivity ...')
                await self.api.decline_challenge(challenge.challenge_id, Decline_Reason.GENERIC)
                self.open_challenges.remove(challenge)
