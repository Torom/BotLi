import json
from typing import Iterable

import requests
from tenacity import retry
from tenacity.retry import retry_if_exception_type
from tenacity.wait import wait_exponential

from enums import Challenge_Color, Decline_Reason, Perf_Type, Variant
from exceptions import Too_Many_Requests_Exception


class API:
    def __init__(self, token: str) -> None:
        self.session = requests.session()
        self.session.headers.update({'Authorization': f'Bearer {token}'})
        self.user = self.get_account()
        self.session.headers.update({'User-Agent': f'BotLi user:{self.user["username"]}'})

    def abort_game(self, game_id: str) -> bool:
        try:
            response = self.session.post(f'https://lichess.org/api/bot/game/{game_id}/abort')
            response.raise_for_status()
            return True
        except requests.HTTPError as e:
            print(e)
            return False

    def accept_challenge(self, challenge_id: str) -> bool:
        try:
            response = self.session.post(f'https://lichess.org/api/challenge/{challenge_id}/accept')
            response.raise_for_status()
            return True
        except requests.HTTPError as e:
            print(e)
            return False

    def cancel_challenge(self, challenge_id: str) -> bool:
        try:
            response = self.session.post(f'https://lichess.org/api/challenge/{challenge_id}/cancel')
            response.raise_for_status()
            return True
        except requests.HTTPError as e:
            print(e)
            return False

    @retry(retry=retry_if_exception_type(Too_Many_Requests_Exception), wait=wait_exponential(min=60, max=600))
    def create_challenge(
        self, username: str, inital_time: int, increment: int, rated: bool, color: Challenge_Color,
            variant: Variant, timeout: int) -> list[dict]:

        challenge_lines = []
        try:
            response = self.session.post(
                f'https://lichess.org/api/challenge/{username}',
                data={'rated': str(rated).lower(),
                      'clock.limit': inital_time, 'clock.increment': increment, 'color': color.value,
                      'variant': variant.value, 'keepAliveStream': 'true'},
                timeout=timeout, stream=True)

            if response.status_code == 429:
                raise Too_Many_Requests_Exception

            for line in response.iter_lines():
                if line:
                    line_json = json.loads(line.decode('utf-8'))
                    challenge_lines.append(line_json)

        except requests.ConnectionError:
            challenge_lines.append({'done': 'timeout'})

        return challenge_lines

    def decline_challenge(self, challenge_id: str, reason: Decline_Reason) -> bool:
        try:
            response = self.session.post(
                f'https://lichess.org/api/challenge/{challenge_id}/decline', data={'reason': reason.value})
            response.raise_for_status()
            return True
        except requests.HTTPError as e:
            print(e)
            return False

    def get_account(self) -> dict:
        response = self.session.get('https://lichess.org/api/account')
        return response.json()

    def get_chessdb_eval(self, fen: str, timeout: int) -> dict | None:
        try:
            response = self.session.get('http://www.chessdb.cn/cdb.php',
                                        params={'action': 'querypv', 'board': fen, 'json': 1},
                                        headers={'Authorization': None},
                                        timeout=timeout)
            response.raise_for_status()
            return response.json()
        except (requests.Timeout, requests.HTTPError, requests.ConnectionError) as e:
            print(e)

    def get_cloud_eval(self, fen: str, variant: Variant, timeout: int) -> dict | None:
        try:
            response = self.session.get('https://lichess.org/api/cloud-eval',
                                        params={'fen': fen, 'variant': variant.value}, timeout=timeout)
            return response.json()
        except requests.Timeout as e:
            print(e)

    def get_egtb(self, fen: str, timeout: int) -> dict | None:
        try:
            response = self.session.get(
                'https://tablebase.lichess.ovh/standard', params={'fen': fen},
                headers={'Authorization': None},
                timeout=timeout)
            response.raise_for_status()
            return response.json()
        except (requests.Timeout, requests.HTTPError) as e:
            print(e)

    def get_event_stream(self) -> Iterable:
        response = self.session.get('https://lichess.org/api/stream/event', stream=True)
        return response.iter_lines()

    def get_game_stream(self, game_id: str) -> Iterable:
        response = self.session.get(f'https://lichess.org/api/bot/game/stream/{game_id}', stream=True)
        return response.iter_lines()

    def get_online_bots_stream(self) -> Iterable:
        response = self.session.get('https://lichess.org/api/bot/online', stream=True)
        return response.iter_lines()

    def get_perfomance(self, username: str, perf_type: Perf_Type) -> dict:
        response = self.session.get(f'https://lichess.org/api/user/{username}/perf/{perf_type.value}')
        return response.json()

    def resign_game(self, game_id: str) -> bool:
        try:
            response = self.session.post(f'https://lichess.org/api/bot/game/{game_id}/resign')
            response.raise_for_status()
            return True
        except requests.HTTPError as e:
            print(e)
            return False

    def send_chat_message(self, game_id: str, room: str, text: str) -> bool:
        try:
            response = self.session.post(
                f'https://lichess.org/api/bot/game/{game_id}/chat', data={'room': room, 'text': text})
            response.raise_for_status()
            return True
        except requests.HTTPError as e:
            print(e)
            return False

    @retry(retry=retry_if_exception_type(requests.ConnectionError))
    def send_move(self, game_id: str, uci_move: str, offer_draw: bool) -> bool:
        try:
            response = self.session.post(
                f'https://lichess.org/api/bot/game/{game_id}/move/{uci_move}',
                params={'offeringDraw': str(offer_draw).lower()})
            response.raise_for_status()
            return True
        except requests.HTTPError as e:
            print(e)
            return False

    def upgrade_account(self) -> bool:
        try:
            response = self.session.post('https://lichess.org/api/bot/account/upgrade')
            response.raise_for_status()
            return True
        except requests.HTTPError as e:
            print(e)
            return False
