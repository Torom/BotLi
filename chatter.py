import os
import platform

import psutil

from api import API
from lichess_game import Lichess_Game


class Chat_Message:
    def __init__(self, chatLine_event: dict) -> None:
        self.username: str = chatLine_event['username']
        self.text: str = chatLine_event['text']
        self.room: str = chatLine_event['room']


class Chatter:
    def __init__(self, api: API, config: dict, game_id: str) -> None:
        self.api = api
        self.game_id = game_id
        self.username = self.api.user['username']
        self.cpu_message = self._get_cpu()
        self.draw_message = self._get_draw_message(config)
        self.ram_message = self._get_ram()
        self.print_eval_rooms: set[str] = set()

    def handle_chat_message(self, chatLine_Event: dict, lichess_game: Lichess_Game) -> None:
        chat_message = Chat_Message(chatLine_Event)

        if chat_message.username == 'lichess':
            if chat_message.room == 'player':
                print(f'{chat_message.username}: {chat_message.text}')
            return
        elif chat_message.username != self.username:
            print(f'{chat_message.username} ({chat_message.room}): {chat_message.text}')

        if chat_message.text.startswith('!'):
            if response := self._handle_command(chat_message, lichess_game):
                self.api.send_chat_message(self.game_id, chat_message.room, response)

    def print_eval(self, lichess_game: Lichess_Game) -> None:
        for room in self.print_eval_rooms:
            self.api.send_chat_message(self.game_id, room, lichess_game.last_message)

    def _handle_command(self, chat_message: Chat_Message, lichess_game: Lichess_Game) -> str | None:
        command = chat_message.text[1:].lower()
        if command == 'cpu':
            return self.cpu_message
        elif command == 'draw':
            return self.draw_message
        elif command == 'engine':
            return lichess_game.engine.id['name']
        elif command == 'eval':
            return ' '.join(lichess_game.last_message.split())
        elif command == 'name':
            return f'{self.username} running {lichess_game.engine.id["name"]} (BotLi)'
        elif command == 'printeval':
            if not lichess_game.increment and lichess_game.initial_time < 180_000:
                return 'Time control is too fast for this function.'
            self.print_eval_rooms.add(chat_message.room)
            return ' '.join(lichess_game.last_message.split())
        elif command == 'stopeval':
            self.print_eval_rooms.discard(chat_message.room)
        elif command == 'ram':
            return self.ram_message
        else:
            return 'Supported commands: !cpu, !draw, !engine, !eval, !name, !printeval / !stopeval, !ram'

    def _get_cpu(self) -> str:
        cpu = ''
        if os.path.exists('/proc/cpuinfo'):
            with open('/proc/cpuinfo', 'r', encoding='utf-8') as cpuinfo:
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
