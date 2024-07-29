from asyncio import Event
from datetime import datetime, timedelta
from typing import Any, AsyncIterator

from api import API
from botli_dataclasses import Game_Information
from chatter import Chatter
from config import Config
from lichess_game import Lichess_Game


class Game:
    def __init__(self,
                 api: API,
                 game_id: str,
                 game_finished_event: Event,
                 game_stream: AsyncIterator[dict[str, Any]],
                 game_information: Game_Information,
                 lichess_game: Lichess_Game,
                 chatter: Chatter) -> None:
        self.api = api
        self.game_id = game_id
        self.game_finished_event = game_finished_event
        self.game_stream = game_stream
        self.info = game_information
        self.lichess_game = lichess_game
        self.chatter = chatter
        self.has_timed_out = False

    @classmethod
    async def create(cls, api: API, config: Config, game_id: str, game_finished_event: Event) -> 'Game':
        game_stream = api.get_game_stream(game_id)
        info = Game_Information.from_gameFull_event(await anext(game_stream))
        lichess_game = Lichess_Game(api, config, info)
        await lichess_game.init_engine()
        game = cls(api,
                   game_id,
                   game_finished_event,
                   game_stream,
                   info,
                   lichess_game,
                   Chatter(api, config, info, lichess_game))
        return game

    async def run(self) -> None:
        self._print_game_information()
        await self.chatter.send_greetings()

        if self.info.state['status'] != 'started':
            self._print_result_message(self.info.state)
            await self.chatter.send_goodbyes()
            await self.lichess_game.end_game()
            return

        if self.lichess_game.is_our_turn:
            await self._make_move()
        else:
            await self.lichess_game.start_pondering()

        opponent_title = self.info.black_title if self.lichess_game.is_white else self.info.white_title
        abortion_seconds = 30.0 if opponent_title == 'BOT' else 60.0
        abortion_time = datetime.now() + timedelta(seconds=abortion_seconds)

        async for event in self.game_stream:
            if event['type'] not in ['gameFull', 'gameState']:
                if self.lichess_game.is_abortable and datetime.now() >= abortion_time:
                    print('Aborting game ...')
                    await self.api.abort_game(self.game_id)
                    await self.chatter.send_abortion_message()
                    self.has_timed_out = True

            if event['type'] == 'gameFull':
                self.lichess_game.update(event['state'])

                if event['state']['status'] != 'started':
                    self._print_result_message(event['state'])
                    await self.chatter.send_goodbyes()
                    break

                if self.lichess_game.is_our_turn:
                    await self._make_move()
                else:
                    await self.lichess_game.start_pondering()
            elif event['type'] == 'gameState':
                self.lichess_game.update(event)

                if event['status'] != 'started':
                    self._print_result_message(event)
                    await self.chatter.send_goodbyes()
                    break

                if self.lichess_game.is_our_turn and not self.lichess_game.board.is_repetition():
                    await self._make_move()
            elif event['type'] == 'chatLine':
                await self.chatter.handle_chat_message(event)
            elif event['type'] == 'opponentGone':
                continue
            elif event['type'] == 'ping':
                continue
            else:
                print(event)

        await self.lichess_game.end_game()
        self.game_finished_event.set()

    async def _make_move(self) -> None:
        lichess_move = await self.lichess_game.make_move()
        if lichess_move.resign:
            await self.api.resign_game(self.game_id)
        else:
            await self.api.send_move(self.game_id, lichess_move.uci_move, lichess_move.offer_draw)
            await self.chatter.print_eval()

    def _print_game_information(self) -> None:
        opponents_str = f'{self.info.white_str}   -   {self.info.black_str}'
        message = (5 * ' ').join([self.info.id_str, opponents_str, self.info.tc_str,
                                  self.info.rated_str, self.info.variant_str])

        print(f'\n{message}\n{128 * "‾"}')

    def _print_result_message(self, game_state: dict) -> None:
        if winner := game_state.get('winner'):
            if winner == 'white':
                message = f'{self.info.white_name} won'
                loser = self.info.black_name
                white_result = '1'
                black_result = '0'
            else:
                message = f'{self.info.black_name} won'
                loser = self.info.white_name
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

        opponents_str = f'{self.info.white_str} {white_result} - {black_result} {self.info.black_str}'
        message = (5 * ' ').join([self.info.id_str, opponents_str, message])

        print(f'{message}\n{128 * "‾"}')
