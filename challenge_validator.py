from enums import Decline_Reason


class Challenge_Validator:
    def __init__(self, config: dict) -> None:
        self.config = config

    def get_decline_reason(self, challenge_event: dict) -> Decline_Reason | None:
        variants = self.config['challenge']['variants']
        time_controls = self.config['challenge']['time_controls']
        bullet_with_increment_only = self.config['challenge'].get('bullet_with_increment_only', False)
        min_increment = self.config['challenge'].get('min_increment', 0)
        max_increment = self.config['challenge'].get('max_increment', 180)
        min_initial = self.config['challenge'].get('min_initial', 0)
        max_initial = self.config['challenge'].get('max_initial', 315360000)
        is_bot = challenge_event['challenge']['challenger']['title'] == 'BOT'
        modes = self.config['challenge']['bot_modes'] if is_bot else self.config['challenge']['human_modes']

        if modes is None:
            if is_bot:
                print('Bots are not allowed according to config.')
                return Decline_Reason.NO_BOT
            else:
                print('Only bots are allowed according to config.')
                return Decline_Reason.ONLY_BOT

        variant = challenge_event['challenge']['variant']['key']
        if variant not in variants:
            print(f'Variant "{variant}" is not allowed according to config.')
            return Decline_Reason.VARIANT

        speed = challenge_event['challenge']['speed']
        increment = challenge_event['challenge']['timeControl'].get('increment')
        initial = challenge_event['challenge']['timeControl'].get('limit')
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
        elif is_bot and speed == 'bullet' and increment == 0 and bullet_with_increment_only:
            print('Bullet against bots is only allowed with increment according to config.')
            return Decline_Reason.TOO_FAST

        is_rated = challenge_event['challenge']['rated']
        is_casual = not is_rated
        if is_rated and 'rated' not in modes:
            print('Rated is not allowed according to config.')
            return Decline_Reason.CASUAL
        elif is_casual and 'casual' not in modes:
            print('Casual is not allowed according to config.')
            return Decline_Reason.RATED

    def format_challenge_event(self, challenge_event: dict) -> str:
        id_str = f'ID: {challenge_event["challenge"]["id"]}'
        title = challenge_event['challenge']['challenger'].get('title') or ''
        name = challenge_event['challenge']['challenger']['name']
        rating = challenge_event['challenge']['challenger']['rating']
        provisional = '?' if challenge_event['challenge']['challenger'].get('provisional') else ''
        challenger_str = f'Challenger: {title}{" " if title else ""}{name} ({rating}{provisional})'
        tc_str = f'TC: {challenge_event["challenge"]["timeControl"].get("show", "Correspondence")}'
        rated_str = f'Rated: {challenge_event["challenge"]["rated"]}'
        color_str = f'Color: {challenge_event["challenge"]["color"].capitalize()}'
        variant_str = f'Variant: {challenge_event["challenge"]["variant"]["name"]}'
        delimiter = 5 * ' '

        return delimiter.join([id_str, challenger_str, tc_str, rated_str, color_str, variant_str])
