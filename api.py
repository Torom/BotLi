import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
from tenacity import after_log, retry, retry_if_exception_type, wait_fixed

from botli_dataclasses import API_Challenge_Reponse, Challenge_Request
from config import Config
from enums import Decline_Reason, Variant

logger = logging.getLogger(__name__)
BASIC_RETRY_CONDITIONS = {'retry': retry_if_exception_type(httpx.RequestError),
                          'wait': wait_fixed(5),
                          'after': after_log(logger, logging.DEBUG)}
JSON_RETRY_CONDITIONS = {'retry': retry_if_exception_type((httpx.RequestError, json.JSONDecodeError)),
                         'wait': wait_fixed(5),
                         'after': after_log(logger, logging.DEBUG)}
MOVE_RETRY_CONDITIONS = {'retry': retry_if_exception_type(httpx.HTTPError),
                         'wait': wait_fixed(1),
                         'after': after_log(logger, logging.DEBUG)}


class API:
    def __init__(self, config: Config) -> None:
        self.lichess_client = httpx.AsyncClient(base_url=config.url,
                                                headers={'Authorization': f'Bearer {config.token}',
                                                         'User-Agent': f'BotLi/{config.version}'})
        self.external_client = httpx.AsyncClient(headers={'User-Agent': f'BotLi/{config.version}'})

    def set_user_agent(self, version: str, username: str) -> None:
        self.lichess_client.headers.update({'User-Agent': f'BotLi/{version} user:{username}'})
        self.external_client.headers.update({'User-Agent': f'BotLi/{version} user:{username}'})

    @retry(**BASIC_RETRY_CONDITIONS)
    async def abort_game(self, game_id: str) -> bool:
        try:
            response = await self.lichess_client.post(f'/api/bot/game/{game_id}/abort')
            response.raise_for_status()
            return True
        except httpx.HTTPStatusError as e:
            print(e)
            return False

    @retry(**BASIC_RETRY_CONDITIONS)
    async def accept_challenge(self, challenge_id: str) -> bool:
        try:
            response = await self.lichess_client.post(f'/api/challenge/{challenge_id}/accept')
            response.raise_for_status()
            return True
        except httpx.HTTPStatusError as e:
            if not e.response.is_client_error:
                print(e)
            return False

    @retry(**BASIC_RETRY_CONDITIONS)
    async def cancel_challenge(self, challenge_id: str) -> bool:
        try:
            response = await self.lichess_client.post(f'/api/challenge/{challenge_id}/cancel')
            response.raise_for_status()
            return True
        except httpx.HTTPStatusError as e:
            print(e)
            return False

    async def create_challenge(self,
                               challenge_request: Challenge_Request
                               ) -> AsyncIterator[API_Challenge_Reponse]:
        try:
            async with self.lichess_client.stream('POST', f'/api/challenge/{challenge_request.opponent_username}',
                                                  data={'rated': str(challenge_request.rated).lower(),
                                                        'clock.limit': challenge_request.initial_time,
                                                        'clock.increment': challenge_request.increment,
                                                        'color': challenge_request.color.value,
                                                        'variant': challenge_request.variant.value,
                                                        'keepAliveStream': 'true'},
                                                  timeout=60.0) as response:

                if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
                    yield API_Challenge_Reponse(has_reached_rate_limit=True)
                    return

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    data: dict[str, Any] = json.loads(line)
                    yield API_Challenge_Reponse(data.get('id', None),
                                                data.get('done') == 'accepted',
                                                data.get('error'),
                                                data.get('done') == 'declined',
                                                'clock.limit' in data,
                                                'clock.increment' in data)
        except (httpx.RequestError, json.JSONDecodeError) as e:
            yield API_Challenge_Reponse(error=str(e))

    @retry(**BASIC_RETRY_CONDITIONS)
    async def decline_challenge(self, challenge_id: str, reason: Decline_Reason) -> bool:
        try:
            response = await self.lichess_client.post(f'/api/challenge/{challenge_id}/decline',
                                                      data={'reason': reason.value})
            response.raise_for_status()
            return True
        except httpx.HTTPStatusError as e:
            print(e)
            return False

    @retry(**JSON_RETRY_CONDITIONS)
    async def get_account(self) -> dict[str, Any]:
        response = await self.lichess_client.get('/api/account')
        json_response = response.json()
        if 'error' in json_response:
            raise RuntimeError(f'Account error: {json_response["error"]}')

        return json_response

    async def get_chessdb_eval(self, fen: str, best_move: bool, timeout: int) -> dict[str, Any] | None:
        try:
            async with asyncio.timeout(timeout):
                response = await self.external_client.get('http://www.chessdb.cn/cdb.php',
                                                          params={'action': 'querypv',
                                                                  'board': fen,
                                                                  'stable': int(best_move),
                                                                  'json': 1},
                                                          timeout=None)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            print(f'ChessDB: {e}')
        except TimeoutError:
            print(f'ChessDB: Timed out after {timeout} second(s).')

    async def get_cloud_eval(self, fen: str, variant: Variant, timeout: int) -> dict[str, Any] | None:
        try:
            async with asyncio.timeout(timeout):
                response = await self.lichess_client.get('/api/cloud-eval', params={'fen': fen,
                                                                                    'variant': variant.value},
                                                         timeout=None)
            return response.json()
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            print(f'Cloud: {e}')
        except TimeoutError:
            print(f'Cloud: Timed out after {timeout} second(s).')

    async def get_egtb(self, fen: str, variant: str, timeout: int) -> dict[str, Any] | None:
        try:
            async with asyncio.timeout(timeout):
                response = await self.external_client.get(f'https://tablebase.lichess.ovh/{variant}',
                                                          params={'fen': fen},
                                                          timeout=None)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            print(f'EGTB: {e}')
        except TimeoutError:
            print(f'EGTB: Timed out after {timeout} second(s).')

    async def get_event_stream(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            try:
                async with self.lichess_client.stream('GET', '/api/stream/event', timeout=9.0) as response:
                    async for line in response.aiter_lines():
                        if line:
                            yield json.loads(line)
            except (httpx.RequestError, json.JSONDecodeError):
                print('Event stream lost connection. Next connection attempt in 5 seconds.')
                await asyncio.sleep(5.0)

    async def get_game_stream(self, game_id: str) -> AsyncIterator[dict[str, Any]]:
        while True:
            try:
                async with self.lichess_client.stream('GET',
                                                      f'/api/bot/game/stream/{game_id}',
                                                      timeout=9.0) as response:
                    async for line in response.aiter_lines():
                        yield json.loads(line) if line else {'type': 'ping'}
            except (httpx.RequestError, json.JSONDecodeError):
                print(f'Game stream {game_id} lost connection. Next connection attempt in 1 second.')
                await asyncio.sleep(1.0)

    async def get_online_bots_stream(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            try:
                async with self.lichess_client.stream('GET', '/api/bot/online', timeout=9.0) as response:
                    async for line in response.aiter_lines():
                        if line:
                            yield json.loads(line)
                    return
            except (httpx.RequestError, json.JSONDecodeError):
                await asyncio.sleep(5.0)

    async def get_opening_explorer(self,
                                   username: str,
                                   fen: str,
                                   variant: Variant,
                                   color: str,
                                   speeds: str,
                                   timeout: int
                                   ) -> dict[str, Any] | None:
        try:
            async with asyncio.timeout(timeout):
                async with self.external_client.stream('GET', 'https://explorer.lichess.ovh/player',
                                                       params={'player': username, 'variant': variant.value,
                                                               'fen': fen, 'color': color, 'speeds': speeds,
                                                               'modes': 'rated', 'recentGames': 0},
                                                       timeout=None) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line:
                            return json.loads(line)
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            print(f'Explore: {e}')
        except TimeoutError:
            print(f'Explore: Timed out after {timeout} second(s).')

    @retry(**JSON_RETRY_CONDITIONS)
    async def get_token_scopes(self, token: str) -> str:
        response = await self.lichess_client.post('/api/token/test', content=token)
        return response.json()[token]['scopes']

    @retry(**JSON_RETRY_CONDITIONS)
    async def get_user_status(self, username: str) -> dict[str, Any]:
        response = await self.lichess_client.get('/api/users/status', params={'ids': username})
        return response.json()[0]

    @retry(**BASIC_RETRY_CONDITIONS)
    async def resign_game(self, game_id: str) -> bool:
        try:
            response = await self.lichess_client.post(f'/api/bot/game/{game_id}/resign')
            response.raise_for_status()
            return True
        except httpx.HTTPStatusError as e:
            print(e)
            return False

    async def send_chat_message(self, game_id: str, room: str, text: str) -> bool:
        try:
            response = await self.lichess_client.post(f'/api/bot/game/{game_id}/chat',
                                                      data={'room': room, 'text': text},
                                                      timeout=1.0)
            response.raise_for_status()
            return True
        except httpx.HTTPError as e:
            print(e)
            return False

    @retry(**MOVE_RETRY_CONDITIONS)
    async def send_move(self, game_id: str, uci_move: str, offer_draw: bool) -> bool:
        try:
            response = await self.lichess_client.post(f'/api/bot/game/{game_id}/move/{uci_move}',
                                                      params={'offeringDraw': str(offer_draw).lower()},
                                                      timeout=1.0)
            response.raise_for_status()
            return True
        except httpx.HTTPStatusError as e:
            if e.response.is_server_error:
                raise
            if e.response.status_code != httpx.codes.BAD_REQUEST:
                print(e)
            return False

    @retry(**BASIC_RETRY_CONDITIONS)
    async def upgrade_account(self) -> bool:
        try:
            response = await self.lichess_client.post('/api/bot/account/upgrade')
            response.raise_for_status()
            return True
        except httpx.HTTPStatusError as e:
            print(e)
            return False
