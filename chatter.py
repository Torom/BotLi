import os
import platform

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
            return 'The bot offers draw automatically at move 35 or later \
                    if the eval is within +0.15 to -0.15 for the last 5 moves. \
                    If there is a pawn advance or a capture the counter will be reset.'
        elif command == 'engine':
            return lichess_game.engine.id["name"]
        elif command == 'eval':
            return lichess_game.last_message
        elif command == 'name':
            return f'{lichess_game.username} running {lichess_game.engine.id["name"]} (Torom\'s BotLi)'
        elif command == 'ram':
            return self.ram_message
        elif command == 'tb':
            return '6-men syzygy tablebases on SSD'
        else:
            return 'Supported commands: !cpu, !draw, !engine, !eval, !name, !ram, !tb'

    def _get_cpu(self) -> str:
        if os.path.exists('/proc/cpuinfo'):
            with open('/proc/cpuinfo', 'r') as cpuinfo:
                while line := cpuinfo.readline():
                    if line.startswith('model name'):
                        return line.split(': ')[1]

        if cpu := platform.processor():
            return cpu

        return 'Unknown'

    def _get_ram(self) -> str:
        mem_bytes = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
        mem_gib = mem_bytes/(1024.**3)

        return f'{mem_gib:.1f} GiB'

    def _get_draw_message(self, config: dict) -> str:
        draw_enabled = config['engine']['offer_draw']['enabled']

        if not draw_enabled:
            return 'This bot will neither accept nor offer draws.'

        max_score_cp = config['engine']['offer_draw']['max_score'] / 100
        consecutive_moves = config['engine']['offer_draw']['consecutive_moves']
        min_game_length = config['engine']['offer_draw']['min_game_length']

        return f'The bot offers draw automatically at move {min_game_length} or later \
                if the eval is within +{max_score_cp:.2f} to -{max_score_cp:.2f} for the last {consecutive_moves} moves. \
                If there is a pawn advance or a capture the counter will be reset.'


class Chat_Message:
    def __init__(self, chatLine_event: dict) -> None:
        self.username: str = chatLine_event['username']
        self.text: str = chatLine_event['text']
        self.room: str = chatLine_event['room']
