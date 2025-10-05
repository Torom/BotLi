import argparse
import asyncio
import logging
import os
import signal
import sys
from enum import StrEnum
from typing import TypeVar

import psutil

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
    "blacklist": "Temporarily blacklists a user. Use config for permanent blacklisting. Usage: blacklist USERNAME",
    "challenge": "Challenges a player. Usage: challenge USERNAME [TIMECONTROL] [COLOR] [RATED] [VARIANT]",
    "clear": "Clears the challenge queue.",
    "create": "Challenges a player to COUNT game pairs. Usage: create COUNT USERNAME [TIMECONTROL] [RATED] [VARIANT]",
    "help": "Prints this message.",
    "join": "Joins a team. Usage: join TEAM_ID [PASSWORD]",
    "leave": "Leaves tournament. Usage: leave ID",
    "matchmaking": "Starts matchmaking mode.",
    "quit": "Exits the bot.",
    "rechallenge": "Challenges the opponent to the last received challenge.",
    "reset": "Resets matchmaking. Usage: reset PERF_TYPE",
    "stats": "Shows bot statistics and performance information.",
    "stop": "Stops matchmaking mode.",
    "tournament": "Joins tournament. Usage: tournament ID [TEAM_ID] [PASSWORD]",
    "whitelist": "Temporarily whitelists a user. Use config for permanent whitelisting. Usage: whitelist USERNAME",
}

EnumT = TypeVar("EnumT", bound=StrEnum)


class User_Interface:
    async def main(self, commands: list[str], config_path: str, allow_upgrade: bool) -> None:
        self.config = Config.from_yaml(config_path)
        print(f"{LOGO} • {self.config.version}", end="", flush=True)

        async with API(self.config) as self.api:
            account = await self.api.get_account()
            username: str = account["username"]

            print(f" • {username}\n")

            self.api.append_user_agent(username)
            await self._handle_bot_status(account.get("title"), allow_upgrade)
            await self._test_engines()
            await self._download_online_blacklists()

            self.game_manager = Game_Manager(self.api, self.config, username)
            self.game_manager_task = asyncio.create_task(self.game_manager.run())

            self.event_handler = Event_Handler(self.api, self.config, username, self.game_manager)
            self.event_handler_task = asyncio.create_task(self.event_handler.run())

            signal.signal(signal.SIGTERM, self.signal_handler)

            if commands:
                # Short timeout to receive ongoing games first
                await asyncio.sleep(0.5)

                for command in commands:
                    await self._handle_command(command.split())

            if not sys.stdin.isatty():
                await self.game_manager_task
                return

            if readline and os.name != "nt":
                completer = Autocompleter(list(COMMANDS.keys()))
                readline.set_completer(completer.complete)
                readline.parse_and_bind("tab: complete")

            while True:
                command = (await asyncio.to_thread(input)).split()
                if len(command) > 0:
                    await self._handle_command(command)

    async def _handle_bot_status(self, title: str | None, allow_upgrade: bool) -> None:
        if "bot:play" not in await self.api.get_token_scopes(self.config.token):
            print(
                "Your token is missing the bot:play scope. This is mandatory to use BotLi.\n"
                "You can create such a token by following this link:\n"
                "https://lichess.org/account/oauth/token/create?scopes[]=bot:play&description=BotLi"
            )
            sys.exit(1)

        if title == "BOT":
            return

        print("\nBotLi can only be used by BOT accounts!\n")

        if not sys.stdin.isatty() and not allow_upgrade:
            print(
                'Start BotLi with the "--upgrade" flag if you are sure you want to upgrade this account.\n'
                "WARNING: This is irreversible. The account will only be able to play as a BOT."
            )
            sys.exit(1)
        elif sys.stdin.isatty():
            print(
                "This will upgrade your account to a BOT account.\n"
                "WARNING: This is irreversible. The account will only be able to play as a BOT."
            )
            approval = input("Do you want to continue? [y/N]: ")

            if approval.lower() not in ["y", "yes"]:
                print("Upgrade aborted.")
                sys.exit()

        if await self.api.upgrade_account():
            print("Upgrade successful.")
        else:
            print("Upgrade failed.")
            sys.exit(1)

    async def _test_engines(self) -> None:
        for engine_name, engine_config in self.config.engines.items():
            print(f'Testing engine "{engine_name}" ... ', end="", flush=True)
            await Engine.test(engine_config)
            print("OK")

    async def _download_online_blacklists(self) -> None:
        for url in self.config.online_blacklists:
            online_blacklist = await self.api.download_blacklist(url) or []
            self.config.blacklist.extend(username.lower() for username in online_blacklist)
            print(f'Blacklisted {len(online_blacklist)} users from "{url}".')

    async def _handle_command(self, command: list[str]) -> None:
        match command[0]:
            case "blacklist":
                self._blacklist(command)
            case "challenge":
                self._challenge(command)
            case "clear":
                self._clear()
            case "create":
                self._create(command)
            case "join":
                await self._join(command)
            case "leave":
                self._leave(command)
            case "matchmaking" | "m":
                self._matchmaking()
            case "quit" | "exit" | "q":
                await self._quit()
                sys.exit()
            case "rechallenge":
                self._rechallenge()
            case "reset":
                self._reset(command)
            case "stats":
                await self._stats()
            case "stop" | "s":
                self._stop()
            case "tournament" | "t":
                self._tournament(command)
            case "whitelist":
                self._whitelist(command)
            case _:
                self._help()

    def _blacklist(self, command: list[str]) -> None:
        if len(command) != 2:
            print(COMMANDS["blacklist"])
            return

        self.config.blacklist.append(command[1].lower())
        print(f"Added {command[1]} to the blacklist.")

    def _challenge(self, command: list[str]) -> None:
        if len(command) < 2:
            print(COMMANDS["challenge"])
            return

        try:
            challenge_request = Challenge_Request.parse_from_command(command[1:], 60)
        except ValueError as e:
            print(e)
            return

        self.game_manager.request_challenge(challenge_request)
        print(f"Challenge against {challenge_request.opponent_username} added to the queue.")

    def _clear(self) -> None:
        self.game_manager.challenge_requests.clear()
        print("Challenge queue cleared.")

    def _create(self, command: list[str]) -> None:
        if len(command) < 3:
            print(COMMANDS["create"])
            return

        try:
            count = int(command[1])
        except ValueError:
            print("First argument must be the number of game pairs to create.")
            return

        try:
            challenge_request = Challenge_Request.parse_from_command(command[2:], 60)
        except ValueError as e:
            print(e)
            return

        challenges: list[Challenge_Request] = []
        for _ in range(count):
            challenges.append(challenge_request.replaced(color=Challenge_Color.WHITE))
            challenges.append(challenge_request.replaced(color=Challenge_Color.BLACK))

        self.game_manager.request_challenge(*challenges)
        print(f"Challenges for {count} game pairs against {challenge_request.opponent_username} added to the queue.")

    async def _join(self, command: list[str]) -> None:
        if len(command) < 2 or len(command) > 3:
            print(COMMANDS["join"])
            return

        password = command[2] if len(command) > 2 else None
        if await self.api.join_team(command[1], password):
            print(f'Joined team "{command[1]}" successfully.')

    def _leave(self, command: list[str]) -> None:
        if len(command) != 2:
            print(COMMANDS["leave"])
            return

        self.game_manager.request_tournament_leaving(command[1])

    def _matchmaking(self) -> None:
        print("Starting matchmaking ...")
        self.game_manager.start_matchmaking()

    async def _quit(self) -> None:
        self.game_manager.stop()
        print("Terminating program ...")
        self.event_handler_task.cancel()
        await self.game_manager_task

    def _rechallenge(self) -> None:
        last_challenge_event = self.event_handler.last_challenge_event
        if last_challenge_event is None:
            print("No last challenge available.")
            return

        if last_challenge_event["speed"] == "correspondence":
            print("Correspondence is not supported by BotLi.")
            return

        opponent_username: str = last_challenge_event["challenger"]["name"]
        initial_time: int = last_challenge_event["timeControl"]["limit"]
        increment: int = last_challenge_event["timeControl"]["increment"]
        rated: bool = last_challenge_event["rated"]
        event_color: str = last_challenge_event["color"]
        variant = Variant(last_challenge_event["variant"]["key"])

        if event_color == "white":
            color = Challenge_Color.BLACK
        elif event_color == "black":
            color = Challenge_Color.WHITE
        else:
            color = Challenge_Color.RANDOM

        challenge_request = Challenge_Request(opponent_username, initial_time, increment, rated, color, variant, 300)
        self.game_manager.request_challenge(challenge_request)
        print(f"Challenge against {challenge_request.opponent_username} added to the queue.")

    def _reset(self, command: list[str]) -> None:
        if len(command) != 2:
            print(COMMANDS["reset"])
            return

        try:
            perf_type = self._find_enum(command[1], Perf_Type)
        except ValueError as e:
            print(e)
            return

        self.game_manager.matchmaking.opponents.reset_release_time(perf_type)
        print("Matchmaking has been reset.")

    async def _stats(self) -> None:
        """Display bot statistics and performance information."""
        print("\n=== Bot Statistics ===")

        try:
            account = await self.api.get_account()
            print(f"👤 Username: {account['username']}")

            perfs = account.get('perfs', {})
            if perfs:
                print("\nCurrent Ratings:")
                for perf_type, perf_data in perfs.items():
                    if 'rating' in perf_data:
                        rating = perf_data['rating']
                        provisional = "?" if perf_data.get('provisional', False) else ""
                        print(f"  {perf_type.title():<15}: {rating}{provisional}")

            activity = await self.api.get_user_activity(account['username'])
            if activity and isinstance(activity, list) and len(activity) > 0:
                today_activity = activity[0]

                if 'games' in today_activity:
                    games = today_activity['games']
                    print("\nToday's Games:")

                    total_games = 0
                    try:
                        for variant_data in games.values():
                            if isinstance(variant_data, dict):
                                total_games += sum(count for count in variant_data.values() if isinstance(count, int))
                    except Exception:
                        total_games = 0

                    print(f"Total Games: {total_games}")

                    for variant, results in games.items():
                        if not isinstance(results, dict):
                            continue

                        wins = results.get('win', 0) if isinstance(results.get('win'), int) else 0
                        losses = results.get('loss', 0) if isinstance(results.get('loss'), int) else 0
                        draws = results.get('draw', 0) if isinstance(results.get('draw'), int) else 0
                        variant_total = wins + losses + draws

                        if variant_total > 0:
                            win_rate = (wins + 0.5 * draws) / variant_total * 100 if variant_total > 0 else 0
                            
                            rating_diff = 0
                            if isinstance(results.get('rp'), dict):
                                rp_data = results['rp']
                                before = rp_data.get('before', 0)
                                after = rp_data.get('after', 0)
                                rating_diff = after - before
                            
                            results_parts = []
                            if wins > 0:
                                results_parts.append(f"{wins} win{'s' if wins != 1 else ''}")
                            if draws > 0:
                                results_parts.append(f"{draws} draw{'s' if draws != 1 else ''}")
                            if losses > 0:
                                results_parts.append(f"{losses} loss{'es' if losses != 1 else ''}")
                            
                            results_str = ", ".join(results_parts)
                            
                            diff_str = f"+{rating_diff}" if rating_diff > 0 else str(rating_diff)
                            
                            variant_name = variant.title()
                            print(f"{variant_name:<15}: ({variant_total} game{'s' if variant_total != 1 else ''}: {results_str} • {win_rate:.1f}% win rate • {diff_str})")

            else:
                print("\nNo games played today.")

        except Exception as e:
            print(f"Could not retrieve stats: {e}")

        print("\nSystem Information:")
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        print(f"Memory Usage: {memory_mb:.1f} MB")
        cpu_percent = process.cpu_percent(interval=0.1)
        print(f"CPU Usage: {cpu_percent:.1f}%")

        print("=" * 25)

    def _stop(self) -> None:
        if self.game_manager.stop_matchmaking():
            print("Stopping matchmaking ...")
        else:
            print("Matchmaking isn't currently running ...")

    def _tournament(self, command: list[str]) -> None:
        if len(command) < 2 or len(command) > 4:
            print(COMMANDS["tournament"])
            return

        tournament_id = command[1]
        tournament_team = command[2] if len(command) > 2 else None
        tournament_password = command[3] if len(command) > 3 else None

        self.game_manager.request_tournament_joining(tournament_id, tournament_team, tournament_password)

    def _whitelist(self, command: list[str]) -> None:
        if len(command) != 2:
            print(COMMANDS["whitelist"])
            return

        self.config.whitelist.append(command[1].lower())
        print(f"Added {command[1]} to the whitelist.")

    def _help(self) -> None:
        print("These commands are supported by BotLi:\n")
        for key, value in COMMANDS.items():
            print(f"{key:11}\t\t# {value}")

    def _find_enum(self, name: str, enum_type: type[EnumT]) -> EnumT:
        for enum in enum_type:
            if enum.lower() == name.lower():
                return enum

        raise ValueError(f"{name} is not a valid {enum_type}")

    def signal_handler(self, *_) -> None:
        self._quit_task = asyncio.create_task(self._quit())


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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("commands", nargs="*", help="Commands that BotLi executes.")
    parser.add_argument("--config", "-c", default="config.yml", help="Path to config.yml.")
    parser.add_argument("--upgrade", "-u", action="store_true", help="Upgrade account to BOT account.")
    parser.add_argument("--debug", "-d", action="store_true", help="Enable debug logging.")
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    asyncio.run(User_Interface().main(args.commands, args.config, args.upgrade), debug=args.debug)
