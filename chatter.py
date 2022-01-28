import os
import platform

from lichess_game import Lichess_Game


class Chatter:
    def __init__(self) -> None:
        self.cpu = self._get_cpu()
        self.ram = self._get_ram()

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
            return 'see !engine'
        elif command == 'ram':
            return self.ram
        elif command == 'tb':
            return '6-men syzygy tablebases on SSD'
        else:
            return 'Supported commands: !cpu, !draw, !engine, !eval, !ram, !tb'

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


class Chat_Message:
    def __init__(self, chatLine_event: dict) -> None:
        self.username: str = chatLine_event['username']
        self.text: str = chatLine_event['text']
        self.room: str = chatLine_event['room']
