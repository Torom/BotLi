import json
from queue import Queue
from threading import Thread

from api import API
from chatter import Chat_Message, Chatter
from enums import Game_Status
from lichess_game import Lichess_Game


class Game_api:
    def __init__(self, config: dict, api: API, game_id: str) -> None:
        self.config: dict = config
        self.api = api
        self.game_id = game_id
        self.chatter = Chatter(config)
        self.ping_counter = 0
        self.game_queue = Queue()
        self.was_aborted = False

    def run_game(self) -> None:
        game_queue_thread = Thread(target=self._watch_game_stream, daemon=True)
        game_queue_thread.start()

        while True:
            event = self.game_queue.get()

            if event['type'] == 'gameFull':
                print(f'Game "{self.game_id}" was started.')
                self.lichess_game = Lichess_Game(self.api, event, self.config)

                if self.lichess_game.is_our_turn():
                    uci_move, offer_draw, resign = self.lichess_game.make_move()
                    if resign:
                        self.api.resign_game(self.game_id)
                    else:
                        self.api.send_move(self.game_id, uci_move, offer_draw)
            elif event['type'] == 'gameState':
                updated = self.lichess_game.update(event)

                if self.lichess_game.status != Game_Status.STARTED:
                    self.was_aborted = self.lichess_game.status == Game_Status.ABORTED
                    print(self.lichess_game.get_result_message(event.get('winner')))
                    break

                if self.lichess_game.is_game_over():
                    continue

                if self.lichess_game.is_our_turn() and updated:
                    uci_move, offer_draw, resign = self.lichess_game.make_move()
                    if resign:
                        self.api.resign_game(self.game_id)
                    else:
                        self.api.send_move(self.game_id, uci_move, offer_draw)
            elif event['type'] == 'chatLine':
                chat_message = Chat_Message(event)

                if chat_message.username == 'lichess':
                    if chat_message.room == 'player':
                        print(f'{chat_message.username}: {chat_message.text}')
                    continue

                print(f'{chat_message.username} ({chat_message.room}): {chat_message.text}')

                if chat_message.text.startswith('!'):
                    command = chat_message.text[1:].lower()
                    response = self.chatter.react(command, self.lichess_game)

                    self.api.send_chat_message(self.game_id, chat_message.room, response)
            elif event['type'] == 'ping':
                self.ping_counter += 1

                if self.ping_counter >= 7 and self.lichess_game.is_abortable() and not self.lichess_game.is_our_turn():
                    self.api.abort_game(self.game_id)
            else:
                print(event)

        self.lichess_game.quit_engine()

    def _watch_game_stream(self) -> None:
        game_stream = self.api.get_game_stream(self.game_id)

        for line in game_stream:
            if line:
                event = json.loads(line.decode('utf-8'))
            else:
                event = {'type': 'ping'}

            self.game_queue.put_nowait(event)
