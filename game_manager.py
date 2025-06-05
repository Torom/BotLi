import asyncio
from asyncio import Event, Task
from collections import deque
from typing import Any

from api import API
from botli_dataclasses import Challenge, Challenge_Request, Tournament, Tournament_Request
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
        self.started_game_events: deque[dict[str, Any]] = deque()
        self.tasks: dict[Task[None], Game] = {}
        self.tournament_requests: deque[Tournament_Request] = deque()
        self.tournament_ids_to_leave: deque[str] = deque()
        self.unstarted_tournaments: dict[str, Tournament] = {}
        self.tournaments_to_join: deque[Tournament] = deque()
        self.tournaments: dict[str, Tournament] = {}

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

            while started_game_event := self._get_next_started_game_event():
                await self._start_game(started_game_event)

            while self.tournament_ids_to_leave:
                await self._leave_tournament_id(self.tournament_ids_to_leave.popleft())

            while self.tournament_requests:
                await self._process_tournament_request(self.tournament_requests.popleft())

            while tournament := self._get_next_tournament_to_join():
                await self._join_tournament(tournament)

            while challenge := self._get_next_challenge():
                await self._accept_challenge(challenge)

            while challenge_request := self._get_next_challenge_request():
                await self._create_challenge(challenge_request)

        for tournament in self.unstarted_tournaments.values():
            tournament.cancel()

        for tournament in self.tournaments.values():
            tournament.cancel()
            await self.api.withdraw_tournament(tournament.id_)

        for task in list(self.tasks):
            await task

    @property
    def is_busy(self) -> bool:
        return len(self.tasks) + len(self.tournaments) + self.reserved_game_spots >= self.config.challenge.concurrency

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

    def on_game_started(self, game_event: dict[str, Any]) -> None:
        if game_event['id'] in {started_game_event['id'] for started_game_event in self.started_game_events}:
            return

        if game_event['id'] in {game.game_id for game in self.tasks.values()}:
            return

        self.started_game_events.append(game_event)
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

    def request_tournament_joining(self, tournament_id: str, team: str | None, password: str | None) -> None:
        self.tournament_requests.append(Tournament_Request(tournament_id, team, password))
        self.changed_event.set()

    def request_tournament_leaving(self, tournament_id: str) -> None:
        self.tournament_ids_to_leave.append(tournament_id)
        self.changed_event.set()

    async def _process_tournament_request(self, tournament_request: Tournament_Request) -> None:
        if tournament_request.id_ in self.tournaments:
            return

        tournament_info = await self.api.get_tournament_info(tournament_request.id_)
        if not tournament_info:
            print(f'Tournament "{tournament_request.id_}" not found.')
            return

        tournament = Tournament.from_tournament_info(tournament_info)
        tournament.team = tournament_request.team
        tournament.password = tournament_request.password

        if not tournament.bots_allowed:
            print(f'BOTs are not allowed in tournament "{tournament.name}".')
            return

        if tournament.seconds_to_start <= 0.0:
            self.tournaments_to_join.append(tournament)
            return

        tournament.start_task = asyncio.create_task(self._tournament_start_task(tournament))
        self.unstarted_tournaments[tournament.id_] = tournament
        print(f'Added tournament "{tournament.name}". Waiting for its start time to join.')

    async def _join_tournament(self, tournament: Tournament) -> None:
        if tournament.seconds_to_finish <= 0.0:
            print(f'Tournament "{tournament.name}" is already finished.')
            return

        if await self.api.join_tournament(tournament.id_, tournament.team, tournament.password):
            tournament.end_task = asyncio.create_task(self._tournament_end_task(tournament))
            self.tournaments[tournament.id_] = tournament
            print(f'Joined tournament "{tournament.name}". Awaiting games ...')

    async def _leave_tournament_id(self, tournament_id: str) -> None:
        if tournament := self.unstarted_tournaments.pop(tournament_id, None):
            tournament.cancel()
            print(f'Removed unstarted tournament "{tournament.name}".')
            return

        if tournament := self.tournaments.pop(tournament_id, None):
            await self.api.withdraw_tournament(tournament_id)
            tournament.cancel()
            print(f'Left tournament "{tournament.name}".')
            return

        for tournament in list(self.tournaments_to_join):
            if tournament.id_ == tournament_id:
                self.tournaments_to_join.remove(tournament)
                print(f'Removed unjoined tournament "{tournament.name}".')

    async def _tournament_start_task(self, tournament: Tournament) -> None:
        await asyncio.sleep(tournament.seconds_to_start)

        del self.unstarted_tournaments[tournament.id_]
        self.tournaments_to_join.append(tournament)
        print(f'Tournament "{tournament.name}" has started.')
        self.changed_event.set()

    async def _tournament_end_task(self, tournament: Tournament) -> None:
        await asyncio.sleep(tournament.seconds_to_finish)

        del self.tournaments[tournament.id_]
        print(f'Tournament "{tournament.name}" has ended.')
        self.changed_event.set()

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

    async def _start_game(self, game_event: dict[str, Any]) -> None:
        if self.reserved_game_spots > 0:
            self.reserved_game_spots -= 1

        if 'tournamentId' in game_event and game_event['tournamentId'] not in self.tournaments:
            tournament_info = await self.api.get_tournament_info(game_event['tournamentId'])
            tournament = Tournament.from_tournament_info(tournament_info)
            tournament.end_task = asyncio.create_task(self._tournament_end_task(tournament))
            self.tournaments[tournament.id_] = tournament
            print(f'External joined tournament "{tournament.name}" detected.')

        game = Game(self.api, self.config, self.username, game_event['id'])
        task = asyncio.create_task(game.run())
        task.add_done_callback(self._task_callback)
        self.tasks[task] = game

    def _get_next_challenge(self) -> Challenge | None:
        if not self.open_challenges:
            return

        if self.is_busy:
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

        if self.is_busy:
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

        if self.is_busy:
            return

        return self.challenge_requests.popleft()

    def _get_next_started_game_event(self) -> dict[str, Any] | None:
        if not self.started_game_events:
            return

        if len(self.tasks) >= self.config.challenge.concurrency:
            print('Max number of concurrent games exceeded. Ignoring already started game for now.')
            return

        return self.started_game_events.popleft()

    def _get_next_tournament_to_join(self) -> Tournament | None:
        if not self.tournaments_to_join:
            return

        if self.is_busy:
            return

        return self.tournaments_to_join.popleft()

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
