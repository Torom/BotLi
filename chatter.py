import os
import platform

import psutil

from lichess_game import Lichess_Game


class Chatter:
    def __init__(self, config: dict) -> None:
        self.cpu = self._get_cpu()
        self.ram_message = self._get_ram()
        self.draw_message = self._get_draw_message(config)

    def react(self, command: str, lichess_game: Lichess_Game) -> str:
        if command == 'cpu':
            return self.cpu
        elif command == 'draw':
            return self.draw_message
        elif command == 'engine':
            return lichess_game.engine.id["name"]
        elif command == 'eval':
            return lichess_game.last_message
        elif command == 'name':
            return f'{lichess_game.username} running {lichess_game.engine.id["name"]} (Torom\'s BotLi)'
        elif command == 'ram':
            return self.ram_message
        else:
            return 'Supported commands: !cpu, !draw, !engine, !eval, !name, !ram'

    def _get_cpu(self) -> str:
        cpu = ''
        if os.path.exists('/proc/cpuinfo'):
            with open('/proc/cpuinfo', 'r') as cpuinfo:
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


class Chat_Message:
    def __init__(self, chatLine_event: dict) -> None:
        self.username: str = chatLine_event['username']
        self.text: str = chatLine_event['text']
        self.room: str = chatLine_event['room']
