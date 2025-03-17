from typing import Any

from config import Config
from enums import Decline_Reason
from game_manager import Game_Manager


class Challenge_Validator:
    def __init__(self, config: Config, game_manager: Game_Manager) -> None:
        self.config = config
        self.game_manager = game_manager
        self.time_controls = self._get_time_controls(self.config.challenge.time_controls)
        self.min_increment = 0 if config.challenge.min_increment is None else config.challenge.min_increment
        self.max_increment = 180 if config.challenge.max_increment is None else config.challenge.max_increment
        self.min_initial = 0 if config.challenge.min_initial is None else config.challenge.min_initial
        self.max_initial = 315360000 if config.challenge.max_initial is None else config.challenge.max_initial

    def get_decline_reason(self, challenge_event: dict[str, Any]) -> Decline_Reason | None:
        speed: str = challenge_event['speed']
        if speed == 'ultraBullet':
            print('Time control "UltraBullet" is not allowed for bots.')
            return Decline_Reason.TIME_CONTROL

        if speed == 'correspondence':
            print('Time control "Correspondence" is not supported by BotLi.')
            return Decline_Reason.TIME_CONTROL

        variant: str = challenge_event['variant']['key']
        if variant not in self.config.challenge.variants:
            print(f'Variant "{variant}" is not allowed according to config.')
            return Decline_Reason.VARIANT

        if (len(self.game_manager.tournaments) +
                len(self.game_manager.tournaments_to_join)) >= self.config.challenge.concurrency:
            print('Concurrency exhausted due to tournaments.')
            return Decline_Reason.LATER

        if challenge_event['challenger']['id'] in self.config.whitelist:
            return

        if challenge_event['challenger']['id'] in self.config.blacklist:
            print('Challenger is blacklisted.')
            return Decline_Reason.GENERIC

        if not (self.config.challenge.bot_modes or self.config.challenge.human_modes):
            print('Neither bots nor humans are allowed according to config.')
            return Decline_Reason.GENERIC

        is_bot: bool = challenge_event['challenger']['title'] == 'BOT'
        modes = self.config.challenge.bot_modes if is_bot else self.config.challenge.human_modes
        if modes is None:
            if is_bot:
                print('Bots are not allowed according to config.')
                return Decline_Reason.NO_BOT

            print('Only bots are allowed according to config.')
            return Decline_Reason.ONLY_BOT

        increment: int = challenge_event['timeControl']['increment']
        initial: int = challenge_event['timeControl']['limit']
        if not self.config.challenge.time_controls:
            print('No time control is allowed according to config.')
            return Decline_Reason.GENERIC

        if speed not in self.config.challenge.time_controls and (initial, increment) not in self.time_controls:
            print(f'Time control "{speed}" is not allowed according to config.')
            return Decline_Reason.TIME_CONTROL

        if increment < self.min_increment:
            print(f'Increment {increment} is too short according to config.')
            return Decline_Reason.TOO_FAST

        if increment > self.max_increment:
            print(f'Increment {increment} is too long according to config.')
            return Decline_Reason.TOO_SLOW

        if initial < self.min_initial:
            print(f'Initial time {initial} is too short according to config.')
            return Decline_Reason.TOO_FAST

        if initial > self.max_initial:
            print(f'Initial time {initial} is too long according to config.')
            return Decline_Reason.TOO_SLOW

        if is_bot and speed == 'bullet' and increment == 0 and self.config.challenge.bullet_with_increment_only:
            print('Bullet against bots is only allowed with increment according to config.')
            return Decline_Reason.TOO_FAST

        is_rated: bool = challenge_event['rated']
        is_casual = not is_rated
        if is_rated and 'rated' not in modes:
            print('Rated is not allowed according to config.')
            return Decline_Reason.CASUAL

        if is_casual and 'casual' not in modes:
            print('Casual is not allowed according to config.')
            return Decline_Reason.RATED

    def _get_time_controls(self, speeds: list[str]) -> list[tuple[int, int]]:
        time_controls: list[tuple[int, int]] = []
        for speed in speeds:
            if '+' in speed:
                initial_str, increment_str = speed.split('+')
                time_controls.append((int(initial_str) * 60, int(increment_str)))

        return time_controls
