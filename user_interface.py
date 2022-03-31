from api import API
from challenge_handler import Challenge_Handler
from config import load_config
from enums import Challenge_Color, Variant
from game_counter import Game_Counter
from logo import LOGO
from matchmaking import Matchmaking

COMMANDS = {'abort': 'Aborts a game. Usage: abort GAME_ID',
            'challenge': 'Challenges a player. Usage: challenge USERNAME [INITIAL_TIME] [INCREMENT] [COLOR] [RATED]',
            'help': 'Prints this message.', 'matchmaking': 'Starts matchmaking mode. Usage: matchmaking [VARIANT]',
            'quit': 'Exits the bot.', 'reset': 'Resets matchmaking.', 'stop': 'Stops matchmaking mode.',
            'upgrade': 'Upgrades your Lichess account to a BOT account.'}


class UserInterface:
    def __init__(self) -> None:
        self.config = load_config()
        self.api = API(self.config['token'])
        self.game_count = Game_Counter(self.config['challenge'].get('concurrency', 1))
        self.is_running = True
        self.matchmaking: Matchmaking | None = None

    def start(self) -> None:
        print(LOGO)

        self.challenge_handler = Challenge_Handler(self.config, self.api, self.game_count)
        self.challenge_handler.start()

        try:
            import readline

            completer = Autocompleter(list(COMMANDS.keys()))
            readline.set_completer(completer.complete)
            readline.parse_and_bind('tab: complete')
        except ImportError:
            pass

        print('accepting challenges ...')

        while self.is_running:
            command = input()

            if command.startswith('abort'):
                self._abort(command)
            elif command.startswith('challenge'):
                self._challenge(command)
            elif command.startswith('matchmaking'):
                self._matchmaking(command)
            elif command == 'quit':
                self._quit()
            elif command == 'reset':
                self._reset()
            elif command == 'stop':
                self._stop()
            elif command == 'upgrade':
                self._upgrade()
            else:
                self._help()

    def _abort(self, command: str) -> None:
        command_parts = command.split()
        if len(command_parts) != 2:
            print(COMMANDS['abort'])
            return

        self.api.abort_game(command_parts[1])

    def _challenge(self, command: str) -> None:
        command_parts = command.split()
        command_length = len(command_parts)
        if command_length < 2 or command_length > 6:
            print(COMMANDS['challenge'])
            return

        opponent_username = command_parts[1]
        initial_time = int(command_parts[2]) if command_length > 2 else 60
        increment = int(command_parts[3]) if command_length > 3 else 1
        color = Challenge_Color(command_parts[4].lower()) if command_length > 4 else Challenge_Color.RANDOM
        rated = command_parts[5].lower() == 'true' if command_length > 5 else True

        self.api.create_challenge(opponent_username, initial_time, increment, rated, color, Variant.STANDARD, 20)

    def _matchmaking(self, command: str) -> None:
        if self.matchmaking:
            print('matchmaking already running ...')
            return

        command_parts = command.split()
        if len(command_parts) > 2:
            print(COMMANDS['matchmaking'])
            return

        variant = Variant(command_parts[1]) if len(command_parts) == 2 else Variant.STANDARD

        self.challenge_handler.stop_accepting_challenges()

        print('Waiting for a game to finish ...')
        self.game_count.wait_for_increment()

        print('Starting matchmaking ...')

        self.matchmaking = Matchmaking(self.config, self.api, variant)
        self.matchmaking.start()

    def _quit(self) -> None:
        self.is_running = False
        self.challenge_handler.stop()
        print('Terminating programm ...')
        if self.matchmaking:
            self.matchmaking.stop()
            self.matchmaking.join()
        self.challenge_handler.join()

    def _reset(self) -> None:
        if self.matchmaking:
            print('Can\'t reset matchmaking while running ...')
            return

        Matchmaking.reset_matchmaking()

    def _stop(self) -> None:
        if not self.matchmaking:
            print('Matchmaking isn\'t currently running ...')
            return

        self.matchmaking.stop()
        print('Stopping matchmaking ...')
        self.matchmaking.join()
        self.matchmaking = None
        self.game_count.decrement()
        self.challenge_handler.start_accepting_challenges()
        print('Matchmaking has been stopped. And challenges are resuming ...')

    def _upgrade(self) -> None:
        print('This will upgrade your account to a bot account.')
        print('WARNING: This is irreversible. The account will only be able to play as a Bot.')
        approval = input('Do you want to continue? [y/N]: ')

        if approval.lower() not in ['y', 'yes']:
            print('Upgrade aborted.')
            return

        outcome = 'successful' if self.api.upgrade_account() else 'failed'
        print(f'Upgrade {outcome}.')

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
    ui.start()
