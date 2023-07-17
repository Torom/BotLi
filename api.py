import json
import logging
from queue import Queue
from typing import Any

import requests
from tenacity import after_log, retry, retry_if_exception_type

from botli_dataclasses import API_Challenge_Reponse, Challenge_Request
from enums import Decline_Reason, Variant

logger = logging.getLogger(__name__)


class API:
    def __init__(self, config: dict) -> None:
        self.session = requests.session()
        self.session.headers.update({'Authorization': f'Bearer {config["token"]}'})
        self.session.headers.update({'User-Agent': f'BotLi/{config["version"]}'})

        account = self.get_account()
        self.username: str = account['username']
        self.user_title: str | None = account.get('title')
        self.session.headers.update({'User-Agent': f'BotLi/{config["version"]} user:{self.username}'})

    @retry(retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)), after=after_log(logger, logging.DEBUG))
    def abort_game(self, game_id: str) -> bool:
        try:
            response = self.session.post(f'https://lichess.org/api/bot/game/{game_id}/abort', timeout=3.0)
            response.raise_for_status()
            return True
        except requests.HTTPError as e:
            print(e)
            return False

    @retry(retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)), after=after_log(logger, logging.DEBUG))
    def accept_challenge(self, challenge_id: str) -> bool:
        try:
            response = self.session.post(f'https://lichess.org/api/challenge/{challenge_id}/accept', timeout=3.0)
            response.raise_for_status()
            return True
        except requests.HTTPError as e:
            print(e)
            return False

    @retry(retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)), after=after_log(logger, logging.DEBUG))
    def cancel_challenge(self, challenge_id: str) -> bool:
        try:
            response = self.session.post(f'https://lichess.org/api/challenge/{challenge_id}/cancel', timeout=3.0)
            response.raise_for_status()
            return True
        except requests.HTTPError as e:
            print(e)
            return False

    @retry(retry=retry_if_exception_type(requests.ConnectionError), after=after_log(logger, logging.DEBUG))
    def create_challenge(self, challenge_request: Challenge_Request, response_queue: Queue[API_Challenge_Reponse]) -> None:
        response = self.session.post(
            f'https://lichess.org/api/challenge/{challenge_request.opponent_username}',
            data={'rated': str(challenge_request.rated).lower(),
                  'clock.limit': challenge_request.initial_time, 'clock.increment': challenge_request.increment,
                  'color': challenge_request.color.value, 'variant': challenge_request.variant.value,
                  'keepAliveStream': 'true'},
            stream=True)

        if response.status_code == 429:
            response_queue.put(API_Challenge_Reponse(has_reached_rate_limit=True))
            return

        for line in filter(None, response.iter_lines()):
            data = json.loads(line)
            challenge_id = data.get('challenge', {'id': None}).get('id')
            was_accepted = data.get('done') == 'accepted'
            error = data.get('error')
            was_declined = data.get('done') == 'declined'
            invalid_initial = 'Invalid value' in data.get('clock.limit', [])
            invalid_increment = 'Invalid value' in data.get('clock.increment', [])
            response_queue.put(API_Challenge_Reponse(challenge_id, was_accepted, error,
                               was_declined, invalid_initial, invalid_increment))

    @retry(retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)), after=after_log(logger, logging.DEBUG))
    def decline_challenge(self, challenge_id: str, reason: Decline_Reason) -> bool:
        try:
            response = self.session.post(f'https://lichess.org/api/challenge/{challenge_id}/decline',
                                         data={'reason': reason.value}, timeout=3.0)
            response.raise_for_status()
            return True
        except requests.HTTPError as e:
            print(e)
            return False

    @retry(retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)), after=after_log(logger, logging.DEBUG))
    def get_account(self) -> dict[str, Any]:
        response = self.session.get('https://lichess.org/api/account', timeout=3.0)
        return response.json()

    def get_chessdb_eval(self, fen: str, timeout: int) -> dict[str, Any] | None:
        try:
            response = self.session.get('http://www.chessdb.cn/cdb.php',
                                        params={'action': 'querypv', 'board': fen, 'json': 1},
                                        headers={'Authorization': None},
                                        timeout=timeout)
            response.raise_for_status()
            return response.json()
        except (requests.Timeout, requests.HTTPError, requests.ConnectionError) as e:
            print(e)

    def get_cloud_eval(self, fen: str, variant: Variant, timeout: int) -> dict[str, Any] | None:
        try:
            response = self.session.get('https://lichess.org/api/cloud-eval',
                                        params={'fen': fen, 'variant': variant.value}, timeout=timeout)
            return response.json()
        except (requests.Timeout, requests.ConnectionError) as e:
            print(e)

    def get_egtb(self, fen: str, variant: str, timeout: int) -> dict[str, Any] | None:
        try:
            response = self.session.get(
                f'https://tablebase.lichess.ovh/{variant}', params={'fen': fen},
                headers={'Authorization': None},
                timeout=timeout)
            response.raise_for_status()
            return response.json()
        except (requests.Timeout, requests.HTTPError, requests.ConnectionError) as e:
            print(e)

    @retry(after=after_log(logger, logging.DEBUG))
    def get_event_stream(self, queue: Queue) -> None:
        response = self.session.get('https://lichess.org/api/stream/event', stream=True, timeout=9.0)
        for line in filter(None, response.iter_lines()):
            queue.put(json.loads(line))

    @retry(after=after_log(logger, logging.DEBUG))
    def get_game_stream(self, game_id: str, queue: Queue) -> None:
        response = self.session.get(f'https://lichess.org/api/bot/game/stream/{game_id}', stream=True, timeout=9.0)
        for line in response.iter_lines():
            event = json.loads(line) if line else {'type': 'ping'}
            queue.put(event)

    @retry(after=after_log(logger, logging.DEBUG))
    def get_online_bots_stream(self) -> list[dict[str, Any]]:
        response = self.session.get('https://lichess.org/api/bot/online', stream=True, timeout=9.0)
        return [json.loads(line) for line in response.iter_lines() if line]

    def get_opening_explorer(self, username: str, fen: str, variant: Variant, color: str, timeout: int) -> dict[str, Any] | None:
        try:
            response = self.session.get('https://explorer.lichess.ovh/player',
                                        params={'player': username, 'variant': variant.value, 'fen': fen,
                                                'color': color, 'speeds': 'bullet,blitz,rapid,classical',
                                                'modes': 'rated', 'recentGames': 0},
                                        headers={'Authorization': None},
                                        stream=True, timeout=timeout)
            response.raise_for_status()
            first_line = next(filter(None, response.iter_lines()))
            return json.loads(first_line)
        except (requests.Timeout, requests.HTTPError, requests.ConnectionError) as e:
            print(e)

    @retry(retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)), after=after_log(logger, logging.DEBUG))
    def get_token_scopes(self, token: str) -> str:
        response = self.session.post('https://lichess.org/api/token/test', data=token, timeout=3.0)
        return response.json()[token]['scopes']

    @retry(retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)), after=after_log(logger, logging.DEBUG))
    def get_user_status(self, username: str) -> dict[str, Any]:
        response = self.session.get('https://lichess.org/api/users/status', params={'ids': username}, timeout=3.0)
        return response.json()[0]

    @retry(retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)), after=after_log(logger, logging.DEBUG))
    def resign_game(self, game_id: str) -> bool:
        try:
            response = self.session.post(f'https://lichess.org/api/bot/game/{game_id}/resign', timeout=3.0)
            response.raise_for_status()
            return True
        except requests.HTTPError as e:
            print(e)
            return False

    def send_chat_message(self, game_id: str, room: str, text: str) -> bool:
        try:
            response = self.session.post(f'https://lichess.org/api/bot/game/{game_id}/chat',
                                         data={'room': room, 'text': text}, timeout=1.0)
            response.raise_for_status()
            return True
        except (requests.HTTPError, requests.ConnectionError, requests.Timeout) as e:
            print(e)
            return False

    @retry(retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)), after=after_log(logger, logging.DEBUG))
    def send_move(self, game_id: str, uci_move: str, offer_draw: bool) -> bool:
        try:
            response = self.session.post(f'https://lichess.org/api/bot/game/{game_id}/move/{uci_move}',
                                         params={'offeringDraw': str(offer_draw).lower()}, timeout=1.0)
            response.raise_for_status()
            return True
        except requests.HTTPError as e:
            print(e)
            return False

    @retry(retry=retry_if_exception_type(requests.ConnectionError), after=after_log(logger, logging.DEBUG))
    def upgrade_account(self) -> bool:
        try:
            response = self.session.post('https://lichess.org/api/bot/account/upgrade')
            response.raise_for_status()
            return True
        except requests.HTTPError as e:
            print(e)
            return False
