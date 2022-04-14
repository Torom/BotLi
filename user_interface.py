import argparse

from api import API
from challenge_handler import Challenge_Handler
from config import load_config
from enums import Challenge_Color, Perf_Type, Variant
from game_counter import Game_Counter
from logo import LOGO
from matchmaking import Matchmaking
from opponents import Opponents

COMMANDS = {'abort': 'Aborts a game. Usage: abort GAME_ID',
            'challenge': 'Challenges a player. Usage: challenge USERNAME [INITIAL_TIME] [INCREMENT] [COLOR] [RATED]',
            'help': 'Prints this message.', 'matchmaking': 'Starts matchmaking mode. Usage: matchmaking [VARIANT]',
            'quit': 'Exits the bot.', 'reset': 'Resets matchmaking. Usage: reset PERF_TYPE',
            'stop': 'Stops matchmaking mode.'}


class UserInterface:
    def __init__(self) -> None:
        self.config = load_config()
        self.api = API(self.config['token'])
        self.game_count = Game_Counter(self.config['challenge'].get('concurrency', 1))
        self.is_running = True
        self.matchmaking: Matchmaking | None = None

    def main(self) -> None:
        print(LOGO)

        parser = argparse.ArgumentParser()
        parser.add_argument('--non_interactive', '-n', action='store_true',
                            help='Set if run as a service or on Heroku.')
        parser.add_argument('--matchmaking', '-m', action='store_true', help='Start matchmaking mode.')
        parser.add_argument('--upgrade', '-u', action='store_true', help='Upgrade account to BOT account.')
        args = parser.parse_args()

        self._handle_bot_status(args.non_interactive, args.upgrade)

        self.challenge_handler = Challenge_Handler(self.config, self.api, self.game_count)

        if args.matchmaking:
            self._matchmaking(Variant(self.config['matchmaking']['variant']))

        print('handling challenges ...')
        self.challenge_handler.start()

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

            if command[0] == 'abort':
                if len(command) != 2:
                    print(COMMANDS['abort'])
                    continue

                self._abort(command[1])
            elif command[0] == 'challenge':
                command_length = len(command)
                if command_length < 2 or command_length > 6:
                    print(COMMANDS['challenge'])
                    continue

                opponent_username = command[1]
                initial_time = int(command[2]) if command_length > 2 else 60
                increment = int(command[3]) if command_length > 3 else 1
                color = Challenge_Color(command[4].lower()) if command_length > 4 else Challenge_Color.RANDOM
                rated = command[5].lower() == 'true' if command_length > 5 else True

                self._challenge(opponent_username, initial_time, increment, rated, color)
            elif command[0] == 'matchmaking':
                if len(command) > 2:
                    print(COMMANDS['matchmaking'])
                    continue

                self._matchmaking(Variant(command[1]) if len(command) == 2 else Variant.STANDARD)
            elif command[0] == 'quit':
                self._quit()
            elif command[0] == 'reset':
                if len(command) != 2:
                    print(COMMANDS['reset'])
                    return

                self._reset(Perf_Type(command[1]))
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

    def _abort(self, game_id: str) -> None:
        self.api.abort_game(game_id)

    def _challenge(self, opponent_username: str, initial_time: int, increment: int, rated: bool, color: Challenge_Color) -> None:
        challenge_lines = self.api.create_challenge(
            opponent_username, initial_time, increment, rated, color, Variant.STANDARD, 20)

        line = challenge_lines[0]
        if 'challenge' in line and 'id' in line['challenge']:
            challenge_id = line['challenge']['id']
        else:
            print(line['error'])
            return

        line = challenge_lines[1]
        if 'done' in line and line['done'] == 'timeout':
            print('challenge timed out.')
            self.api.cancel_challenge(challenge_id)
        elif 'done' in line and line['done'] == 'declined':
            print('challenge was declined.')

    def _matchmaking(self, variant: Variant) -> None:
        if self.matchmaking:
            print('matchmaking already running ...')
            return

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

    def _reset(self, perf_type: Perf_Type) -> None:
        if self.matchmaking:
            print('Can\'t reset matchmaking while running ...')
            return

        Opponents(perf_type).reset_release_time(full_reset=True, save_to_file=True)

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
