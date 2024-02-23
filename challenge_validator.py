from enums import Decline_Reason


class Challenge_Validator:
    def __init__(self, config: dict) -> None:
        self.variants: list[str] = config['challenge']['variants']
        self.speeds: list[str] = config['challenge']['time_controls']
        self.time_controls = self._get_time_controls(self.speeds)
        self.bullet_with_increment_only: bool = config['challenge'].get('bullet_with_increment_only', False)
        self.min_increment: int = config['challenge'].get('min_increment', 0)
        self.max_increment: int = config['challenge'].get('max_increment', 180)
        self.min_initial: int = config['challenge'].get('min_initial', 0)
        self.max_initial: int = config['challenge'].get('max_initial', 315360000)
        self.bot_modes: list[str] = config['challenge']['bot_modes']
        self.human_modes: list[str] = config['challenge']['human_modes']
        self.whitelist: list[str] = config.get('whitelist', [])
        self.blacklist: list[str] = config.get('blacklist', [])

    def get_decline_reason(self, challenge_event: dict) -> Decline_Reason | None:
        speed: str = challenge_event['challenge']['speed']
        if speed == 'correspondence':
            print('Time control "Correspondence" is not supported by BotLi.')
            return Decline_Reason.TIME_CONTROL

        variant: str = challenge_event['challenge']['variant']['key']
        if variant not in self.variants:
            print(f'Variant "{variant}" is not allowed according to config.')
            return Decline_Reason.VARIANT

        if challenge_event['challenge']['challenger']['id'] in self.whitelist:
            return

        if challenge_event['challenge']['challenger']['id'] in self.blacklist:
            print('Challenger is blacklisted.')
            return Decline_Reason.GENERIC

        if not (self.bot_modes or self.human_modes):
            print('Neither bots nor humans are allowed according to config.')
            return Decline_Reason.GENERIC

        is_bot: bool = challenge_event['challenge']['challenger']['title'] == 'BOT'
        modes = self.bot_modes if is_bot else self.human_modes
        if modes is None:
            if is_bot:
                print('Bots are not allowed according to config.')
                return Decline_Reason.NO_BOT

            print('Only bots are allowed according to config.')
            return Decline_Reason.ONLY_BOT

        increment: int = challenge_event['challenge']['timeControl']['increment']
        initial: int = challenge_event['challenge']['timeControl']['limit']
        if not self.speeds:
            print('No time control is allowed according to config.')
            return Decline_Reason.GENERIC

        if speed not in self.speeds and (initial, increment) not in self.time_controls:
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

        if is_bot and speed == 'bullet' and increment == 0 and self.bullet_with_increment_only:
            print('Bullet against bots is only allowed with increment according to config.')
            return Decline_Reason.TOO_FAST

        is_rated: bool = challenge_event['challenge']['rated']
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
