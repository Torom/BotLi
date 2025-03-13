import os
import platform
from collections import defaultdict

import psutil

from api import API
from botli_dataclasses import Chat_Message, Game_Information
from config import Config
from lichess_game import Lichess_Game


class Chatter:
    def __init__(self,
                 api: API,
                 config: Config,
                 username: str,
                 game_information: Game_Information,
                 lichess_game: Lichess_Game
                 ) -> None:
        self.api = api
        self.username = username
        self.game_info = game_information
        self.lichess_game = lichess_game
        self.cpu_message = self._get_cpu()
        self.draw_message = self._get_draw_message(config)
        self.name_message = self._get_name_message(config.version)
        self.ram_message = self._get_ram()
        self.player_greeting = self._format_message(config.messages.greeting)
        self.player_goodbye = self._format_message(config.messages.goodbye)
        self.spectator_greeting = self._format_message(config.messages.greeting_spectators)
        self.spectator_goodbye = self._format_message(config.messages.goodbye_spectators)
        self.print_eval_rooms: set[str] = set()

    async def handle_chat_message(self, chatLine_Event: dict) -> None:
        chat_message = Chat_Message.from_chatLine_event(chatLine_Event)

        if chat_message.username == 'lichess':
            if chat_message.room == 'player':
                print(chat_message.text)
            return

        if chat_message.username != self.username:
            prefix = f'{chat_message.username} ({chat_message.room}): '
            output = prefix + chat_message.text
            if len(output) > 128:
                output = f'{output[:128]}\n{len(prefix) * " "}{output[128:]}'

            print(output)

        if chat_message.text.startswith('!'):
            await self._handle_command(chat_message)

    async def print_eval(self) -> None:
        if not self.game_info.increment_ms and self.lichess_game.own_time < 30.0:
            return

        for room in self.print_eval_rooms:
            await self._send_last_message(room)

    async def send_greetings(self) -> None:
        if self.player_greeting:
            await self.api.send_chat_message(self.game_info.id_, 'player', self.player_greeting)

        if self.spectator_greeting:
            await self.api.send_chat_message(self.game_info.id_, 'spectator', self.spectator_greeting)

    async def send_goodbyes(self) -> None:
        if self.lichess_game.is_abortable:
            return

        if self.player_goodbye:
            await self.api.send_chat_message(self.game_info.id_, 'player', self.player_goodbye)

        if self.spectator_goodbye:
            await self.api.send_chat_message(self.game_info.id_, 'spectator', self.spectator_goodbye)

    async def send_abortion_message(self) -> None:
        await self.api.send_chat_message(self.game_info.id_, 'player', ('Too bad you weren\'t there. '
                                                                        'Feel free to challenge me again, '
                                                                        'I will accept the challenge if possible.'))

    async def _handle_command(self, chat_message: Chat_Message) -> None:
        match chat_message.text[1:].lower():
            case 'cpu':
                await self.api.send_chat_message(self.game_info.id_, chat_message.room, self.cpu_message)
            case 'draw':
                await self.api.send_chat_message(self.game_info.id_, chat_message.room, self.draw_message)
            case 'eval':
                await self._send_last_message(chat_message.room)
            case 'motor':
                await self.api.send_chat_message(self.game_info.id_, chat_message.room, self.lichess_game.engine.name)
            case 'name':
                await self.api.send_chat_message(self.game_info.id_, chat_message.room, self.name_message)
            case 'printeval':
                if not self.game_info.increment_ms and self.game_info.initial_time_ms < 180_000:
                    await self._send_last_message(chat_message.room)
                    return

                if chat_message.room in self.print_eval_rooms:
                    return

                self.print_eval_rooms.add(chat_message.room)
                await self.api.send_chat_message(self.game_info.id_,
                                                 chat_message.room,
                                                 'Type !quiet to stop eval printing.')
                await self._send_last_message(chat_message.room)
            case 'quiet':
                self.print_eval_rooms.discard(chat_message.room)
            case 'pv':
                if chat_message.room == 'player':
                    return

                if not (message := self._append_pv()):
                    message = 'No PV available.'

                await self.api.send_chat_message(self.game_info.id_, chat_message.room, message)
            case 'ram':
                await self.api.send_chat_message(self.game_info.id_, chat_message.room, self.ram_message)
            case 'help' | 'commands':
                if chat_message.room == 'player':
                    message = 'Supported commands: !cpu, !draw, !eval, !motor, !name, !printeval, !ram'
                else:
                    message = 'Supported commands: !cpu, !draw, !eval, !motor, !name, !printeval, !pv, !ram'

                await self.api.send_chat_message(self.game_info.id_, chat_message.room, message)

    async def _send_last_message(self, room: str) -> None:
        last_message = self.lichess_game.last_message.replace('Engine', 'Evaluation')
        last_message = ' '.join(last_message.split())

        if room == 'spectator':
            last_message = self._append_pv(last_message)

        await self.api.send_chat_message(self.game_info.id_, room, last_message)

    def _get_cpu(self) -> str:
        cpu = ''
        if os.path.exists('/proc/cpuinfo'):
            with open('/proc/cpuinfo', encoding='utf-8') as cpuinfo:
                while line := cpuinfo.readline():
                    if line.startswith('model name'):
                        cpu = line.split(': ')[1]
                        cpu = cpu.replace('(R)', '')
                        cpu = cpu.replace('(TM)', '')

                        if len(cpu.split()) > 1:
                            return cpu

        if processor := platform.processor():
            cpu = processor.split()[0]
            cpu = cpu.replace('GenuineIntel', 'Intel')

        cores = psutil.cpu_count(logical=False)
        threads = psutil.cpu_count(logical=True)
        cpu_freq = psutil.cpu_freq().max / 1000

        return f'{cpu} {cores}c/{threads}t @ {cpu_freq:.2f}GHz'

    def _get_ram(self) -> str:
        mem_bytes = psutil.virtual_memory().total
        mem_gib = mem_bytes / (1024.**3)

        return f'{mem_gib:.1f} GiB'

    def _get_draw_message(self, config: Config) -> str:
        if not config.offer_draw.enabled:
            return 'This bot will neither accept nor offer draws.'

        max_score = config.offer_draw.score / 100

        return (f'The bot offers draw at move {config.offer_draw.min_game_length} or later '
                f'if the eval is within +{max_score:.2f} to -{max_score:.2f} for the last '
                f'{config.offer_draw.consecutive_moves} moves.')

    def _get_name_message(self, version: str) -> str:
        return (f'{self.username} running {self.lichess_game.engine.name} (BotLi {version})')

    def _format_message(self, message: str | None) -> str | None:
        if not message:
            return

        opponent_username = self.game_info.black_name if self.lichess_game.is_white else self.game_info.white_name
        mapping = defaultdict(str, {'opponent': opponent_username, 'me': self.username,
                                    'engine': self.lichess_game.engine.name, 'cpu': self.cpu_message,
                                    'ram': self.ram_message})
        return message.format_map(mapping)

    def _append_pv(self, initial_message: str = '') -> str:
        if len(self.lichess_game.last_pv) < 2:
            return initial_message

        if initial_message:
            initial_message += ' '

        if self.lichess_game.is_our_turn:
            board = self.lichess_game.board.copy(stack=1)
            board.pop()
        else:
            board = self.lichess_game.board.copy(stack=False)

        if board.turn:
            initial_message += 'PV:'
        else:
            initial_message += f'PV: {board.fullmove_number}...'

        final_message = initial_message
        for move in self.lichess_game.last_pv[1:]:
            if board.turn:
                initial_message += f' {board.fullmove_number}.'
            initial_message += f' {board.san(move)}'
            if len(initial_message) > 140:
                break
            board.push(move)
            final_message = initial_message

        return final_message
