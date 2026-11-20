import asyncio
from asyncio import Event, Future, Task
from collections import Counter, deque
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from typing import Any

from api import API
from botli_dataclasses import Challenge, ChallengeRequest, Tournament, TournamentRequest
from challenger import Challenger
from config import Config
from correspondence_game import CorrespondenceGame
from game import Game
from matchmaking import Matchmaking
from utils import GAME_COLORS, game_color, get_future_timestamp


class GameManager:
    def __init__(self, api: API, config: Config, username: str) -> None:
        self.api = api
        self.config = config
        self.username = username

        self.challenger = Challenger(api)
        self.changed_event = Event()
        self.matchmaking = Matchmaking(api, config, username)

        self.challenge_requests: deque[ChallengeRequest] = deque()
        self.current_matchmaking_game_id: str | None = None
        self.is_rate_limited = False
        self.is_running = True
        self.matchmaking_enabled = False
        self.next_matchmaking: float | None = None
        self._matchmaking_deferred = False
        self.open_challenges: list[Challenge] = []
        self.reserved_game_spots = 0
        self.started_game_events: list[dict[str, Any]] = []
        self.correspondence_slot_requests: deque[Future[None]] = deque()
        self.active_correspondence_moves = 0
        self.tasks: dict[Task[None], Game] = {}
        self.tournament_requests: deque[TournamentRequest] = deque()
        self.tournament_ids_to_leave: deque[str] = deque()
        self.unstarted_tournaments: dict[str, Tournament] = {}
        self.tournaments_to_join: deque[Tournament] = deque()
        self.tournaments: dict[str, Tournament] = {}
        self.track_tournaments_task: Task[None] | None = None

    def stop(self):
        self.is_running = False
        self.changed_event.set()

    async def run(self) -> None:
        if self.config.tournament.tracked_users or self.config.tournament.tracked_teams:
            self.track_tournaments_task = asyncio.create_task(self._track_tournaments())

        while self.is_running:
            timed_out = False
            try:
                async with asyncio.timeout_at(self.next_matchmaking):
                    await self.changed_event.wait()
            except TimeoutError:
                timed_out = True

            if not self.is_running:
                break

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

            if self._is_matchmaking_due(timed_out):
                await self._check_matchmaking()

            self._grant_correspondence_slots()

        if self.track_tournaments_task:
            self.track_tournaments_task.cancel()

        for tournament in self.unstarted_tournaments.values():
            tournament.cancel()

        for tournament in self.tournaments.values():
            tournament.cancel()
            await self.api.withdraw_tournament(tournament.id_)

        for game in list(self.tasks.values()):
            if isinstance(game, CorrespondenceGame):
                game.stop()

        for task in list(self.tasks):
            await task

    @property
    def live_task_count(self) -> int:
        return sum(1 for game in self.tasks.values() if not isinstance(game, CorrespondenceGame))

    @property
    def live_used_slots(self) -> int:
        return self.live_task_count + len(self.tournaments) + self.reserved_game_spots

    @property
    def used_slots(self) -> int:
        return self.live_used_slots + self.active_correspondence_moves

    @property
    def is_busy(self) -> bool:
        return self.used_slots >= self.config.challenge.concurrency

    @asynccontextmanager
    async def correspondence_slot(self) -> AsyncGenerator[None]:
        request: Future[None] = asyncio.get_running_loop().create_future()
        self.correspondence_slot_requests.append(request)
        self.changed_event.set()
        try:
            await request
            yield
        finally:
            with suppress(ValueError):
                self.correspondence_slot_requests.remove(request)
            if request.done() and not request.cancelled():
                self.active_correspondence_moves -= 1
            self.changed_event.set()

    def _grant_correspondence_slots(self) -> None:
        while not self.is_busy and self.correspondence_slot_requests:
            request = self.correspondence_slot_requests.popleft()
            if not request.done():
                request.set_result(None)
                self.active_correspondence_moves += 1

    def add_challenge(self, challenge: Challenge) -> None:
        if challenge not in self.open_challenges:
            self.open_challenges.append(challenge)
            self.changed_event.set()

    def request_challenge(self, *challenge_requests: ChallengeRequest) -> None:
        self.challenge_requests.extend(challenge_requests)
        self.changed_event.set()

    def remove_challenge(self, challenge: Challenge) -> None:
        if challenge in self.open_challenges:
            self.open_challenges.remove(challenge)
            self.changed_event.set()

    def on_game_started(self, game_event: dict[str, Any]) -> None:
        game_id: str = game_event["id"]
        if any(event["id"] == game_id for event in self.started_game_events):
            return

        if any(game.info.id_ == game_id for game in self.tasks.values()):
            return

        self.started_game_events.append(game_event)
        self.changed_event.set()

    def start_matchmaking(self) -> None:
        self.matchmaking_enabled = True
        self._set_next_matchmaking(1, force=True)
        self.changed_event.set()

    def stop_matchmaking(self) -> bool:
        if not self.matchmaking_enabled:
            return False

        self.matchmaking_enabled = False
        self.next_matchmaking = None
        self._matchmaking_deferred = False
        self.changed_event.set()
        return True

    def request_tournament_joining(self, tournament_id: str, team: str | None, password: str | None) -> None:
        self.tournament_requests.append(TournamentRequest(tournament_id, team, password))
        self.changed_event.set()

    def request_tournament_leaving(self, tournament_id: str) -> None:
        self.tournament_ids_to_leave.append(tournament_id)
        self.changed_event.set()

    async def _track_tournaments(self) -> None:
        while self.is_running:
            tournament_infos: list[dict[str, Any]] = []
            for user in self.config.tournament.tracked_users:
                tournament_infos.extend(info for info in await self.api.get_user_tournaments(user))

            for team_id in self.config.tournament.tracked_teams:
                tournament_infos.extend(info for info in await self.api.get_team_tournaments_created(team_id))
                tournament_infos.extend(info for info in await self.api.get_team_tournaments_started(team_id))

            tournaments: list[Tournament] = []
            for tournament_info in tournament_infos:
                if tournament_info["id"] in self.unstarted_tournaments:
                    continue

                if tournament_info["id"] in self.tournaments:
                    continue

                if tournament_info["id"] in {tournament.id_ for tournament in self.tournaments_to_join}:
                    continue

                if tournament_info["variant"]["key"] not in self.config.tournament.variants:
                    continue

                if "teamBattle" in tournament_info and (
                    self.config.tournament.own_team is None
                    or self.config.tournament.own_team not in tournament_info["teamBattle"]["teams"]
                ):
                    continue

                tournaments.append(
                    Tournament.from_tournament_info(
                        await self.api.get_tournament_info(tournament_info["id"]), self.config.tournament.waiting_period
                    )
                )

            tournaments.sort(key=lambda tournament: tournament.seconds_to_finish, reverse=True)
            tournaments.sort(key=lambda tournament: tournament.player_count, reverse=True)

            for tournament in tournaments:
                if not tournament.allowed_to_play:
                    continue

                if tournament.is_team_battle:
                    tournament.team = self.config.tournament.own_team

                if tournament.seconds_to_start <= 0.0:
                    self.tournaments_to_join.append(tournament)
                    continue

                tournament.start_task = asyncio.create_task(self._tournament_start_task(tournament))
                self.unstarted_tournaments[tournament.id_] = tournament
                print(f'Added tournament "{tournament.name}". Waiting for its start time to join.')

            await asyncio.sleep(900)

    async def _process_tournament_request(self, tournament_request: TournamentRequest) -> None:
        if tournament_request.id_ in self.unstarted_tournaments:
            return

        if tournament_request.id_ in self.tournaments:
            return

        if tournament_request.id_ in {tournament.id_ for tournament in self.tournaments_to_join}:
            return

        tournament_info = await self.api.get_tournament_info(tournament_request.id_)
        if not tournament_info:
            print(f'Tournament "{tournament_request.id_}" not found.')
            return

        tournament = Tournament.from_tournament_info(tournament_info, self.config.tournament.waiting_period)
        tournament.team = tournament_request.team
        tournament.password = tournament_request.password

        if not tournament.allowed_to_play:
            print(f'We don\'t fulfill the requirements for "{tournament.name}".')
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

        if tournament := self.tournaments.pop(tournament_id, None):
            await self.api.withdraw_tournament(tournament_id)
            tournament.cancel()
            print(f'Left tournament "{tournament.name}".')

        for tournament in list(self.tournaments_to_join):
            if tournament.id_ == tournament_id:
                self.tournaments_to_join.remove(tournament)
                print(f'Removed unjoined tournament "{tournament.name}".')

        self._set_next_matchmaking(1)

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
        self._set_next_matchmaking(self.config.matchmaking.delay)
        self.changed_event.set()

    def _set_next_matchmaking(self, delay: int, force: bool = False) -> None:
        self._matchmaking_deferred = False
        if not self.matchmaking_enabled:
            return

        if self.is_rate_limited and not force:
            return

        self.next_matchmaking = asyncio.get_running_loop().time() + delay

    async def _run_game_task(self, game: Game) -> None:
        try:
            await game.run()
        finally:
            task = asyncio.current_task()
            if task is not None:
                self.tasks.pop(task, None)

            if game.info.id_ == self.current_matchmaking_game_id:
                self.matchmaking.on_game_finished(game.was_aborted)
                self.current_matchmaking_game_id = None

            if game.ejected_tournament in self.tournaments:
                self.tournaments[game.ejected_tournament].cancel()
                del self.tournaments[game.ejected_tournament]
                print(f'Ignoring tournament "{game.ejected_tournament}" after failure to start the game.')

            if game.info.opponent_is_bot and not game.info.tournament_id:
                self.is_rate_limited = False

            if not isinstance(game, CorrespondenceGame):
                self._set_next_matchmaking(self.config.matchmaking.delay)

            self.changed_event.set()

    async def _start_game(self, game_event: dict[str, Any]) -> None:
        is_correspondence = game_event["speed"] == "correspondence"
        if not is_correspondence and self.reserved_game_spots > 0:
            self.reserved_game_spots -= 1

        if "tournamentId" in game_event and game_event["tournamentId"] not in self.tournaments:
            tournament_info = await self.api.get_tournament_info(game_event["tournamentId"])
            tournament = Tournament.from_tournament_info(tournament_info, self.config.tournament.waiting_period)
            tournament.end_task = asyncio.create_task(self._tournament_end_task(tournament))
            self.tournaments[tournament.id_] = tournament
            print(f'External joined tournament "{tournament.name}" detected.')

        color = self._get_next_game_color()
        token = game_color.set(color)
        try:
            if is_correspondence:
                game = await CorrespondenceGame.create(
                    self.api, self.config, self.username, game_event["id"], self.correspondence_slot, color
                )
            else:
                game = await Game.acreate(self.api, self.config, self.username, game_event["id"], color)
        finally:
            game_color.reset(token)

        task = asyncio.create_task(self._run_game_task(game))
        self.tasks[task] = game

    def _get_next_game_color(self) -> str | None:
        counts = Counter(game.color for game in self.tasks.values())
        return min(GAME_COLORS, key=counts.__getitem__)

    def _get_next_challenge(self) -> Challenge | None:
        eligible = [c for c in self.open_challenges if c.is_correspondence or not self.is_busy]
        if not eligible:
            return

        challenge = min(eligible, key=lambda c: c.priority)
        self.open_challenges.remove(challenge)
        return challenge

    async def _accept_challenge(self, challenge: Challenge) -> None:
        if await self.api.accept_challenge(challenge.challenge_id) and not challenge.is_correspondence:
            self.reserved_game_spots += 1

    def _is_matchmaking_due(self, timed_out: bool) -> bool:
        if timed_out or self._matchmaking_deferred:
            return True

        return self.next_matchmaking is not None and asyncio.get_running_loop().time() >= self.next_matchmaking

    async def _check_matchmaking(self) -> None:
        self.next_matchmaking = None
        self._matchmaking_deferred = False
        self.is_rate_limited = False

        if self.current_matchmaking_game_id:
            return

        if self.is_busy:
            if (
                self.matchmaking_enabled
                and self.active_correspondence_moves
                and self.live_used_slots < self.config.challenge.concurrency
            ):
                self._matchmaking_deferred = True
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
            wait_seconds = 3600 if challenge_response.wait_seconds is None else challenge_response.wait_seconds
            self._set_next_matchmaking(wait_seconds)
            print(f"Matchmaking has reached rate limit, next attempt at {get_future_timestamp(wait_seconds)}.")
            self.is_rate_limited = True
        elif challenge_response.is_misconfigured:
            print("Matchmaking stopped due to misconfiguration.")
            self.stop_matchmaking()
        else:
            self._set_next_matchmaking(1)

    def _get_next_challenge_request(self) -> ChallengeRequest | None:
        for request in self.challenge_requests:
            if request.is_correspondence or not self.is_busy:
                self.challenge_requests.remove(request)
                return request

    def _get_next_started_game_event(self) -> dict[str, Any] | None:
        if not self.started_game_events:
            return

        can_start_live = self.live_task_count + self.active_correspondence_moves < self.config.challenge.concurrency
        for event in self.started_game_events:
            if event["speed"] == "correspondence" or can_start_live:
                self.started_game_events.remove(event)
                return event

        print("Max number of concurrent games exceeded. Ignoring already started game for now.")

    def _get_next_tournament_to_join(self) -> Tournament | None:
        if not self.tournaments_to_join:
            return

        if self.is_busy:
            return

        return self.tournaments_to_join.popleft()

    async def _create_challenge(self, challenge_request: ChallengeRequest) -> None:
        print(f"Challenging {challenge_request.opponent_username} ...")
        response = await self.challenger.create(challenge_request)

        if response.success:
            self.reserved_game_spots += 1
        elif response.was_created:
            return
        elif response.has_reached_rate_limit:
            if response.wait_seconds is not None:
                print(f"Don't create new challenges before {get_future_timestamp(response.wait_seconds)}!")
            if self.challenge_requests:
                print("Challenge queue cleared due to rate limiting.")
                self.challenge_requests.clear()
        elif challenge_request in self.challenge_requests:
            print(f"Challenges against {challenge_request.opponent_username} removed from queue.")
            while challenge_request in self.challenge_requests:
                self.challenge_requests.remove(challenge_request)
