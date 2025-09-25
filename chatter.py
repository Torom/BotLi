import os
import platform
from collections import defaultdict

import psutil

from api import API
from botli_dataclasses import Chat_Message, Game_Information
from config import Config
from lichess_game import Lichess_Game
from utils import ml_print

COMMANDS = {
    "cpu": "Shows information about the bot's CPU (processor, cores, threads, frequency).",
    "draw": "Explains the bot's draw offering/accepting policy based on evaluation and game length.",
    "eval": "Shows the latest position evaluation.",
    "motor": "Displays the name of the chess motor currently being used.",
    "name": "Shows the bot's name and motor information.",
    "ping": "Tests the network connection latency to Lichess servers.",
    "printeval": "Enables automatic printing of evaluations after each move (use !quiet to stop).",
    "quiet": "Stops automatic evaluation printing (use after !printeval).",
    "ram": "Displays the amount of system memory (RAM).",
    "takeback": "Shows how many takebacks are allowed and how many the opponent has used.",
}
SPECTATOR_COMMANDS = {"pv": "Shows the principal variation (best line of play) from the latest position."}


class Chatter:
    def __init__(
        self, api: API, config: Config, username: str, game_information: Game_Information, lichess_game: Lichess_Game
    ) -> None:
        self.api = api
        self.username = username
        self.game_info = game_information
        self.lichess_game = lichess_game
        self.opponent_username = self.game_info.black_name if lichess_game.is_white else self.game_info.white_name
        self.cpu_message = self._get_cpu()
        self.draw_message = self._get_draw_message(config)
        self.name_message = self._get_name_message(config.version)
        self.ram_message = self._get_ram()
        self.player_greeting = self._format_message(config.messages.greeting)
        self.player_goodbye = self._format_message(config.messages.goodbye)
        self.spectator_greeting = self._format_message(config.messages.greeting_spectators)
        self.spectator_goodbye = self._format_message(config.messages.goodbye_spectators)
        self.print_eval_rooms: set[str] = set()

    async def handle_chat_message(self, chatLine_Event: dict, takeback_count: int, max_takebacks: int) -> None:
        chat_message = Chat_Message.from_chatLine_event(chatLine_Event)

        if chat_message.username == "lichess":
            if chat_message.room == "player":
                print(chat_message.text)
            return

        if chat_message.username != self.username:
            ml_print(f"{chat_message.username} ({chat_message.room}): ", chat_message.text)

        if chat_message.text.startswith("!"):
            await self._handle_command(chat_message, takeback_count, max_takebacks)

    async def print_eval(self) -> None:
        if not self.game_info.increment_ms and self.lichess_game.own_time < 30.0:
            return

        for room in self.print_eval_rooms:
            await self._send_last_message(room)

    async def send_greetings(self) -> None:
        if self.player_greeting:
            await self.api.send_chat_message(self.game_info.id_, "player", self.player_greeting)

        if self.spectator_greeting:
            await self.api.send_chat_message(self.game_info.id_, "spectator", self.spectator_greeting)

    async def send_goodbyes(self) -> None:
        if self.lichess_game.is_abortable:
            return

        if self.player_goodbye:
            await self.api.send_chat_message(self.game_info.id_, "player", self.player_goodbye)

        if self.spectator_goodbye:
            await self.api.send_chat_message(self.game_info.id_, "spectator", self.spectator_goodbye)

    async def send_abortion_message(self) -> None:
        await self.api.send_chat_message(
            self.game_info.id_,
            "player",
            ("Too bad you weren't there. Feel free to challenge me again, I will accept the challenge if possible."),
        )

    async def _handle_command(self, chat_message: Chat_Message, takeback_count: int, max_takebacks: int) -> None:
        match chat_message.text[1:].lower():
            case "cpu":
                await self.api.send_chat_message(self.game_info.id_, chat_message.room, self.cpu_message)
            case "draw":
                await self.api.send_chat_message(self.game_info.id_, chat_message.room, self.draw_message)
            case "eval":
                await self._send_last_message(chat_message.room)
            case "motor":
                await self.api.send_chat_message(self.game_info.id_, chat_message.room, self.lichess_game.engine.name)
            case "name":
                await self.api.send_chat_message(self.game_info.id_, chat_message.room, self.name_message)
            case "ping":
                if not self.game_info.increment_ms and self.lichess_game.own_time < 10.0:
                    return

                ping = await self.api.ping() * 1000.0
                await self.api.send_chat_message(self.game_info.id_, chat_message.room, f"Ping: {ping:.1f} ms")
            case "printeval":
                if not self.game_info.increment_ms and self.game_info.initial_time_ms < 180_000:
                    await self._send_last_message(chat_message.room)
                    return

                if chat_message.room in self.print_eval_rooms:
                    return

                self.print_eval_rooms.add(chat_message.room)
                await self.api.send_chat_message(
                    self.game_info.id_, chat_message.room, "Type !quiet to stop eval printing."
                )
                await self._send_last_message(chat_message.room)
            case "quiet":
                self.print_eval_rooms.discard(chat_message.room)
            case "pv":
                if chat_message.room == "player":
                    return

                if not (message := self._append_pv()):
                    message = "No PV available."

                await self.api.send_chat_message(self.game_info.id_, chat_message.room, message)
            case "ram":
                await self.api.send_chat_message(self.game_info.id_, chat_message.room, self.ram_message)
            case "takeback":
                await self._send_takeback_message(chat_message.room, takeback_count, max_takebacks)
            case command if command.startswith("help"):
                commands = COMMANDS if chat_message.room == "player" else COMMANDS | SPECTATOR_COMMANDS
                words = chat_message.text.split()
                if len(words) == 1:
                    message = f"Commands: !{', !'.join(commands)}. Type !help <command> for more information."
                    await self.api.send_chat_message(self.game_info.id_, chat_message.room, message)
                    return

                command = words[1].lstrip("!").lower()
                if command in commands:
                    message = f"!{command}: {commands[command]}"
                else:
                    message = f'Unknown command: "!{command}". Type !help for a list of available commands.'

                await self.api.send_chat_message(self.game_info.id_, chat_message.room, message)

    async def _send_last_message(self, room: str) -> None:
        last_message = self.lichess_game.last_message.replace("Engine", "Evaluation")
        last_message = " ".join(last_message.split())

        if room == "spectator":
            last_message = self._append_pv(last_message)

        await self.api.send_chat_message(self.game_info.id_, room, last_message)

    async def _send_takeback_message(self, room: str, takeback_count: int, max_takebacks: int) -> None:
        if not max_takebacks:
            message = f"{self.username} does not accept takebacks."
        else:
            message = (
                f"{self.username} accepts up to {max_takebacks} takeback(s). "
                f"{self.opponent_username} used {takeback_count} so far."
            )

        await self.api.send_chat_message(self.game_info.id_, room, message)

    def _get_cpu(self) -> str:
        cpu = ""
        if os.path.exists("/proc/cpuinfo"):
            with open("/proc/cpuinfo", encoding="utf-8") as cpuinfo:
                while line := cpuinfo.readline():
                    if line.startswith("model name"):
                        cpu = line.split(": ")[1]
                        cpu = cpu.replace("(R)", "")
                        cpu = cpu.replace("(TM)", "")

                        if len(cpu.split()) > 1:
                            return cpu

        if processor := platform.processor():
            cpu = processor.split()[0]
            cpu = cpu.replace("GenuineIntel", "Intel")

        cores = psutil.cpu_count(logical=False)
        threads = psutil.cpu_count(logical=True)
        cpu_freq = psutil.cpu_freq().max / 1000

        return f"{cpu} {cores}c/{threads}t @ {cpu_freq:.2f}GHz"

    def _get_ram(self) -> str:
        mem_bytes = psutil.virtual_memory().total
        mem_gib = mem_bytes / (1024.0**3)

        return f"{mem_gib:.1f} GiB"

    def _get_draw_message(self, config: Config) -> str:
        too_low_rating = (
            config.offer_draw.min_rating is not None
            and self.lichess_game.engine.opponent.rating is not None
            and self.lichess_game.engine.opponent.rating < config.offer_draw.min_rating
        )
        no_draw_against_humans = (
            not self.lichess_game.engine.opponent.is_engine and not config.offer_draw.against_humans
        )
        if not config.offer_draw.enabled or too_low_rating or no_draw_against_humans:
            return f"{self.username} will neither accept nor offer draws."

        max_score = config.offer_draw.score / 100

        return (
            f"{self.username} offers draw at move {config.offer_draw.min_game_length} or later "
            f"if the eval is within +{max_score:.2f} to -{max_score:.2f} for the last "
            f"{config.offer_draw.consecutive_moves} moves."
        )

    def _get_name_message(self, version: str) -> str:
        return f"{self.username} running {self.lichess_game.engine.name} (BotLi {version})"

    def _format_message(self, message: str | None) -> str | None:
        if not message:
            return

        mapping = defaultdict(
            str,
            {
                "opponent": self.opponent_username,
                "me": self.username,
                "engine": self.lichess_game.engine.name,
                "cpu": self.cpu_message,
                "ram": self.ram_message,
            },
        )
        return message.format_map(mapping)

    def _append_pv(self, initial_message: str = "") -> str:
        if len(self.lichess_game.last_pv) < 2:
            return initial_message

        if initial_message:
            initial_message += " "

        if self.lichess_game.is_our_turn:
            board = self.lichess_game.board.copy(stack=1)
            board.pop()
        else:
            board = self.lichess_game.board.copy(stack=False)

        if board.turn:
            initial_message += "PV:"
        else:
            initial_message += f"PV: {board.fullmove_number}..."

        final_message = initial_message
        for move in self.lichess_game.last_pv[1:]:
            if board.turn:
                initial_message += f" {board.fullmove_number}."
            initial_message += f" {board.san(move)}"
            if len(initial_message) > 140:
                break
            board.push(move)
            final_message = initial_message

        return final_message
