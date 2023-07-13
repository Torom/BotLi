from collections import deque
from datetime import datetime, timedelta
from threading import Event, Thread

from aliases import Challenge_ID, Game_ID
from api import API
from botli_dataclasses import Challenge_Request
from challenger import Challenger
from game import Game
from matchmaking import Matchmaking
from pending_challenge import Pending_Challenge


class Game_Manager(Thread):
    def __init__(self, config: dict, api: API) -> None:
        Thread.__init__(self)
        self.config = config
        self.api = api
        self.is_running = True
        self.games: dict[Game_ID, Game] = {}
        self.open_challenge_ids: deque[Challenge_ID] = deque()
        self.reserved_game_spots = 0
        self.started_game_ids: deque[Game_ID] = deque()
        self.challenge_requests: deque[Challenge_Request] = deque()
        self.changed_event = Event()
        self.matchmaking = Matchmaking(self.config, self.api)
        self.current_matchmaking_game_id: Game_ID | None = None
        self.challenger = Challenger(self.config, self.api)
        self.is_rate_limited = False
        self.next_matchmaking = datetime.max
        self.matchmaking_delay = timedelta(seconds=config['matchmaking'].get('delay', 10))
        self.concurrency: int = config['challenge'].get('concurrency', 1)

    def start(self):
        Thread.start(self)

    def stop(self):
        self.is_running = False
        self.changed_event.set()

    def run(self) -> None:
        while self.is_running:
            event_received = self.changed_event.wait(1.0)
            if not event_received:
                self._check_matchmaking()
                continue

            self.changed_event.clear()

            self._check_for_finished_games()

            while self.started_game_ids:
                self._start_game(self.started_game_ids.popleft())

            while challenge_request := self._get_next_challenge_request():
                self._create_challenge(challenge_request)

            while challenge_id := self._get_next_challenge_id():
                self._accept_challenge(challenge_id)

        for game_id, game in self.games.items():
            game.join()

            if game_id == self.current_matchmaking_game_id:
                self.matchmaking.on_game_finished(game)

    def add_challenge(self, challenge_id: Challenge_ID) -> None:
        if challenge_id not in self.open_challenge_ids:
            self.open_challenge_ids.append(challenge_id)
            self.changed_event.set()

    def request_challenge(self, *challenge_requests: Challenge_Request) -> None:
        self.challenge_requests.extend(challenge_requests)
        self.changed_event.set()

    def remove_challenge(self, challenge_id: Challenge_ID) -> None:
        if challenge_id in self.open_challenge_ids:
            self.open_challenge_ids.remove(challenge_id)
            self.changed_event.set()

    def on_game_started(self, game_id: Game_ID) -> None:
        self.started_game_ids.append(game_id)
        if game_id == self.current_matchmaking_game_id:
            self.matchmaking.on_game_started()
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

    def _check_for_finished_games(self) -> None:
        for game_id, game in list(self.games.items()):
            if game.is_alive():
                continue

            if game_id == self.current_matchmaking_game_id:
                self.matchmaking.on_game_finished(game)
                self.current_matchmaking_game_id = None

            self._delay_matchmaking(self.matchmaking_delay)

            del self.games[game_id]

    def _start_game(self, game_id: Game_ID) -> None:
        if game_id in self.games:
            return

        if self.reserved_game_spots > 0:
            # Remove reserved spot, if it exists:
            self.reserved_game_spots -= 1

        if len(self.games) >= self.concurrency:
            print(f'Max number of concurrent games exceeded. Aborting already started game {game_id}.')
            self.api.abort_game(game_id)
            return

        self.games[game_id] = Game(self.config, self.api, game_id, self.changed_event)
        self.games[game_id].start()

    def _finish_game(self, game_id: Game_ID) -> None:
        self.games[game_id].join()
        del self.games[game_id]

    def _get_next_challenge_id(self) -> Challenge_ID | None:
        if not self.open_challenge_ids:
            return

        if len(self.games) + self.reserved_game_spots >= self.concurrency:
            return

        return self.open_challenge_ids.popleft()

    def _accept_challenge(self, challenge_id: Challenge_ID) -> None:
        if self.api.accept_challenge(challenge_id):
            # Reserve a spot for this game
            self.reserved_game_spots += 1
        else:
            print(f'Challenge "{challenge_id}" could not be accepted!')

    def _check_matchmaking(self) -> None:
        if self.next_matchmaking > datetime.now():
            return

        if len(self.games) + self.reserved_game_spots >= self.concurrency:
            return

        if self.current_matchmaking_game_id:
            # There is already a matchmaking game running
            return

        pending_challenge = Pending_Challenge()
        Thread(target=self.matchmaking.create_challenge, args=(pending_challenge,), daemon=True).start()

        challenge_id = pending_challenge.get_challenge_id()
        self.current_matchmaking_game_id = challenge_id

        success, has_reached_rate_limit, is_misconfigured = pending_challenge.get_final_state()
        self.is_rate_limited = False

        if success:
            # Reserve a spot for this game
            self.reserved_game_spots += 1
        else:
            self.current_matchmaking_game_id = None
            if has_reached_rate_limit:
                self._delay_matchmaking(timedelta(hours=1.0))
                next_matchmaking_str = self.next_matchmaking.isoformat(sep=' ', timespec='seconds')
                print(f'Matchmaking has reached rate limit, next attempt at {next_matchmaking_str}.')
                self.is_rate_limited = True
            if is_misconfigured:
                print('Matchmaking stopped due to misconfiguration.')
                self.stop_matchmaking()

    def _get_next_challenge_request(self) -> Challenge_Request | None:
        if not self.challenge_requests:
            return

        if len(self.games) + self.reserved_game_spots >= self.concurrency:
            return

        return self.challenge_requests.popleft()

    def _create_challenge(self, challenge_request: Challenge_Request) -> None:
        print(f'Challenging {challenge_request.opponent_username} ...')
        *_, last_response = self.challenger.create(challenge_request)

        if last_response.success:
            # Reserve a spot for this game
            self.reserved_game_spots += 1
        elif last_response.has_reached_rate_limit and self.challenge_requests:
            print('Challenge queue cleared due to rate limiting.')
            self.challenge_requests.clear()
        elif challenge_request in self.challenge_requests:
            print(f'Challenges against {challenge_request.opponent_username} removed from queue.')
            while challenge_request in self.challenge_requests:
                self.challenge_requests.remove(challenge_request)
