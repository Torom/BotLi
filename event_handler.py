import asyncio
from typing import Any

from api import API
from botli_dataclasses import Challenge
from challenge_validator import Challenge_Validator
from config import Config
from game_manager import Game_Manager


class Event_Handler:
    def __init__(self, api: API, config: Config, username: str, game_manager: Game_Manager) -> None:
        self.api = api
        self.username = username
        self.game_manager = game_manager
        self.challenge_validator = Challenge_Validator(config, game_manager)
        self.last_challenge_event: dict[str, Any] | None = None

    async def run(self) -> None:
        event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        asyncio.create_task(self.api.get_event_stream(event_queue))
        while event := await event_queue.get():
            match event['type']:
                case 'challenge':
                    if event['challenge']['challenger']['name'] == self.username:
                        continue

                    self.last_challenge_event = event['challenge']
                    self._print_challenge_event(event['challenge'])

                    if decline_reason := self.challenge_validator.get_decline_reason(event['challenge']):
                        print(128 * '‾')
                        await self.api.decline_challenge(event['challenge']['id'], decline_reason)
                        continue

                    self.game_manager.add_challenge(Challenge(event['challenge']['id'],
                                                              event['challenge']['challenger']['name']))
                    print('Challenge added to queue.')
                    print(128 * '‾')
                case 'gameStart':
                    self.game_manager.on_game_started(event['game'])
                case 'gameFinish':
                    continue
                case 'challengeDeclined':
                    opponent_name = event['challenge']['destUser']['name']

                    if opponent_name == self.username:
                        continue

                    print(f'{opponent_name} declined challenge: {event["challenge"]["declineReason"]}')
                case 'challengeCanceled':
                    if event['challenge']['challenger']['name'] == self.username:
                        continue

                    self.game_manager.remove_challenge(Challenge(event['challenge']['id'],
                                                                 event['challenge']['challenger']['name']))
                    self._print_challenge_event(event['challenge'])
                    print('Challenge has been canceled.')
                    print(128 * '‾')
                case _:
                    print(event)

    def _print_challenge_event(self, challenge_event: dict[str, Any]) -> None:
        id_str = f'ID: {challenge_event["id"]}'
        title = challenge_event['challenger'].get('title') or ''
        name = challenge_event['challenger']['name']
        rating = challenge_event['challenger']['rating']
        provisional = '?' if challenge_event['challenger'].get('provisional') else ''
        challenger_str = f'Challenger: {title}{" " if title else ""}{name} ({rating}{provisional})'
        tc_str = f'TC: {challenge_event["timeControl"].get("show", "Correspondence")}'
        rated_str = 'Rated' if challenge_event['rated'] else 'Casual'
        color_str = f'Color: {challenge_event["color"].capitalize()}'
        variant_str = f'Variant: {challenge_event["variant"]["name"]}'
        delimiter = 5 * ' '

        print(128 * '_')
        print(delimiter.join([id_str, challenger_str, tc_str, rated_str, color_str, variant_str]))
