import argparse
import asyncio
import logging
import os
import sys
from asyncio import Task
from enum import Enum
from typing import TypeVar

from chess.engine import EventLoopPolicy

from api import API
from botli_dataclasses import Challenge_Request
from config import Config
from engine import Engine
from enums import Challenge_Color, Perf_Type, Variant
from event_handler import Event_Handler
from game_manager import Game_Manager
from logo import LOGO

try:
    import readline
except ImportError:
    readline = None

COMMANDS = {
    'blacklist': 'Temporarily blacklists a user. Use config for permanent blacklisting. Usage: blacklist USERNAME',
    'challenge': 'Challenges a player. Usage: challenge USERNAME [TIMECONTROL] [COLOR] [RATED] [VARIANT]',
    'clear': 'Clears the challenge queue.',
    'create': 'Challenges a player to COUNT game pairs. Usage: create COUNT USERNAME [TIMECONTROL] [RATED] [VARIANT]',
    'help': 'Prints this message.',
    'matchmaking': 'Starts matchmaking mode.',
    'quit': 'Exits the bot.',
    'rechallenge': 'Challenges the opponent to the last received challenge.',
    'reset': 'Resets matchmaking. Usage: reset PERF_TYPE',
    'stop': 'Stops matchmaking mode.',
    'whitelist': 'Temporarily whitelists a user. Use config for permanent whitelisting. Usage: whitelist USERNAME'
}

EnumT = TypeVar('EnumT', bound=Enum)


class UserInterface:
    def __init__(self, config_path: str, start_matchmaking: bool, allow_upgrade: bool) -> None:
        self.start_matchmaking = start_matchmaking
        self.allow_upgrade = allow_upgrade
        self.config = Config.from_yaml(config_path)
        self.api = API(self.config)
        self.is_running = True

    async def main(self) -> None:
        print(f'{LOGO} {self.config.version}\n')

        account = await self.api.get_account()
        username: str = account['username']
        self.api.set_user_agent(self.config.version, username)
        await self._handle_bot_status(account.get('title'))
        await self._test_engines()

        game_manager = Game_Manager(self.api, self.config, username)
        event_handler = Event_Handler(self.api, self.config, username, game_manager)
        game_manager_task = asyncio.create_task(game_manager.run())
        event_handler_task = asyncio.create_task(event_handler.run())
        game_manager.is_running = True
        event_handler.last_challenge_event = None
        print('Handling challenges ...')

        if self.start_matchmaking:
            self._matchmaking(game_manager)

        if not sys.stdin.isatty():
            await game_manager_task
            await event_handler_task
            return

        if readline and not os.name == 'nt':
            completer = Autocompleter(list(COMMANDS.keys()))
            readline.set_completer(completer.complete)
            readline.parse_and_bind('tab: complete')

        while self.is_running:
            command = (await asyncio.to_thread(input)).split()
            if len(command) == 0:
                continue

            if command[0] == 'blacklist':
                self._blacklist(command)
            elif command[0] == 'challenge':
                self._challenge(command, game_manager)
            elif command[0] == 'create':
                self._create(command, game_manager)
            elif command[0] == 'clear':
                self._clear(game_manager)
            elif command[0] in ['exit', 'quit']:
                await self._quit(game_manager, game_manager_task, event_handler_task)
            elif command[0] == 'matchmaking':
                self._matchmaking(game_manager)
            elif command[0] == 'rechallenge':
                self._rechallenge(game_manager, event_handler)
            elif command[0] == 'reset':
                self._reset(command, game_manager)
            elif command[0] == 'stop':
                self._stop(game_manager)
            elif command[0] == 'whitelist':
                self._whitelist(command)
            else:
                self._help()

    async def _handle_bot_status(self, title: str | None) -> None:
        if 'bot:play' not in await self.api.get_token_scopes(self.config.token):
            print('Your token is missing the bot:play scope. This is mandatory to use BotLi.\n'
                  'You can create such a token by following this link:\n'
                  'https://lichess.org/account/oauth/token/create?scopes%5B%5D=bot:play&description=BotLi')
            sys.exit(1)

        if title == 'BOT':
            return

        print('\nBotLi can only be used by BOT accounts!\n')

        if not sys.stdin.isatty() and not self.allow_upgrade:
            print('Start BotLi with the "--upgrade" flag if you are sure you want to upgrade this account.\n'
                  'WARNING: This is irreversible. The account will only be able to play as a BOT.')
            sys.exit(1)
        elif sys.stdin.isatty():
            print('This will upgrade your account to a BOT account.\n'
                  'WARNING: This is irreversible. The account will only be able to play as a BOT.')
            approval = input('Do you want to continue? [y/N]: ')

            if approval.lower() not in ['y', 'yes']:
                print('Upgrade aborted.')
                sys.exit()

        if await self.api.upgrade_account():
            print('Upgrade successful.')
        else:
            print('Upgrade failed.')
            sys.exit(1)

    async def _test_engines(self) -> None:
        for engine_name, engine_config in self.config.engines.items():
            print(f'Testing engine "{engine_name}" ... ', end='')
            await Engine.test(engine_config, self.config.syzygy)
            print('OK')

    def _blacklist(self, command: list[str]) -> None:
        if len(command) != 2:
            print(COMMANDS['blacklist'])
            return

        self.config.blacklist.append(command[1].lower())
        print(f'Added {command[1]} to the blacklist.')

    def _challenge(self, command: list[str], game_manager: Game_Manager) -> None:
        command_length = len(command)
        if command_length < 2 or command_length > 6:
            print(COMMANDS['challenge'])
            return

        try:
            opponent_username = command[1]
            time_control = command[2] if command_length > 2 else '1+1'
            initial_time_str, increment_str = time_control.split('+')
            initial_time = int(float(initial_time_str) * 60)
            increment = int(increment_str)
            color = Challenge_Color(command[3].lower()) if command_length > 3 else Challenge_Color.RANDOM
            rated = command[4].lower() in ['true', 'yes', 'rated'] if command_length > 4 else True
            variant = self._find_enum(command[5], Variant) if command_length > 5 else Variant.STANDARD
        except ValueError as e:
            print(e)
            return

        challenge_request = Challenge_Request(opponent_username, initial_time, increment, rated, color, variant, 30)
        game_manager.request_challenge(challenge_request)
        print(f'Challenge against {challenge_request.opponent_username} added to the queue.')

    def _create(self, command: list[str], game_manager: Game_Manager) -> None:
        command_length = len(command)
        if command_length < 3 or command_length > 6:
            print(COMMANDS['create'])
            return

        try:
            count = int(command[1])
            opponent_username = command[2]
            time_control = command[3] if command_length > 3 else '1+1'
            initial_time_str, increment_str = time_control.split('+')
            initial_time = int(float(initial_time_str) * 60)
            increment = int(increment_str)
            rated = command[4].lower() in ['true', 'yes', 'rated'] if command_length > 4 else True
            variant = self._find_enum(command[5], Variant) if command_length > 5 else Variant.STANDARD
        except ValueError as e:
            print(e)
            return

        challenges: list[Challenge_Request] = []
        for _ in range(count):
            challenges.append(Challenge_Request(opponent_username, initial_time,
                              increment, rated, Challenge_Color.WHITE, variant, 30))
            challenges.append(Challenge_Request(opponent_username, initial_time,
                              increment, rated, Challenge_Color.BLACK, variant, 30))

        game_manager.request_challenge(*challenges)
        print(f'Challenges for {count} game pairs against {opponent_username} added to the queue.')

    def _clear(self, game_manager: Game_Manager) -> None:
        game_manager.challenge_requests.clear()
        print('Challenge queue cleared.')

    def _matchmaking(self, game_manager: Game_Manager) -> None:
        print('Starting matchmaking ...')
        game_manager.start_matchmaking()

    async def _quit(self, game_manager: Game_Manager, game_manager_task: Task, event_handler_task: Task) -> None:
        self.is_running = False
        game_manager.stop()
        print('Terminating program ...')
        event_handler_task.cancel()
        await game_manager_task

    def _rechallenge(self, game_manager: Game_Manager, event_handler: Event_Handler) -> None:
        last_challenge_event = event_handler.last_challenge_event
        if last_challenge_event is None:
            print('No last challenge available.')
            return

        if last_challenge_event['speed'] == 'correspondence':
            print('Correspondence is not supported by BotLi.')
            return

        opponent_username: str = last_challenge_event['challenger']['name']
        initial_time: int = last_challenge_event['timeControl']['limit']
        increment: int = last_challenge_event['timeControl']['increment']
        rated: bool = last_challenge_event['rated']
        event_color: str = last_challenge_event['color']
        variant = Variant(last_challenge_event['variant']['key'])

        if event_color == 'white':
            color = Challenge_Color.BLACK
        elif event_color == 'black':
            color = Challenge_Color.WHITE
        else:
            color = Challenge_Color.RANDOM

        challenge_request = Challenge_Request(opponent_username, initial_time, increment, rated, color, variant, 30)
        game_manager.request_challenge(challenge_request)
        print(f'Challenge against {challenge_request.opponent_username} added to the queue.')

    def _reset(self, command: list[str], game_manager: Game_Manager) -> None:
        if len(command) != 2:
            print(COMMANDS['reset'])
            return

        try:
            perf_type = self._find_enum(command[1], Perf_Type)
        except ValueError as e:
            print(e)
            return

        game_manager.matchmaking.opponents.reset_release_time(perf_type)
        print('Matchmaking has been reset.')

    def _stop(self, game_manager: Game_Manager) -> None:
        if game_manager.stop_matchmaking():
            print('Stopping matchmaking ...')
        else:
            print('Matchmaking isn\'t currently running ...')

    def _whitelist(self, command: list[str]) -> None:
        if len(command) != 2:
            print(COMMANDS['whitelist'])
            return

        self.config.whitelist.append(command[1].lower())
        print(f'Added {command[1]} to the whitelist.')

    def _help(self) -> None:
        print('These commands are supported by BotLi:\n')
        for key, value in COMMANDS.items():
            print(f'{key:11}\t\t# {value}')

    def _find_enum(self, name: str, enum_type: type[EnumT]) -> EnumT:
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
    parser.add_argument('--matchmaking', '-m', action='store_true', help='Start matchmaking mode.')
    parser.add_argument('--upgrade', '-u', action='store_true', help='Upgrade account to BOT account.')
    parser.add_argument('--debug', '-d', action='store_const', const=logging.DEBUG,
                        default=logging.WARNING, help='Enable debug logging.')
    args = parser.parse_args()

    logging.basicConfig(level=args.debug)

    ui = UserInterface(args.config, args.matchmaking, args.upgrade)
    asyncio.set_event_loop_policy(EventLoopPolicy())
    asyncio.run(ui.main(), debug=True)
