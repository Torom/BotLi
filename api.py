import json
import logging
from queue import Queue
from typing import Any

import requests
from requests.compat import urljoin
from tenacity import after_log, retry, retry_if_exception_type

from botli_dataclasses import API_Challenge_Reponse, Challenge_Request
from enums import Decline_Reason, Variant

logger = logging.getLogger(__name__)


class API:
    def __init__(self, config: dict) -> None:
        self.urls = self._get_urls(config)
        self.session = requests.session()
        self.session.headers.update({'Authorization': f'Bearer {config["token"]}',
                                     'User-Agent': f'BotLi/{config["version"]}'})

    def set_user_agent(self, version: str, username: str) -> None:
        self.session.headers.update({'User-Agent': f'BotLi/{version} user:{username}'})

    @retry(retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
           after=after_log(logger, logging.DEBUG))
    def abort_game(self, game_id: str) -> bool:
        try:
            response = self.session.post(self.urls['abort_game'].format(game_id), timeout=3.0)
            response.raise_for_status()
            return True
        except requests.HTTPError as e:
            print(e)
            return False

    @retry(retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
           after=after_log(logger, logging.DEBUG))
    def accept_challenge(self, challenge_id: str) -> bool:
        try:
            response = self.session.post(self.urls['accept_challenge'].format(challenge_id), timeout=3.0)
            response.raise_for_status()
            return True
        except requests.HTTPError as e:
            print(e)
            return False

    @retry(retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
           after=after_log(logger, logging.DEBUG))
    def cancel_challenge(self, challenge_id: str) -> bool:
        try:
            response = self.session.post(self.urls['cancel_challenge'].format(challenge_id), timeout=3.0)
            response.raise_for_status()
            return True
        except requests.HTTPError as e:
            print(e)
            return False

    @retry(retry=retry_if_exception_type(requests.ConnectionError),
           after=after_log(logger, logging.DEBUG))
    def create_challenge(self,
                         challenge_request: Challenge_Request,
                         response_queue: Queue[API_Challenge_Reponse]
                         ) -> None:
        response = self.session.post(
            self.urls['create_challenge'].format(challenge_request.opponent_username),
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
            invalid_initial = 'clock.limit' in data
            invalid_increment = 'clock.increment' in data
            response_queue.put(API_Challenge_Reponse(challenge_id, was_accepted, error,
                               was_declined, invalid_initial, invalid_increment))

    @retry(retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
           after=after_log(logger, logging.DEBUG))
    def decline_challenge(self, challenge_id: str, reason: Decline_Reason) -> bool:
        try:
            response = self.session.post(self.urls['decline_challenge'].format(challenge_id),
                                         data={'reason': reason.value}, timeout=3.0)
            response.raise_for_status()
            return True
        except requests.HTTPError as e:
            print(e)
            return False

    def download_usernames(self, url: str) -> list[str]:
        try:
            response = self.session.get(url, headers={'Authorization': None}, timeout=5.0)
            response.raise_for_status()
            return response.text.splitlines()
        except (requests.Timeout, requests.HTTPError, requests.ConnectionError) as e:
            print(e)
            return []

    @retry(retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
           after=after_log(logger, logging.DEBUG))
    def get_account(self) -> dict[str, Any]:
        response = self.session.get(self.urls['get_account'], timeout=3.0)
        json_response = response.json()
        if 'error' in json_response:
            raise RuntimeError(f'Account error: {json_response["error"]}')

        return json_response

    def get_chessdb_eval(self, fen: str, best_move: bool, timeout: int) -> dict[str, Any] | None:
        try:
            response = self.session.get('http://www.chessdb.cn/cdb.php',
                                        params={'action': 'querypv',
                                                'board': fen,
                                                'stable': int(best_move),
                                                'json': 1},
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
        response = self.session.get(self.urls['get_event_stream'], stream=True, timeout=9.0)
        for line in filter(None, response.iter_lines()):
            queue.put(json.loads(line))

    @retry(after=after_log(logger, logging.DEBUG))
    def get_game_stream(self, game_id: str, queue: Queue) -> None:
        response = self.session.get(self.urls['get_game_stream'].format(game_id), stream=True, timeout=9.0)
        for line in response.iter_lines():
            event = json.loads(line) if line else {'type': 'ping'}
            queue.put(event)

    @retry(after=after_log(logger, logging.DEBUG))
    def get_online_bots_stream(self) -> list[dict[str, Any]]:
        response = self.session.get(self.urls['get_online_bots_stream'], stream=True, timeout=9.0)
        return [json.loads(line) for line in response.iter_lines() if line]

    def get_opening_explorer(self,
                             username: str,
                             fen: str,
                             variant: Variant,
                             color: str,
                             timeout: int
                             ) -> dict[str, Any] | None:
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

    @retry(retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
           after=after_log(logger, logging.DEBUG))
    def get_token_scopes(self, token: str) -> str:
        response = self.session.post(self.urls['get_token_scopes'], data=token, timeout=3.0)
        return response.json()[token]['scopes']

    @retry(retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
           after=after_log(logger, logging.DEBUG))
    def get_user_status(self, username: str) -> dict[str, Any]:
        response = self.session.get(self.urls['get_user_status'], params={'ids': username}, timeout=3.0)
        return response.json()[0]

    @retry(retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
           after=after_log(logger, logging.DEBUG))
    def resign_game(self, game_id: str) -> bool:
        try:
            response = self.session.post(self.urls['resign_game'].format(game_id), timeout=3.0)
            response.raise_for_status()
            return True
        except requests.HTTPError as e:
            print(e)
            return False

    def send_chat_message(self, game_id: str, room: str, text: str) -> bool:
        try:
            response = self.session.post(self.urls['send_chat_message'].format(game_id),
                                         data={'room': room, 'text': text}, timeout=1.0)
            response.raise_for_status()
            return True
        except (requests.HTTPError, requests.ConnectionError, requests.Timeout) as e:
            print(e)
            return False

    @retry(retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
           after=after_log(logger, logging.DEBUG))
    def send_move(self, game_id: str, uci_move: str, offer_draw: bool) -> bool:
        try:
            response = self.session.post(self.urls['send_move'].format(game_id, uci_move),
                                         params={'offeringDraw': str(offer_draw).lower()}, timeout=1.0)
            response.raise_for_status()
            return True
        except requests.HTTPError as e:
            print(e)
            return False

    @retry(retry=retry_if_exception_type(requests.ConnectionError),
           after=after_log(logger, logging.DEBUG))
    def upgrade_account(self) -> bool:
        try:
            response = self.session.post(self.urls['upgrade_account'])
            response.raise_for_status()
            return True
        except requests.HTTPError as e:
            print(e)
            return False

    def _get_urls(self, config: dict[str, Any]) -> dict[str, str]:
        url = config.get('url', 'https://lichess.org')
        return {
            'abort_game': urljoin(url, '/api/bot/game/{0}/abort'),
            'accept_challenge': urljoin(url, '/api/challenge/{0}/accept'),
            'cancel_challenge': urljoin(url, '/api/challenge/{0}/cancel'),
            'create_challenge': urljoin(url, '/api/challenge/{0}'),
            'decline_challenge': urljoin(url, '/api/challenge/{0}/decline'),
            'get_account': urljoin(url, '/api/account'),
            'get_event_stream': urljoin(url, '/api/stream/event'),
            'get_game_stream': urljoin(url, '/api/bot/game/stream/{0}'),
            'get_online_bots_stream': urljoin(url, '/api/bot/online'),
            'get_token_scopes': urljoin(url, '/api/token/test'),
            'get_user_status': urljoin(url, '/api/users/status'),
            'resign_game': urljoin(url, '/api/bot/game/{0}/resign'),
            'send_chat_message': urljoin(url, '/api/bot/game/{0}/chat'),
            'send_move': urljoin(url, '/api/bot/game/{0}/move/{1}'),
            'upgrade_account': urljoin(url, '/api/bot/account/upgrade')
        }
