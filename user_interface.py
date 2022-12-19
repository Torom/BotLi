import argparse
from enum import Enum
from typing import Type, TypeVar

from api import API
from botli_dataclasses import Challenge_Request
from config import load_config
from enums import Challenge_Color, Perf_Type, Variant
from event_handler import Event_Handler
from game_manager import Game_Manager
from logo import LOGO

COMMANDS = {
    'challenge': 'Challenges a player.\n\t\t\t'
    '  Usage: challenge USERNAME [INITIAL_TIME] [INCREMENT] [COLOR] [RATED] [VARIANT]',
    'create': 'Challenges a player to COUNT game pairs.\n\t\t\t'
    '  Usage: create COUNT USERNAME [INITIAL_TIME] [INCREMENT] [RATED] [VARIANT]',
    'help': 'Prints this message.',
    'matchmaking': 'Starts matchmaking mode.',
    'quit': 'Exits the bot.',
    'reset': 'Resets matchmaking.\n\t\t\t'
    '  Usage: reset [PERF_TYPE]',
    'stop': 'Stops matchmaking mode.'
}

EnumT = TypeVar('EnumT', bound=Enum)


class UserInterface:
    def __init__(self, config_path: str, non_interactive: bool, start_matchmaking: bool, allow_upgrade: bool) -> None:
        self.non_interactive = non_interactive
        self.start_matchmaking = start_matchmaking
        self.allow_upgrade = allow_upgrade
        self.config = load_config(config_path)
        self.api = API(self.config['token'])
        self.is_running = True
        self.game_manager = Game_Manager(self.config, self.api)
        self.event_handler = Event_Handler(self.config, self.api, self.game_manager)

    def main(self) -> None:
        print(LOGO)

        self._handle_bot_status(self.non_interactive, self.allow_upgrade)

        print('Handling challenges ...')
        self.event_handler.start()
        self.game_manager.start()

        if self.start_matchmaking:
            self._matchmaking()

        if self.non_interactive:
            return

        try:
            import readline

            completer = Autocompleter(list(COMMANDS.keys()))
            readline.set_completer(completer.complete)
            readline.parse_and_bind('tab: complete')
        except ImportError:
            pass

        while self.is_running:
            command = input().split()

            if len(command) == 0:
                continue
            elif command[0] == 'challenge':
                self._challenge(command)
            elif command[0] == 'create':
                self._create(command)
            elif command[0] == 'exit':
                self._quit()
            elif command[0] == 'matchmaking':
                self._matchmaking()
            elif command[0] == 'quit':
                self._quit()
            elif command[0] == 'reset':
                self._reset(command)
            elif command[0] == 'stop':
                self._stop()
            else:
                self._help()

    def _handle_bot_status(self, non_interactive: bool, upgrade_account: bool) -> None:
        if 'bot:play' not in self.api.get_token_scopes(self.config['token']):
            print('Your token is missing the bot:play scope. This is mandatory to use BotLi.')
            print('You can create such a token by following this link:')
            print('https://lichess.org/account/oauth/token/create?scopes%5B%5D=bot:play&description=BotLi')
            exit(1)

        if self.api.user.get('title') == 'BOT':
            return

        print('\nBotLi can only be used by BOT accounts!\n')

        if non_interactive and not upgrade_account:
            exit(1)
        elif not non_interactive:
            print('This will upgrade your account to a BOT account.')
            print('WARNING: This is irreversible. The account will only be able to play as a BOT.')
            approval = input('Do you want to continue? [y/N]: ')

            if approval.lower() not in ['y', 'yes']:
                print('Upgrade aborted.')
                exit()

        if self.api.upgrade_account():
            print('Upgrade successful.')
        else:
            print('Upgrade failed.')
            exit(1)

    def _challenge(self, command: list[str]) -> None:
        command_length = len(command)
        if command_length < 2 or command_length > 7:
            print(COMMANDS['challenge'])
            return

        try:
            opponent_username = command[1]
            initial_time = int(command[2]) if command_length > 2 else 60
            increment = int(command[3]) if command_length > 3 else 1
            color = Challenge_Color(command[4].lower()) if command_length > 4 else Challenge_Color.RANDOM
            rated = command[5].lower() == 'true' if command_length > 5 else True
            variant = self._find_enum(command[6], Variant) if command_length > 6 else Variant.STANDARD
        except ValueError as e:
            print(e)
            return

        challenge_request = Challenge_Request(opponent_username, initial_time, increment, rated, color, variant, 30)
        self.game_manager.request_challenge(challenge_request)
        print(f'Challenge against {challenge_request.opponent_username} added to the queue.')

    def _create(self, command: list[str]) -> None:
        command_length = len(command)
        if command_length < 3 or command_length > 7:
            print(COMMANDS['create'])
            return

        try:
            count = int(command[1])
            opponent_username = command[2]
            initial_time = int(command[3]) if command_length > 3 else 60
            increment = int(command[4]) if command_length > 4 else 1
            rated = command[5].lower() == 'true' if command_length > 5 else True
            variant = self._find_enum(command[6], Variant) if command_length > 6 else Variant.STANDARD
        except ValueError as e:
            print(e)
            return

        challenges: list[Challenge_Request] = []
        for _ in range(count):
            challenges.append(Challenge_Request(opponent_username, initial_time,
                              increment, rated, Challenge_Color.WHITE, variant, 30))
            challenges.append(Challenge_Request(opponent_username, initial_time,
                              increment, rated, Challenge_Color.BLACK, variant, 30))

        self.game_manager.request_challenge(*challenges)
        print(f'Challenges for {count} game pairs against {opponent_username} added to the queue.')

    def _matchmaking(self) -> None:
        if self.game_manager.is_matchmaking_allowed:
            print('matchmaking already running ...')
            return

        print('Starting matchmaking ...')
        self.game_manager.is_matchmaking_allowed = True

    def _quit(self) -> None:
        self.is_running = False
        self.game_manager.stop()
        print('Terminating program ...')
        self.game_manager.join()
        self.event_handler.stop()
        self.event_handler.join()

    def _reset(self, command: list[str]) -> None:
        if len(command) != 2:
            print(COMMANDS['reset'])
            return

        try:
            perf_type = self._find_enum(command[1], Perf_Type)
        except ValueError as e:
            print(e)
            return

        self.game_manager.matchmaking.opponents.reset_release_time(perf_type, full_reset=True)
        print('Matchmaking has been reset.')

    def _stop(self) -> None:
        if not self.game_manager.is_matchmaking_allowed:
            print('Matchmaking isn\'t currently running ...')
            return

        print('Stopping matchmaking ...')
        self.game_manager.is_matchmaking_allowed = False

    def _help(self) -> None:
        print('These commands are supported by BotLi:\n')
        for key, value in COMMANDS.items():
            print(f'{key:11}\t\t# {value}')

    def _find_enum(self, name: str, enum_type: Type[EnumT]) -> EnumT:
        for enum in enum_type:
            if enum.value.lower() == name.lower():
                return enum

        raise ValueError(f'{name} is not a valid {enum_type}')


class Autocompleter:
    def __init__(self, options: list[str]) -> None:
        self.options = options
        self.matches: list[str] = []

    def complete(self, text: str, state: int) -> str | None:
        if state == 0:
            if text:
                self.matches = [s for s in self.options if s and s.startswith(text)]
            else:
                self.matches = self.options[:]

        try:
            return self.matches[state]
        except IndexError:
            return None


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', '-c', default='config.yml', type=str, help='Path to config.yml.')
    parser.add_argument('--non_interactive', '-n', action='store_true', help='Set if run as a service.')
    parser.add_argument('--matchmaking', '-m', action='store_true', help='Start matchmaking mode.')
    parser.add_argument('--upgrade', '-u', action='store_true', help='Upgrade account to BOT account.')
    args = parser.parse_args()

    ui = UserInterface(args.config, args.non_interactive, args.matchmaking, args.upgrade)
    ui.main()
