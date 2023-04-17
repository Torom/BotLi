import os
import platform
from collections import defaultdict

import psutil

from api import API
from botli_dataclasses import Game_Information
from lichess_game import Lichess_Game


class Chat_Message:
    def __init__(self, chatLine_event: dict) -> None:
        self.username: str = chatLine_event['username']
        self.text: str = chatLine_event['text']
        self.room: str = chatLine_event['room']


class Chatter:
    def __init__(self, api: API, config: dict, game_information: Game_Information, lichess_game: Lichess_Game) -> None:
        self.api = api
        self.game_info = game_information
        self.lichess_game = lichess_game
        self.version: str = config['version']
        self.cpu_message = self._get_cpu()
        self.draw_message = self._get_draw_message(config)
        self.ram_message = self._get_ram()
        self.player_greeting = self._format_message(config['messages'].get('greeting', ''))
        self.player_goodbye = self._format_message(config['messages'].get('goodbye', ''))
        self.spectator_greeting = self._format_message(config['messages'].get('greeting_spectators', ''))
        self.spectator_goodbye = self._format_message(config['messages'].get('goodbye_spectators', ''))
        self.print_eval_rooms: set[str] = set()

    @property
    def last_message(self) -> str:
        last_message = self.lichess_game.last_message.replace('Engine', 'Evaluation')
        return ' '.join(last_message.split())

    def handle_chat_message(self, chatLine_Event: dict) -> None:
        chat_message = Chat_Message(chatLine_Event)

        if chat_message.username == 'lichess':
            if chat_message.room == 'player':
                print(f'{chat_message.username}: {chat_message.text}')
            return
        elif chat_message.username != self.api.username:
            print(f'{chat_message.username} ({chat_message.room}): {chat_message.text}')

        if chat_message.text.startswith('!'):
            if response := self._handle_command(chat_message):
                self.api.send_chat_message(self.game_info.id_, chat_message.room, response)

    def print_eval(self) -> None:
        for room in self.print_eval_rooms:
            self.api.send_chat_message(self.game_info.id_, room, self.last_message)

    def send_greetings(self) -> None:
        self.api.send_chat_message(self.game_info.id_, 'player', self.player_greeting)
        self.api.send_chat_message(self.game_info.id_, 'spectator', self.spectator_greeting)

    def send_goodbyes(self) -> None:
        if self.lichess_game.is_abortable:
            return

        self.api.send_chat_message(self.game_info.id_, 'player', self.player_goodbye)
        self.api.send_chat_message(self.game_info.id_, 'spectator', self.spectator_goodbye)

    def send_abortion_message(self) -> None:
        message = 'Too bad you weren\'t there. Feel free to challenge me again, I will accept the challenge when I have time.'
        self.api.send_chat_message(self.game_info.id_, 'player', message)

    def _handle_command(self, chat_message: Chat_Message) -> str | None:
        command = chat_message.text[1:].lower()
        if command == 'cpu':
            return self.cpu_message
        elif command == 'draw':
            return self.draw_message
        elif command == 'eval':
            return self.last_message
        elif command == 'motor':
            return self.lichess_game.engine.id['name']
        elif command == 'name':
            return f'{self.api.username} running {self.lichess_game.engine.id["name"]} (BotLi {self.version})'
        elif command == 'printeval':
            if not self.game_info.increment_ms and self.game_info.initial_time_ms < 180_000:
                return 'Time control is too fast for this function.'
            self.print_eval_rooms.add(chat_message.room)
            return self.last_message
        elif command == 'stopeval':
            self.print_eval_rooms.discard(chat_message.room)
        elif command == 'ram':
            return self.ram_message
        elif command in ['help', 'commands']:
            return 'Supported commands: !cpu, !draw, !eval, !motor, !name, !printeval / !stopeval, !ram'

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

        try:
            cpu_freq = psutil.cpu_freq().max / 1000
        except FileNotFoundError:
            cpu_freq = float('NaN')

        return f'{cpu} {cores}c/{threads}t @ {cpu_freq:.2f}GHz'

    def _get_ram(self) -> str:
        mem_bytes = psutil.virtual_memory().total
        mem_gib = mem_bytes/(1024.**3)

        return f'{mem_gib:.1f} GiB'

    def _get_draw_message(self, config: dict) -> str:
        draw_enabled = config['engine']['offer_draw']['enabled']

        if not draw_enabled:
            return 'This bot will neither accept nor offer draws.'

        min_game_length = config['engine']['offer_draw']['min_game_length']
        max_score = config['engine']['offer_draw']['score'] / 100
        consecutive_moves = config['engine']['offer_draw']['consecutive_moves']

        return f'The bot offers draw at move {min_game_length} or later ' \
            f'if the eval is within +{max_score:.2f} to -{max_score:.2f} for the last {consecutive_moves} moves.'

    def _format_message(self, message: str) -> str:
        opponent_username = self.game_info.black_name if self.game_info.is_white else self.game_info.white_name
        mapping = defaultdict(str, {'opponent': opponent_username, 'me': self.api.username,
                                    'engine': self.lichess_game.engine.id['name'], 'cpu': self.cpu_message,
                                    'ram': self.ram_message})
        return message.format_map(mapping)
