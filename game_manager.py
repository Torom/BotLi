from collections import deque
from datetime import datetime, timedelta
from queue import Queue
from threading import Event, Thread

from api import API
from botli_dataclasses import Challenge, Challenge_Request
from challenger import Challenger
from config import Config
from enums import Decline_Reason
from game import Game
from matchmaking import Matchmaking
from pending_challenge import Pending_Challenge


class Game_Manager(Thread):
    def __init__(self, api: API, config: Config) -> None:
        Thread.__init__(self)
        self.config = config
        self.api = api
        self.is_running = True
        self.games: dict[str, Game] = {}
        self.open_challenges: deque[Challenge] = deque()
        self.reserved_game_spots = 0
        self.started_game_ids: deque[str] = deque()
        self.challenge_requests: deque[Challenge_Request] = deque()
        self.changed_event = Event()
        self.matchmaking = Matchmaking(api, config)
        self.current_matchmaking_game_id: str | None = None
        self.challenger = Challenger(api)
        self.is_rate_limited = False
        self.next_matchmaking = datetime.max
        self.matchmaking_delay = timedelta(seconds=config.matchmaking.delay)

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

            while challenge := self._get_next_challenge():
                self._accept_challenge(challenge)

        for game_id, game in self.games.items():
            game.join()

            if game_id == self.current_matchmaking_game_id:
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
                self.matchmaking.on_game_finished(game.lichess_game.is_abortable)
                self.current_matchmaking_game_id = None

            if game.has_timed_out:
                self._decline_challenges(game.game_info.black_name
                                         if game.lichess_game.is_white
                                         else game.game_info.white_name)

            self._delay_matchmaking(self.matchmaking_delay)

            del self.games[game_id]

    def _start_game(self, game_id: str) -> None:
        if game_id in self.games:
            return

        if self.reserved_game_spots > 0:
            # Remove reserved spot, if it exists:
            self.reserved_game_spots -= 1

        if len(self.games) >= self.config.challenge.concurrency:
            print(f'Max number of concurrent games exceeded. Aborting already started game {game_id}.')
            self.api.abort_game(game_id)
            return

        game_queue = Queue()
        Thread(target=self.api.get_game_stream, args=(game_id, game_queue), daemon=True).start()

        self.games[game_id] = Game(self.api, self.config, game_id, self.changed_event, game_queue)
        self.games[game_id].start()

    def _finish_game(self, game_id: str) -> None:
        self.games[game_id].join()
        del self.games[game_id]

    def _get_next_challenge(self) -> Challenge | None:
        if not self.open_challenges:
            return

        if len(self.games) + self.reserved_game_spots >= self.config.challenge.concurrency:
            return

        return self.open_challenges.popleft()

    def _accept_challenge(self, challenge: Challenge) -> None:
        if self.api.accept_challenge(challenge.challenge_id):
            # Reserve a spot for this game
            self.reserved_game_spots += 1
        else:
            print(f'Challenge "{challenge.challenge_id}" could not be accepted!')

    def _check_matchmaking(self) -> None:
        if self.current_matchmaking_game_id:
            # There is already a matchmaking game running
            return

        if len(self.games) + self.reserved_game_spots >= self.config.challenge.concurrency:
            return

        if self.next_matchmaking > datetime.now():
            return

        pending_challenge = Pending_Challenge()
        Thread(target=self.matchmaking.create_challenge, args=(pending_challenge,), daemon=True).start()

        self.current_matchmaking_game_id = pending_challenge.get_challenge_id()

        challenge_response = pending_challenge.get_final_state()
        self.is_rate_limited = False

        if challenge_response.success:
            # Reserve a spot for this game
            self.reserved_game_spots += 1
        else:
            self.current_matchmaking_game_id = None
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

    def _decline_challenges(self, opponent_username: str) -> None:
        for challenge in list(self.open_challenges):
            if opponent_username == challenge.opponent_username:
                print(f'Declining challenge "{challenge.challenge_id}" due to inactivity ...')
                self.api.decline_challenge(challenge.challenge_id, Decline_Reason.GENERIC)
                self.open_challenges.remove(challenge)
