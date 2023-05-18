from queue import Queue
from threading import Event, Thread

from api import API
from botli_dataclasses import Game_Information
from chatter import Chatter
from enums import Game_Status
from lichess_game import Lichess_Game


class Game(Thread):
    def __init__(self, config: dict, api: API, game_id: str, game_finished_event: Event) -> None:
        Thread.__init__(self)
        self.config = config
        self.api = api
        self.game_id = game_id
        self.game_finished_event = game_finished_event
        self.ping_counter = 0
        self.abortion_counter = 0
        self.lichess_game: Lichess_Game | None = None
        self.chatter: Chatter | None = None
        self.game_info: Game_Information | None = None

    def start(self):
        Thread.start(self)

    def run(self) -> None:
        game_queue = Queue()
        game_queue_thread = Thread(target=self.api.get_game_stream, args=(self.game_id, game_queue), daemon=True)
        game_queue_thread.start()

        gameFull_event = game_queue.get()
        self.game_info = Game_Information.from_gameFull_event(gameFull_event, self.api.username)
        self._print_game_information()
        self.lichess_game = Lichess_Game(self.api, self.game_info, self.config)
        self.chatter = Chatter(self.api, self.config, self.game_info, self.lichess_game)
        self.chatter.send_greetings()

        if self._finish_game(gameFull_event['state'].get('winner')):
            self.lichess_game.end_game()
            return

        if self.lichess_game.is_our_turn:
            self._make_move()
        else:
            self.lichess_game.start_pondering()

        while True:
            event = game_queue.get()

            if event['type'] == 'gameFull':
                self.lichess_game.update(event['state'])

                if self._finish_game(event['state'].get('winner')):
                    break

                if self.lichess_game.is_our_turn:
                    self._make_move()
                else:
                    self.lichess_game.start_pondering()
            elif event['type'] == 'gameState':
                self.ping_counter = 0
                updated = self.lichess_game.update(event)

                if self._finish_game(event.get('winner')):
                    break

                if self.lichess_game.is_game_over:
                    continue

                if self.lichess_game.is_our_turn and updated:
                    self._make_move()
            elif event['type'] == 'chatLine':
                self.chatter.handle_chat_message(event)
            elif event['type'] == 'opponentGone':
                continue
            elif event['type'] == 'ping':
                self.ping_counter += 1

                max_pings = 5 if self.game_info.opponent_is_bot else 10
                if self.ping_counter >= max_pings and self.lichess_game.is_abortable:
                    print('Aborting game ...')
                    self.chatter.send_abortion_message()
                    self.api.abort_game(self.game_id)
                    self.abortion_counter += 1

                    if self.abortion_counter >= 3:
                        break
            else:
                print(event)

        self.lichess_game.end_game()
        self.game_finished_event.set()

    def _make_move(self) -> None:
        assert self.lichess_game
        assert self.chatter

        uci_move, offer_draw, resign = self.lichess_game.make_move()
        if resign:
            self.api.resign_game(self.game_id)
        else:
            self.api.send_move(self.game_id, uci_move, offer_draw)
            self.chatter.print_eval()

    def _finish_game(self, winner: str | None) -> bool:
        assert self.lichess_game
        assert self.chatter

        if self.lichess_game.is_finished:
            self._print_result_message(winner)
            self.chatter.send_goodbyes()
            return True

        return False

    def _print_game_information(self) -> None:
        assert self.game_info

        opponents_str = f'{self.game_info.white_str}   -   {self.game_info.black_str}'
        delimiter = 5 * ' '

        print()
        print(delimiter.join([self.game_info.id_str, opponents_str, self.game_info.tc_str,
                              self.game_info.rated_str, self.game_info.variant_str]))
        print(128 * '‾')

    def _print_result_message(self, winner: str | None) -> None:
        assert self.lichess_game
        assert self.game_info

        winning_name = self.game_info.white_name if winner == 'white' else self.game_info.black_name
        winning_title = self.game_info.white_title if winner == 'white' else self.game_info.black_title
        losing_name = self.game_info.white_name if winner == 'black' else self.game_info.black_name
        losing_title = self.game_info.white_title if winner == 'black' else self.game_info.black_title

        if winner:
            if winner == 'white':
                white_result = '1'
                black_result = '0'
            else:
                white_result = '0'
                black_result = '1'

            message = f'{winning_title}{" " if winning_title else ""}{winning_name} won'

            if self.lichess_game.status == Game_Status.MATE:
                message += ' by checkmate!'
            elif self.lichess_game.status == Game_Status.OUT_OF_TIME:
                message += f'! {losing_title}{" " if losing_title else ""}{losing_name} ran out of time.'
            elif self.lichess_game.status == Game_Status.RESIGN:
                message += f'! {losing_title}{" " if losing_title else ""}{losing_name} resigned.'
            elif self.lichess_game.status == Game_Status.VARIANT_END:
                message += ' by variant rules!'
        else:
            white_result = '½'
            black_result = '½'

            if self.lichess_game.status == Game_Status.DRAW:
                if self.lichess_game.board.is_fifty_moves():
                    message = 'Game drawn by 50-move rule.'
                elif self.lichess_game.board.is_repetition():
                    message = 'Game drawn by threefold repetition.'
                elif self.lichess_game.board.is_insufficient_material():
                    message = 'Game drawn due to insufficient material.'
                elif self.lichess_game.board.is_variant_draw():
                    message = 'Game drawn by variant rules.'
                else:
                    message = 'Game drawn by agreement.'
            elif self.lichess_game.status == Game_Status.STALEMATE:
                message = 'Game drawn by stalemate.'
            else:
                message = 'Game aborted.'

                white_result = 'X'
                black_result = 'X'

        opponents_str = f'{self.game_info.white_str} {white_result} - {black_result} {self.game_info.black_str}'
        delimiter = 5 * ' '

        print(delimiter.join([self.game_info.id_str, opponents_str, message]))
        print(128 * '‾')
