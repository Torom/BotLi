from typing import Any

from config import Config
from enums import DeclineReason
from game_manager import GameManager
from utils import get_estimated_game_duration, parse_time_control


class ChallengeValidator:
    def __init__(self, config: Config, game_manager: GameManager) -> None:
        self.config = config
        self.game_manager = game_manager
        self.bot_time_controls = self._get_time_controls(self.config.challenge.bot.time_controls)
        self.human_time_controls = self._get_time_controls(self.config.challenge.human.time_controls)

    def get_decline_reason(self, challenge_event: dict[str, Any]) -> DeclineReason | None:
        speed: str = challenge_event["speed"]
        if speed == "ultraBullet":
            print('Time control "UltraBullet" is not allowed for bots.')
            return DeclineReason.TIME_CONTROL

        if speed == "correspondence":
            print('Time control "Correspondence" is not supported by BotLi.')
            return DeclineReason.TIME_CONTROL

        is_bot = challenge_event["challenger"].get("title") == "BOT"
        opponent_config = self.config.challenge.bot if is_bot else self.config.challenge.human

        if not opponent_config.variants:
            if is_bot:
                print("Bots are not allowed according to config.")
                return DeclineReason.NO_BOT

            print("Only bots are allowed according to config.")
            return DeclineReason.ONLY_BOT

        if challenge_event["variant"]["key"] not in opponent_config.variants:
            print(f'Variant "{challenge_event["variant"]["key"]}" is not allowed according to config.')
            return DeclineReason.VARIANT

        if (
            len(self.game_manager.tournaments) + len(self.game_manager.tournaments_to_join)
        ) >= self.config.challenge.concurrency:
            print("Concurrency exhausted due to tournaments.")
            return DeclineReason.LATER

        if challenge_event["challenger"]["id"] in self.config.whitelist:
            return

        if challenge_event["challenger"]["id"] in self.config.blacklist:
            print("Challenger is blacklisted.")
            return DeclineReason.GENERIC

        if not (self.config.challenge.bot.modes or self.config.challenge.human.modes):
            print("Neither bots nor humans are allowed according to config.")
            return DeclineReason.GENERIC

        if not opponent_config.modes:
            if is_bot:
                print("Bots are not allowed according to config.")
                return DeclineReason.NO_BOT

            print("Only bots are allowed according to config.")
            return DeclineReason.ONLY_BOT

        if not opponent_config.time_controls:
            if is_bot:
                print("Bots are not allowed according to config.")
                return DeclineReason.NO_BOT

            print("Only bots are allowed according to config.")
            return DeclineReason.ONLY_BOT

        initial: int = challenge_event["timeControl"]["limit"]
        increment: int = challenge_event["timeControl"]["increment"]
        time_controls = self.bot_time_controls if is_bot else self.human_time_controls
        if speed not in opponent_config.time_controls and (initial, increment) not in time_controls:
            print(f'Time control "{speed}" is not allowed according to config.')
            return DeclineReason.TIME_CONTROL

        if opponent_config.min_increment and increment < opponent_config.min_increment:
            print(f"Increment {increment} is too short according to config.")
            return DeclineReason.TOO_FAST

        if opponent_config.max_increment and increment > opponent_config.max_increment:
            print(f"Increment {increment} is too long according to config.")
            return DeclineReason.TOO_SLOW

        if opponent_config.min_initial and initial < opponent_config.min_initial:
            print(f"Initial time {initial} is too short according to config.")
            return DeclineReason.TOO_FAST

        if opponent_config.max_initial and initial > opponent_config.max_initial:
            print(f"Initial time {initial} is too long according to config.")
            return DeclineReason.TOO_SLOW

        if (
            opponent_config.max_estimated_game_duration
            and (estimated_game_duration := get_estimated_game_duration(initial, increment))
            > opponent_config.max_estimated_game_duration
        ):
            print(f"Estimated game duration ({estimated_game_duration:.0f} seconds) is too long according to config.")
            return DeclineReason.TOO_SLOW

        if speed == "bullet" and increment == 0 and opponent_config.bullet_with_increment_only:
            print("Bullet is only allowed with increment according to config.")
            return DeclineReason.TOO_FAST

        is_rated: bool = challenge_event["rated"]
        if is_rated and "rated" not in opponent_config.modes:
            print("Rated is not allowed according to config.")
            return DeclineReason.CASUAL

        if not is_rated and "casual" not in opponent_config.modes:
            print("Casual is not allowed according to config.")
            return DeclineReason.RATED

    @staticmethod
    def _get_time_controls(speeds: list[str]) -> list[tuple[int, int]]:
        return [parse_time_control(speed) for speed in speeds if "+" in speed]
