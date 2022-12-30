from queue import Queue
from threading import Thread

from api import API
from chatter import Chatter
from lichess_game import Lichess_Game


class Game(Thread):
    def __init__(self, config: dict, api: API, game_id: str) -> None:
        Thread.__init__(self)
        self.config = config
        self.api = api
        self.game_id = game_id
        self.ping_counter = 0
        self.abortion_counter = 0
        self.lichess_game: Lichess_Game | None = None
        self.chatter: Chatter | None = None

    def start(self):
        Thread.start(self)

    def run(self) -> None:
        game_queue = Queue()
        game_queue_thread = Thread(target=self.api.get_game_stream, args=(self.game_id, game_queue), daemon=True)
        game_queue_thread.start()

        while True:
            event = game_queue.get()

            if event['type'] == 'gameFull':
                if not self.lichess_game:
                    print(f'Game "{self.game_id}" was started.')
                    self.lichess_game = Lichess_Game(self.api, event, self.config)
                    self.chatter = Chatter(self.api, self.config, event, self.lichess_game)
                    self.chatter.send_greetings()
                else:
                    self.lichess_game.update(event['state'])

                if self.lichess_game.is_our_turn:
                    self._make_move()
                else:
                    self.lichess_game.start_pondering()
            elif event['type'] == 'gameState':
                assert self.lichess_game
                assert self.chatter

                self.ping_counter = 0
                updated = self.lichess_game.update(event)

                if self.lichess_game.is_finished:
                    print(self.lichess_game.get_result_message(event.get('winner')))
                    self.chatter.send_goodbyes()
                    break

                if self.lichess_game.is_game_over:
                    continue

                if self.lichess_game.is_our_turn and updated:
                    self._make_move()
            elif event['type'] == 'chatLine':
                assert self.lichess_game
                assert self.chatter

                self.chatter.handle_chat_message(event)
            elif event['type'] == 'opponentGone':
                continue
            elif event['type'] == 'ping':
                assert self.lichess_game
                assert self.chatter

                self.ping_counter += 1

                if self.ping_counter >= 10 and self.lichess_game.is_abortable:
                    print('Aborting game ...')
                    self.chatter.send_abortion_message()
                    self.api.abort_game(self.game_id)
                    self.abortion_counter += 1

                    if self.abortion_counter >= 3:
                        break
            else:
                print(event)

        assert self.lichess_game

        self.lichess_game.end_game()

    def _make_move(self) -> None:
        assert self.lichess_game
        assert self.chatter

        uci_move, offer_draw, resign = self.lichess_game.make_move()
        if resign:
            self.api.resign_game(self.game_id)
        else:
            self.api.send_move(self.game_id, uci_move, offer_draw)
            self.chatter.print_eval()
