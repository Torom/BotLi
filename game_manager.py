import asyncio
from asyncio import Event, Task
from collections import deque

from api import API
from botli_dataclasses import Challenge, Challenge_Request
from challenger import Challenger
from config import Config
from game import Game
from matchmaking import Matchmaking


class Game_Manager:
    def __init__(self, api: API, config: Config, username: str) -> None:
        self.api = api
        self.config = config
        self.username = username

        self.challenger = Challenger(api)
        self.changed_event = Event()
        self.matchmaking = Matchmaking(api, config, username)

        self.challenge_requests: deque[Challenge_Request] = deque()
        self.current_matchmaking_game_id: str | None = None
        self.is_rate_limited = False
        self.is_running = True
        self.matchmaking_enabled = False
        self.next_matchmaking: float | None = None
        self.open_challenges: deque[Challenge] = deque()
        self.reserved_game_spots = 0
        self.started_game_ids: deque[str] = deque()
        self.tasks: dict[Task[None], Game] = {}

    def stop(self):
        self.is_running = False
        self.changed_event.set()

    async def run(self) -> None:
        while self.is_running:
            try:
                async with asyncio.timeout_at(self.next_matchmaking):
                    await self.changed_event.wait()
            except TimeoutError:
                await self._check_matchmaking()
                continue

            self.changed_event.clear()

            while self.started_game_ids:
                await self._start_game(self.started_game_ids.popleft())

            while challenge_request := self._get_next_challenge_request():
                await self._create_challenge(challenge_request)

            while challenge := self._get_next_challenge():
                await self._accept_challenge(challenge)

        for task in list(self.tasks):
            await task

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
        self.matchmaking_enabled = True
        self._set_next_matchmaking(1)
        self.changed_event.set()

    def stop_matchmaking(self) -> bool:
        if not self.matchmaking_enabled:
            return False

        self.matchmaking_enabled = False
        self.next_matchmaking = None
        self.changed_event.set()
        return True

    def _set_next_matchmaking(self, delay: int) -> None:
        if not self.matchmaking_enabled:
            return

        if self.is_rate_limited:
            return

        self.next_matchmaking = asyncio.get_running_loop().time() + delay

    def _task_callback(self, task: Task[None]) -> None:
        game = self.tasks.pop(task)

        if game.game_id == self.current_matchmaking_game_id:
            self.matchmaking.on_game_finished(game.was_aborted)
            self.current_matchmaking_game_id = None

        self._set_next_matchmaking(self.config.matchmaking.delay)
        self.changed_event.set()

    async def _start_game(self, game_id: str) -> None:
        if game_id in {game.game_id for game in self.tasks.values()}:
            return

        if self.reserved_game_spots > 0:
            self.reserved_game_spots -= 1

        if len(self.tasks) >= self.config.challenge.concurrency:
            print(f'Max number of concurrent games exceeded. Aborting already started game {game_id}.')
            await self.api.abort_game(game_id)
            return

        game = Game(self.api, self.config, self.username, game_id)
        task = asyncio.create_task(game.run())
        task.add_done_callback(self._task_callback)
        self.tasks[task] = game

    def _get_next_challenge(self) -> Challenge | None:
        if not self.open_challenges:
            return

        if len(self.tasks) + self.reserved_game_spots >= self.config.challenge.concurrency:
            return

        return self.open_challenges.popleft()

    async def _accept_challenge(self, challenge: Challenge) -> None:
        if await self.api.accept_challenge(challenge.challenge_id):
            self.reserved_game_spots += 1
        else:
            print(f'Challenge "{challenge.challenge_id}" could not be accepted!')

    async def _check_matchmaking(self) -> None:
        self.next_matchmaking = None
        self.is_rate_limited = False

        if self.current_matchmaking_game_id:
            return

        if len(self.tasks) + self.reserved_game_spots >= self.config.challenge.concurrency:
            return

        challenge_response = await self.matchmaking.create_challenge()
        if challenge_response is None:
            self._set_next_matchmaking(1)
            return

        if challenge_response.success:
            self.reserved_game_spots += 1
            self.current_matchmaking_game_id = challenge_response.challenge_id
            return

        if challenge_response.no_opponent:
            self._set_next_matchmaking(self.config.matchmaking.delay)
        elif challenge_response.has_reached_rate_limit:
            self._set_next_matchmaking(3600)
            print('Matchmaking has reached rate limit, next attempt in one hour.')
            self.is_rate_limited = True
        elif challenge_response.is_misconfigured:
            print('Matchmaking stopped due to misconfiguration.')
            self.stop_matchmaking()
        else:
            self._set_next_matchmaking(1)

    def _get_next_challenge_request(self) -> Challenge_Request | None:
        if not self.challenge_requests:
            return

        if len(self.tasks) + self.reserved_game_spots >= self.config.challenge.concurrency:
            return

        return self.challenge_requests.popleft()

    async def _create_challenge(self, challenge_request: Challenge_Request) -> None:
        print(f'Challenging {challenge_request.opponent_username} ...')
        response = await self.challenger.create(challenge_request)

        if response.success:
            self.reserved_game_spots += 1
        elif response.has_reached_rate_limit and self.challenge_requests:
            print('Challenge queue cleared due to rate limiting.')
            self.challenge_requests.clear()
        elif challenge_request in self.challenge_requests:
            print(f'Challenges against {challenge_request.opponent_username} removed from queue.')
            while challenge_request in self.challenge_requests:
                self.challenge_requests.remove(challenge_request)
