from datetime import datetime, timedelta

from api import API
from botli_dataclasses import Game_Information
from chatter import Chatter
from config import Config
from lichess_game import Lichess_Game


class Game:
    def __init__(self, api: API, config: Config, username: str, game_id: str) -> None:
        self.api = api
        self.config = config
        self.username = username
        self.game_id = game_id
        self.was_aborted = False

    async def run(self) -> None:
        game_stream = self.api.get_game_stream(self.game_id)
        info = Game_Information.from_gameFull_event(await anext(game_stream))
        lichess_game = await Lichess_Game.acreate(self.api, self.config, self.username, info)
        chatter = Chatter(self.api, self.config, self.username, info, lichess_game)

        self._print_game_information(info)
        await chatter.send_greetings()

        if info.state['status'] != 'started':
            self._print_result_message(info.state, lichess_game, info)
            await chatter.send_goodbyes()
            await lichess_game.end_game()
            return

        if lichess_game.is_our_turn:
            await self._make_move(lichess_game, chatter)
        else:
            await lichess_game.start_pondering()

        opponent_title = info.black_title if lichess_game.is_white else info.white_title
        abortion_seconds = 30.0 if opponent_title == 'BOT' else 60.0
        abortion_time = datetime.now() + timedelta(seconds=abortion_seconds)

        async for event in game_stream:
            if event['type'] not in ['gameFull', 'gameState']:
                if lichess_game.is_abortable and datetime.now() >= abortion_time:
                    print('Aborting game ...')
                    await self.api.abort_game(self.game_id)
                    await chatter.send_abortion_message()

                if event['type'] == 'chatLine':
                    await chatter.handle_chat_message(event)

                continue

            if event['type'] == 'gameFull':
                event = event['state']

            lichess_game.update(event)

            if event['status'] != 'started':
                self._print_result_message(event, lichess_game, info)
                await chatter.send_goodbyes()
                break

            if lichess_game.is_our_turn and not lichess_game.board.is_repetition():
                await self._make_move(lichess_game, chatter)

        self.was_aborted = lichess_game.is_abortable
        await lichess_game.end_game()

    async def _make_move(self, lichess_game: Lichess_Game, chatter: Chatter) -> None:
        lichess_move = await lichess_game.make_move()
        if lichess_move.resign:
            await self.api.resign_game(self.game_id)
        else:
            await self.api.send_move(self.game_id, lichess_move.uci_move, lichess_move.offer_draw)
            await chatter.print_eval()

    def _print_game_information(self, info: Game_Information) -> None:
        opponents_str = f'{info.white_str}   -   {info.black_str}'
        message = (5 * ' ').join([info.id_str, opponents_str, info.tc_str,
                                  info.rated_str, info.variant_str])

        print(f'\n{message}\n{128 * "‾"}')

    def _print_result_message(self, game_state: dict, lichess_game: Lichess_Game, info: Game_Information) -> None:
        if winner := game_state.get('winner'):
            if winner == 'white':
                message = f'{info.white_name} won'
                loser = info.black_name
                white_result = '1'
                black_result = '0'
            else:
                message = f'{info.black_name} won'
                loser = info.white_name
                white_result = '0'
                black_result = '1'

            match game_state['status']:
                case 'mate':
                    message += ' by checkmate!'
                case 'outoftime':
                    message += f'! {loser} ran out of time.'
                case 'resign':
                    message += f'! {loser} resigned.'
                case 'variantEnd':
                    message += ' by variant rules!'
        else:
            white_result = '½'
            black_result = '½'

            if game_state['status'] == 'draw':
                if lichess_game.board.is_fifty_moves():
                    message = 'Game drawn by 50-move rule.'
                elif lichess_game.board.is_repetition():
                    message = 'Game drawn by threefold repetition.'
                elif lichess_game.board.is_insufficient_material():
                    message = 'Game drawn due to insufficient material.'
                elif lichess_game.board.is_variant_draw():
                    message = 'Game drawn by variant rules.'
                else:
                    message = 'Game drawn by agreement.'
            elif game_state['status'] == 'stalemate':
                message = 'Game drawn by stalemate.'
            else:
                message = 'Game aborted.'

                white_result = 'X'
                black_result = 'X'

        opponents_str = f'{info.white_str} {white_result} - {black_result} {info.black_str}'
        message = (5 * ' ').join([info.id_str, opponents_str, message])

        print(f'{message}\n{128 * "‾"}')
