import json
import logging
from queue import Queue
from typing import Any

import httpx
from tenacity import after_log, retry, retry_if_exception_type

from botli_dataclasses import API_Challenge_Reponse, Challenge_Request
from config import Config
from enums import Decline_Reason, Variant

logger = logging.getLogger(__name__)


class API:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.lichess_client = httpx.Client(base_url=config.url, headers={'Authorization': f'Bearer {config.token}',
                                                                         'User-Agent': f'BotLi/{config.version}'})
        self.external_client = httpx.Client(headers={'User-Agent': f'BotLi/{config.version}'})

    def set_user_agent(self) -> None:
        self.lichess_client.headers.update({'User-Agent': f'BotLi/{self.config.version} user:{self.config.username}'})
        self.external_client.headers.update({'User-Agent': f'BotLi/{self.config.version} user:{self.config.username}'})

    @retry(retry=retry_if_exception_type(httpx.RequestError), after=after_log(logger, logging.DEBUG))
    def abort_game(self, game_id: str) -> bool:
        try:
            response = self.lichess_client.post(f'/api/bot/game/{game_id}/abort')
            response.raise_for_status()
            return True
        except httpx.HTTPStatusError as e:
            print(e)
            return False

    @retry(retry=retry_if_exception_type(httpx.RequestError), after=after_log(logger, logging.DEBUG))
    def accept_challenge(self, challenge_id: str) -> bool:
        try:
            response = self.lichess_client.post(f'/api/challenge/{challenge_id}/accept')
            response.raise_for_status()
            return True
        except httpx.HTTPStatusError as e:
            print(e)
            return False

    @retry(retry=retry_if_exception_type(httpx.RequestError), after=after_log(logger, logging.DEBUG))
    def cancel_challenge(self, challenge_id: str) -> bool:
        try:
            response = self.lichess_client.post(f'/api/challenge/{challenge_id}/cancel')
            response.raise_for_status()
            return True
        except httpx.HTTPStatusError as e:
            print(e)
            return False

    @retry(retry=retry_if_exception_type(httpx.RequestError), after=after_log(logger, logging.DEBUG))
    def create_challenge(self,
                         challenge_request: Challenge_Request,
                         response_queue: Queue[API_Challenge_Reponse]
                         ) -> None:
        with self.lichess_client.stream('POST', f'/api/challenge/{challenge_request.opponent_username}',
                                        data={'rated': str(challenge_request.rated).lower(),
                                              'clock.limit': challenge_request.initial_time,
                                              'clock.increment': challenge_request.increment,
                                              'color': challenge_request.color.value,
                                              'variant': challenge_request.variant.value,
                                              'keepAliveStream': 'true'},
                                        timeout=60.0) as response:

            if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
                response_queue.put(API_Challenge_Reponse(has_reached_rate_limit=True))
                return

            for line in filter(None, response.iter_lines()):
                data: dict[str, Any] = json.loads(line)
                response_queue.put(API_Challenge_Reponse(data.get('id', None),
                                                         data.get('done') == 'accepted',
                                                         data.get('error'),
                                                         data.get('done') == 'declined',
                                                         'clock.limit' in data,
                                                         'clock.increment' in data))

    @retry(retry=retry_if_exception_type(httpx.RequestError), after=after_log(logger, logging.DEBUG))
    def decline_challenge(self, challenge_id: str, reason: Decline_Reason) -> bool:
        try:
            response = self.lichess_client.post(f'/api/challenge/{challenge_id}/decline',
                                                data={'reason': reason.value})
            response.raise_for_status()
            return True
        except httpx.HTTPStatusError as e:
            print(e)
            return False

    @retry(retry=retry_if_exception_type(httpx.RequestError), after=after_log(logger, logging.DEBUG))
    def get_account(self) -> dict[str, Any]:
        response = self.lichess_client.get('/api/account')
        json_response = response.json()
        if 'error' in json_response:
            raise RuntimeError(f'Account error: {json_response["error"]}')

        return json_response

    def get_chessdb_eval(self, fen: str, best_move: bool, timeout: int) -> dict[str, Any] | None:
        try:
            response = self.external_client.get('http://www.chessdb.cn/cdb.php',
                                                params={'action': 'querypv',
                                                        'board': fen,
                                                        'stable': int(best_move),
                                                        'json': 1},
                                                timeout=timeout)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            print(e)

    def get_cloud_eval(self, fen: str, variant: Variant, timeout: int) -> dict[str, Any] | None:
        try:
            response = self.lichess_client.get('/api/cloud-eval', params={'fen': fen, 'variant': variant.value},
                                               timeout=timeout)
            return response.json()
        except httpx.HTTPError as e:
            print(e)

    def get_egtb(self, fen: str, variant: str, timeout: int) -> dict[str, Any] | None:
        try:
            response = self.external_client.get(f'https://tablebase.lichess.ovh/{variant}', params={'fen': fen},
                                                timeout=timeout)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            print(e)

    @retry(after=after_log(logger, logging.DEBUG))
    def get_event_stream(self, queue: Queue) -> None:
        with self.lichess_client.stream('GET', '/api/stream/event', timeout=9.0) as response:
            for line in filter(None, response.iter_lines()):
                queue.put(json.loads(line))

    @retry(after=after_log(logger, logging.DEBUG))
    def get_game_stream(self, game_id: str, queue: Queue) -> None:
        with self.lichess_client.stream('GET', f'/api/bot/game/stream/{game_id}', timeout=9.0) as response:
            for line in response.iter_lines():
                event = json.loads(line) if line else {'type': 'ping'}
                queue.put(event)

    @retry(after=after_log(logger, logging.DEBUG))
    def get_online_bots_stream(self) -> list[dict[str, Any]]:
        with self.lichess_client.stream('GET', '/api/bot/online', timeout=9.0) as response:
            return [json.loads(line) for line in filter(None, response.iter_lines())]

    def get_opening_explorer(self,
                             username: str,
                             fen: str,
                             variant: Variant,
                             color: str,
                             speeds: str,
                             timeout: int
                             ) -> dict[str, Any] | None:
        try:
            with self.external_client.stream('GET', 'https://explorer.lichess.ovh/player',
                                             params={'player': username, 'variant': variant.value, 'fen': fen,
                                                     'color': color, 'speeds': speeds, 'modes': 'rated',
                                                     'recentGames': 0},
                                             timeout=timeout) as response:
                response.raise_for_status()
                return json.loads(next(filter(None, response.iter_lines())))
        except httpx.HTTPError as e:
            print(e)

    @retry(retry=retry_if_exception_type(httpx.RequestError), after=after_log(logger, logging.DEBUG))
    def get_token_scopes(self, token: str) -> str:
        response = self.lichess_client.post('/api/token/test', content=token)
        return response.json()[token]['scopes']

    @retry(retry=retry_if_exception_type(httpx.RequestError), after=after_log(logger, logging.DEBUG))
    def get_user_status(self, username: str) -> dict[str, Any]:
        response = self.lichess_client.get('/api/users/status', params={'ids': username})
        return response.json()[0]

    @retry(retry=retry_if_exception_type(httpx.RequestError), after=after_log(logger, logging.DEBUG))
    def resign_game(self, game_id: str) -> bool:
        try:
            response = self.lichess_client.post(f'/api/bot/game/{game_id}/resign')
            response.raise_for_status()
            return True
        except httpx.HTTPStatusError as e:
            print(e)
            return False

    def send_chat_message(self, game_id: str, room: str, text: str) -> bool:
        try:
            response = self.lichess_client.post(f'/api/bot/game/{game_id}/chat',
                                                data={'room': room, 'text': text}, timeout=1.0)
            response.raise_for_status()
            return True
        except httpx.HTTPError as e:
            print(e)
            return False

    @retry(retry=retry_if_exception_type(httpx.RequestError), after=after_log(logger, logging.DEBUG))
    def send_move(self, game_id: str, uci_move: str, offer_draw: bool) -> bool:
        try:
            response = self.lichess_client.post(f'/api/bot/game/{game_id}/move/{uci_move}',
                                                params={'offeringDraw': str(offer_draw).lower()}, timeout=1.0)

            response.raise_for_status()
            return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code != httpx.codes.BAD_REQUEST:
                print(e)
            return False

    @retry(retry=retry_if_exception_type(httpx.RequestError), after=after_log(logger, logging.DEBUG))
    def upgrade_account(self) -> bool:
        try:
            response = self.lichess_client.post('/api/bot/account/upgrade')
            response.raise_for_status()
            return True
        except httpx.HTTPStatusError as e:
            print(e)
            return False
