from datetime import datetime, timedelta
from queue import Queue
from threading import Event, Thread

from api import API
from botli_dataclasses import Game_Information
from chatter import Chatter
from lichess_game import Lichess_Game


class Game(Thread):
    def __init__(self, config: dict, api: API, game_id: str, game_finished_event: Event, game_queue: Queue) -> None:
        Thread.__init__(self)
        self.config = config
        self.api = api
        self.game_id = game_id
        self.game_finished_event = game_finished_event
        self.game_queue = game_queue

        self.game_info = Game_Information.from_gameFull_event(self.game_queue.get())
        self.lichess_game = Lichess_Game(self.api, self.game_info, self.config)
        self.chatter = Chatter(self.api, self.config, self.game_info, self.lichess_game)

    def start(self):
        Thread.start(self)

    def run(self) -> None:
        self._print_game_information()
        self.chatter.send_greetings()

        if self.game_info.state['status'] != 'started':
            self._print_result_message(self.game_info.state)
            self.chatter.send_goodbyes()
            self.lichess_game.end_game()
            return

        if self.lichess_game.is_our_turn:
            self._make_move()
        else:
            self.lichess_game.start_pondering()

        opponent_title = self.game_info.black_title if self.lichess_game.is_white else self.game_info.white_title
        abortion_seconds = 30.0 if opponent_title == 'BOT' else 60.0
        abortion_time = datetime.now() + timedelta(seconds=abortion_seconds)

        while True:
            event = self.game_queue.get()

            if event['type'] not in ['gameFull', 'gameState']:
                if self.lichess_game.is_abortable and datetime.now() >= abortion_time:
                    print('Aborting game ...')
                    self.api.abort_game(self.game_id)
                    self.chatter.send_abortion_message()

            if event['type'] == 'gameFull':
                if event['state']['status'] != 'started':
                    self._print_result_message(event['state'])
                    self.chatter.send_goodbyes()
                    break

                self.lichess_game.update(event['state'])

                if self.lichess_game.is_our_turn:
                    self._make_move()
                else:
                    self.lichess_game.start_pondering()
            elif event['type'] == 'gameState':
                if event['status'] != 'started':
                    self._print_result_message(event)
                    self.chatter.send_goodbyes()
                    break

                self.lichess_game.update(event)

                if self.lichess_game.is_our_turn and not self.lichess_game.board.is_repetition():
                    self._make_move()
            elif event['type'] == 'chatLine':
                self.chatter.handle_chat_message(event)
            elif event['type'] == 'opponentGone':
                continue
            elif event['type'] == 'ping':
                continue
            else:
                print(event)

        self.lichess_game.end_game()
        self.game_finished_event.set()

    def _make_move(self) -> None:
        uci_move, offer_draw, resign = self.lichess_game.make_move()
        if resign:
            self.api.resign_game(self.game_id)
        else:
            self.api.send_move(self.game_id, uci_move, offer_draw)
            self.chatter.print_eval()

    def _print_game_information(self) -> None:
        opponents_str = f'{self.game_info.white_str}   -   {self.game_info.black_str}'
        message = (5 * ' ').join([self.game_info.id_str, opponents_str, self.game_info.tc_str,
                                  self.game_info.rated_str, self.game_info.variant_str])

        print(f'\n{message}\n{128 * "‾"}')

    def _print_result_message(self, game_state: dict) -> None:
        if winner := game_state.get('winner'):
            if winner == 'white':
                message = f'{self.game_info.white_name} won'
                loser = self.game_info.black_name
                white_result = '1'
                black_result = '0'
            else:
                message = f'{self.game_info.black_name} won'
                loser = self.game_info.white_name
                white_result = '0'
                black_result = '1'

            if game_state['status'] == 'mate':
                message += ' by checkmate!'
            elif game_state['status'] == 'outoftime':
                message += f'! {loser} ran out of time.'
            elif game_state['status'] == 'resign':
                message += f'! {loser} resigned.'
            elif game_state['status'] == 'variantEnd':
                message += ' by variant rules!'
        else:
            white_result = '½'
            black_result = '½'

            if game_state['status'] == 'draw':
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
            elif game_state['status'] == 'stalemate':
                message = 'Game drawn by stalemate.'
            else:
                message = 'Game aborted.'

                white_result = 'X'
                black_result = 'X'

        opponents_str = f'{self.game_info.white_str} {white_result} - {black_result} {self.game_info.black_str}'
        message = (5 * ' ').join([self.game_info.id_str, opponents_str, message])

        print(f'{message}\n{128 * "‾"}')
