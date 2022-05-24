import json
import queue
import sys
from queue import Queue
from threading import Thread

from api import API
from enums import Decline_Reason
from game_manager import Game_Manager


class Event_Handler(Thread):
    def __init__(self, config: dict, api: API, game_manager: Game_Manager) -> None:
        Thread.__init__(self)
        self.daemon = True
        self.config = config
        self.api = api
        self.challenge_queue = Queue()
        self.game_manager = game_manager

    def start(self):
        Thread.start(self)

    def run(self) -> None:
        challenge_queue_thread = Thread(target=self._watch_challenge_stream, daemon=True)
        challenge_queue_thread.start()

        while True:
            try:
                event = self.challenge_queue.get(timeout=2)
            except queue.Empty:
                continue

            if event['type'] == 'challenge':
                challenger_name = event['challenge']['challenger']['name']

                if challenger_name == self.api.user['username']:
                    continue

                challenge_id = event['challenge']['id']
                challenger_title = event['challenge']['challenger']['title']
                challenger_title = challenger_title if challenger_title else ''
                challenger_rating = event['challenge']['challenger']['rating']
                tc = event['challenge']['timeControl'].get('show')
                rated = event['challenge']['rated']
                variant = event['challenge']['variant']['name']
                print(
                    f'ID: {challenge_id}\tChallenger: {challenger_title} {challenger_name} ({challenger_rating})\tTC: {tc}\tRated: {rated}\tVariant: {variant}')

                if decline_reason := self._get_decline_reason(event):
                    self.api.decline_challenge(challenge_id, decline_reason)
                    continue

                self.game_manager.add_challenge(challenge_id)
                print(f'Challenge "{challenge_id}" added to queue.')
            elif event['type'] == 'gameStart':
                game_id = event['game']['id']

                self.game_manager.on_game_started(game_id)
            elif event['type'] == 'gameFinish':
                game_id = event['game']['id']

                self.game_manager.on_game_finished(game_id)
            elif event['type'] == 'challengeDeclined':
                continue
            elif event['type'] == 'challengeCanceled':
                challenge_id = event['challenge']['id']
                self.game_manager.remove_challenge(challenge_id)
            else:
                print('Event type not caught:', file=sys.stderr)
                print(event)

    def _watch_challenge_stream(self) -> None:
        while True:
            try:
                event_stream = self.api.get_event_stream()
                for line in event_stream:
                    if line:
                        event = json.loads(line.decode('utf-8'))
                        self.challenge_queue.put_nowait(event)
            except Exception:
                pass

    def _get_decline_reason(self, event: dict) -> Decline_Reason | None:
        variants = self.config['challenge']['variants']
        time_controls = self.config['challenge']['time_controls']
        bullet_with_increment_only = self.config['challenge'].get('bullet_with_increment_only', False)
        min_increment = self.config['challenge'].get('min_increment', 0)
        max_increment = self.config['challenge'].get('max_increment', 180)
        min_initial = self.config['challenge'].get('min_initial', 0)
        max_initial = self.config['challenge'].get('max_initial', 315360000)
        is_bot = event['challenge']['challenger']['title'] == 'BOT'
        modes = self.config['challenge']['bot_modes'] if is_bot else self.config['challenge']['human_modes']

        if modes is None:
            if is_bot:
                print('Bots are not allowed according to config.')
                return Decline_Reason.NO_BOT
            else:
                print('Only bots are allowed according to config.')
                return Decline_Reason.ONLY_BOT

        variant = event['challenge']['variant']['key']
        if variant not in variants:
            print(f'Variant "{variant}" is not allowed according to config.')
            return Decline_Reason.VARIANT

        speed = event['challenge']['speed']
        increment = event['challenge']['timeControl'].get('increment')
        initial = event['challenge']['timeControl'].get('limit')
        if speed not in time_controls:
            print(f'Time control "{speed}" is not allowed according to config.')
            return Decline_Reason.TIME_CONTROL
        elif increment < min_increment:
            print(f'Increment {increment} is too short according to config.')
            return Decline_Reason.TOO_FAST
        elif increment > max_increment:
            print(f'Increment {increment} is too long according to config.')
            return Decline_Reason.TOO_SLOW
        elif initial < min_initial:
            print(f'Initial time {initial} is too short according to config.')
            return Decline_Reason.TOO_FAST
        elif initial > max_initial:
            print(f'Initial time {initial} is too long according to config.')
            return Decline_Reason.TOO_SLOW
        elif speed == 'bullet' and increment == 0 and bullet_with_increment_only:
            print('Bullet is only allowed with increment according to config.')
            return Decline_Reason.TOO_FAST

        is_rated = event['challenge']['rated']
        is_casual = not is_rated
        if is_rated and 'rated' not in modes:
            print(f'Rated is not allowed according to config.')
            return Decline_Reason.CASUAL
        elif is_casual and 'casual' not in modes:
            print(f'Casual is not allowed according to config.')
            return Decline_Reason.RATED
