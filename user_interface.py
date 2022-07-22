import argparse

from api import API
from challenge_request import Challenge_Request
from config import load_config
from enums import Challenge_Color, Variant
from event_handler import Event_Handler
from game_manager import Game_Manager
from logo import LOGO

COMMANDS = {
    'challenge': 'Challenges a player. Usage: challenge USERNAME [INITIAL_TIME] [INCREMENT] [COLOR] [RATED]',
    'help': 'Prints this message.',
    'matchmaking': 'Starts matchmaking mode.',
    'quit': 'Exits the bot.',
    'reset': 'Resets matchmaking.',
    'stop': 'Stops matchmaking mode.'
}


class UserInterface:
    def __init__(self) -> None:
        self.config = load_config()
        self.api = API(self.config['token'])
        self.is_running = True
        self.game_manager = Game_Manager(self.config, self.api)
        self.event_handler = Event_Handler(self.config, self.api, self.game_manager)

    def main(self) -> None:
        print(LOGO)

        parser = argparse.ArgumentParser()
        parser.add_argument('--non_interactive', '-n', action='store_true',
                            help='Set if run as a service or on Heroku.')
        parser.add_argument('--matchmaking', '-m', action='store_true', help='Start matchmaking mode.')
        parser.add_argument('--upgrade', '-u', action='store_true', help='Upgrade account to BOT account.')
        args = parser.parse_args()

        self._handle_bot_status(args.non_interactive, args.upgrade)

        if args.matchmaking:
            self._matchmaking()

        print('handling challenges ...')
        self.event_handler.start()
        self.game_manager.start()

        if args.non_interactive:
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
            elif command[0] == 'matchmaking':
                self._matchmaking()
            elif command[0] == 'quit':
                self._quit()
            elif command[0] == 'reset':
                self._reset()
            elif command[0] == 'stop':
                self._stop()
            else:
                self._help()

    def _handle_bot_status(self, non_interactive: bool, upgrade_account: bool) -> None:
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

        outcome = self.api.upgrade_account()

        if outcome:
            print('Upgrade successful.')
        else:
            print('Upgrade failed.')
            exit()

    def _challenge(self, command: list[str]) -> None:
        command_length = len(command)
        if command_length < 2 or command_length > 6:
            print(COMMANDS['challenge'])
            return

        opponent_username = command[1]
        initial_time = int(command[2]) if command_length > 2 else 60
        increment = int(command[3]) if command_length > 3 else 1
        color = Challenge_Color(command[4].lower()) if command_length > 4 else Challenge_Color.RANDOM
        rated = command[5].lower() == 'true' if command_length > 5 else True

        challenge_request = Challenge_Request(opponent_username, initial_time,
                                              increment, rated, color, Variant.STANDARD, 30)
        self.game_manager.request_challenge(challenge_request)
        print(f'Challenge against {challenge_request.opponent_username} added to the queue.')

    def _matchmaking(self) -> None:
        if self.game_manager.is_matchmaking_allowed:
            print('matchmaking already running ...')
            return

        print('Starting matchmaking ...')
        self.game_manager.is_matchmaking_allowed = True

    def _quit(self) -> None:
        self.is_running = False
        self.game_manager.stop()
        print('Terminating programm ...')
        self.game_manager.join()
        self.event_handler.stop()
        self.event_handler.join()

    def _reset(self) -> None:
        self.game_manager.matchmaking.opponents.reset_release_time(full_reset=True)
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


class Autocompleter:
    def __init__(self, options: list[str]) -> None:
        self.options = options

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
    ui = UserInterface()
    ui.main()
