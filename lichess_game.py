import asyncio
import random
import struct
import time
from collections.abc import Awaitable, Callable, Iterable
from itertools import islice
from typing import Any, Literal

import chess
import chess.engine
import chess.gaviota
import chess.polyglot
import chess.syzygy
from chess.variant import find_variant

from api import API
from botli_dataclasses import (Book_Settings, Game_Information, Gaviota_Result, Lichess_Move, Move_Response,
                               Syzygy_Result)
from config import Config
from configs import Engine_Config, Syzygy_Config
from engine import Engine
from enums import Variant


class Lichess_Game:
    def __init__(self,
                 api: API,
                 config: Config,
                 username: str,
                 game_info: Game_Information,
                 board: chess.Board,
                 syzygy_config: Syzygy_Config,
                 engine_key: str,
                 engine: Engine) -> None:
        self.api = api
        self.config = config
        self.game_info = game_info
        self.board = board
        self.syzygy_config = syzygy_config
        self.white_time: float = self.game_info.state['wtime'] / 1000
        self.black_time: float = self.game_info.state['btime'] / 1000
        self.increment = self.game_info.increment_ms / 1000
        self.is_white = self.game_info.white_name == username
        self.book_settings = self._get_book_settings()
        self.syzygy_tablebase = self._get_syzygy_tablebase()
        self.gaviota_tablebase = self._get_gaviota_tablebase()
        self.move_sources = self._get_move_sources()

        self.opening_explorer_counter = 0
        self.out_of_opening_explorer_counter = 0
        self.cloud_counter = 0
        self.out_of_cloud_counter = 0
        self.chessdb_counter = 0
        self.out_of_chessdb_counter = 0
        self.move_overhead = self._get_move_overhead(config.engines[engine_key])
        self.engine = engine
        self.scores: list[chess.engine.PovScore] = []
        self.last_message = 'No eval available yet.'
        self.last_pv: list[chess.Move] = []

    @classmethod
    async def acreate(cls, api: API, config: Config, username: str, game_info: Game_Information) -> 'Lichess_Game':
        board = cls._get_board(game_info)
        is_white = game_info.white_name == username
        engine_key = cls._get_engine_key(config, board, is_white, game_info)
        syzygy_config = cls._get_syzygy_config(config, board)
        engine = await Engine.from_config(config.engines[engine_key],
                                          syzygy_config,
                                          game_info.black_opponent if is_white else game_info.white_opponent)
        return cls(api, config, username, game_info, board, syzygy_config, engine_key, engine)

    @staticmethod
    def _get_board(game_info: Game_Information) -> chess.Board:
        if game_info.variant == Variant.CHESS960:
            board = chess.Board(game_info.initial_fen, chess960=True)
        elif game_info.variant == Variant.FROM_POSITION:
            board = chess.Board(game_info.initial_fen)
        else:
            VariantBoard = find_variant(game_info.variant_name)
            board = VariantBoard()

        for uci_move in game_info.state['moves'].split():
            board.push_uci(uci_move)

        return board

    @staticmethod
    def _get_engine_key(config: Config, board: chess.Board, is_white: bool, game_info: Game_Information) -> str:
        color = 'white' if is_white else 'black'

        if board.uci_variant == 'chess':
            if board.chess960:
                if f'chess960_{color}' in config.engines:
                    return f'chess960_{color}'

                if 'chess960' in config.engines:
                    return 'chess960'

            else:
                if f'{game_info.speed}_{color}' in config.engines:
                    return f'{game_info.speed}_{color}'

                if game_info.speed in config.engines:
                    return game_info.speed

        else:
            for alias in [alias.lower() for alias in board.aliases]:
                if f'{alias}_{color}' in config.engines:
                    return f'{alias}_{color}'

                if alias in config.engines:
                    return alias

            if f'variants_{color}' in config.engines:
                return f'variants_{color}'

            if 'variants' in config.engines:
                return 'variants'

        if f'standard_{color}' in config.engines:
            return f'standard_{color}'

        if 'standard' in config.engines:
            return 'standard'

        raise RuntimeError(f'No suitable engine for "{board.uci_variant}" configured.')

    @classmethod
    def _get_syzygy_config(cls, config: Config, board: chess.Board) -> Syzygy_Config:
        match board.uci_variant:
            case 'chess':
                return config.syzygy['standard']
            case 'antichess':
                return config.syzygy['antichess']
            case 'atomic':
                return config.syzygy['atomic']
            case _:
                return Syzygy_Config(False, [], 0, False)

    async def make_move(self) -> Lichess_Move:
        for move_source in self.move_sources:
            if move_response := await move_source():
                break
        else:
            move, info = await self.engine.make_move(self.board, *self.engine_times)

            if 'score' in info:
                self.scores.append(info['score'])
            message = f'Engine:  {self._format_move(move):14} {self._format_engine_info(info)}'
            move_response = Move_Response(move, message,
                                          pv=info.get('pv', []),
                                          is_engine_move=len(self.board.move_stack) > 1)

        self.board.push(move_response.move)
        if not move_response.is_engine_move:
            await self.engine.start_pondering(self.board)

        print(f'{move_response.public_message} {move_response.private_message}'.strip())
        self.last_message = move_response.public_message
        self.last_pv = move_response.pv

        return Lichess_Move(move_response.move.uci(), self._offer_draw(move_response), self._resign(move_response))

    def update(self, gameState_event: dict[str, Any]) -> None:
        moves = gameState_event['moves'].split()
        if len(moves) <= len(self.board.move_stack):
            return

        self.board.push(chess.Move.from_uci(moves[-1]))
        self.white_time = gameState_event['wtime'] / 1000
        self.black_time = gameState_event['btime'] / 1000

    @property
    def is_our_turn(self) -> bool:
        return self.is_white == self.board.turn

    @property
    def is_abortable(self) -> bool:
        return len(self.board.move_stack) < 2

    @property
    def own_time(self) -> float:
        return self.white_time if self.is_white else self.black_time

    @property
    def opponent_time(self) -> float:
        return self.black_time if self.is_white else self.white_time

    @property
    def engine_times(self) -> tuple[float, float, float]:
        if self.is_white:
            if self.white_time > self.move_overhead:
                white_time = self.white_time - self.move_overhead
            else:
                white_time = self.white_time / 2.0

            return white_time, self.black_time, self.increment

        if self.black_time > self.move_overhead:
            black_time = self.black_time - self.move_overhead
        else:
            black_time = self.black_time / 2.0

        return self.white_time, black_time, self.increment

    async def start_pondering(self) -> None:
        await self.engine.start_pondering(self.board)

    async def close(self) -> None:
        await self.engine.close()

        for book_reader in self.book_settings.readers.values():
            book_reader.close()

        if self.syzygy_tablebase:
            self.syzygy_tablebase.close()

        if self.gaviota_tablebase:
            self.gaviota_tablebase.close()

    def _offer_draw(self, move_response: Move_Response) -> bool:
        if not self.config.offer_draw.enabled:
            return False

        if not self.engine.opponent.is_engine and not self.config.offer_draw.against_humans:
            return False

        if not self.increment and self.opponent_time < 10.0:
            return False

        if not move_response.is_engine_move:
            return move_response.is_drawish

        if self.board.fullmove_number - (not self.is_white) < self.config.offer_draw.min_game_length:
            return False

        if len(self.scores) < self.config.offer_draw.consecutive_moves:
            return False

        for score in islice(self.scores, len(self.scores) - self.config.offer_draw.consecutive_moves, None):
            if abs(score.relative.score(mate_score=40_000)) > self.config.offer_draw.score:
                return False

        return True

    def _resign(self, move_response: Move_Response) -> bool:
        if not self.config.resign.enabled:
            return False

        if not self.engine.opponent.is_engine and not self.config.resign.against_humans:
            return False

        if not self.increment and self.opponent_time < 10.0:
            return False

        if not move_response.is_engine_move:
            return move_response.is_resignable

        if len(self.scores) < self.config.resign.consecutive_moves:
            return False

        for score in islice(self.scores, len(self.scores) - self.config.resign.consecutive_moves, None):
            if score.relative.score(mate_score=40_000) > self.config.resign.score:
                return False

        return True

    async def _make_book_move(self) -> Move_Response | None:
        if self.book_settings.max_depth and self.board.ply() >= self.book_settings.max_depth:
            return

        for name, book_reader in self.book_settings.readers.items():
            try:
                entries = list(book_reader.find_all(self.board))
            except struct.error:
                print(f'Skipping book "{name}" due to error.')
                continue

            if not entries:
                continue

            match self.book_settings.selection:
                case 'weighted_random':
                    entries.sort(key=lambda entry: random.random() ** (1.0 / entry.weight), reverse=True)
                case 'uniform_random':
                    random.shuffle(entries)
                case 'best_move':
                    entries.sort(key=lambda entry: entry.weight, reverse=True)

            for entry in entries:
                if not self._is_repetition(entry.move):
                    break
            else:
                continue

            weight = entry.weight / sum(entry.weight for entry in entries) * 100.0
            learn = entry.learn if self.config.opening_books.read_learn else 0
            name = name if len(self.book_settings.readers) > 1 else ''
            public_message = f'Book:    {self._format_move(entry.move):14}'
            private_message = f'{self._format_book_info(weight, learn)}     {name}'
            return Move_Response(entry.move, public_message, private_message=private_message)

    def _get_book_settings(self) -> Book_Settings:
        if not self.config.opening_books.enabled:
            return Book_Settings()

        key = self._get_book_key()
        if not key:
            return Book_Settings()

        books_config = self.config.opening_books.books[key]
        return Book_Settings(books_config.selection,
                             books_config.max_depth,
                             {name: chess.polyglot.open_reader(path)
                              for name, path in books_config.names.items()})

    def _get_book_key(self) -> str | None:
        color = 'white' if self.is_white else 'black'

        if self.board.uci_variant != 'chess':
            for alias in [alias.lower() for alias in self.board.aliases]:
                if f'{alias}_{color}' in self.config.opening_books.books:
                    return f'{alias}_{color}'

                if alias in self.config.opening_books.books:
                    return alias

            return

        if self.board.chess960:
            if f'chess960_{color}' in self.config.opening_books.books:
                return f'chess960_{color}'

            if 'chess960' in self.config.opening_books.books:
                return 'chess960'

        else:
            if f'{self.game_info.speed}_{color}' in self.config.opening_books.books:
                return f'{self.game_info.speed}_{color}'

            if self.game_info.speed in self.config.opening_books.books:
                return self.game_info.speed

        if f'standard_{color}' in self.config.opening_books.books:
            return f'standard_{color}'

        if 'standard' in self.config.opening_books.books:
            return 'standard'

        return

    async def _make_opening_explorer_move(self) -> Move_Response | None:
        out_of_book = self.out_of_opening_explorer_counter >= 5
        too_deep = (False
                    if self.config.online_moves.opening_explorer.max_depth is None
                    else self.board.ply() >= self.config.online_moves.opening_explorer.max_depth)
        out_of_range = self.board.fullmove_number > 25
        too_many_moves = (False
                          if self.config.online_moves.opening_explorer.max_moves is None
                          else self.opening_explorer_counter >= self.config.online_moves.opening_explorer.max_moves)
        has_time = self._has_time(self.config.online_moves.opening_explorer.min_time)

        if out_of_book or too_deep or out_of_range or too_many_moves or not has_time:
            return

        if self.config.online_moves.opening_explorer.anti:
            color = 'black' if self.board.turn else 'white'
            username = self.game_info.black_name if self.board.turn else self.game_info.white_name
        else:
            color = 'white' if self.board.turn else 'black'
            username = self.game_info.white_name if self.board.turn else self.game_info.black_name

        speeds = self.game_info.speed if self.game_info.variant == Variant.STANDARD else None
        modes = 'rated' if self.game_info.rated else None

        start_time = time.perf_counter()
        response = await self.api.get_opening_explorer(username,
                                                       self.board.fen(),
                                                       self.game_info.variant,
                                                       color,
                                                       modes,
                                                       speeds,
                                                       self.config.online_moves.opening_explorer.timeout)
        if response is None:
            self.out_of_opening_explorer_counter += 1
            self._reduce_own_time(time.perf_counter() - start_time)
            return

        game_count = response['white'] + response['draws'] + response['black']
        if game_count < max(self.config.online_moves.opening_explorer.min_games, 1):
            self.out_of_opening_explorer_counter += 1
            return

        for move in response['moves']:
            move['wins'] = move['white'] if self.board.turn else move['black']
            move['losses'] = move['black'] if self.board.turn else move['white']

        if self.config.online_moves.opening_explorer.only_with_wins:
            response['moves'] = list(filter(lambda move: move['wins'] > 0, response['moves']))

            if not response['moves']:
                self.out_of_opening_explorer_counter += 1
                return

        self.out_of_opening_explorer_counter = 0
        top_move = self._get_opening_explorer_top_move(response['moves'])
        move = chess.Move.from_uci(top_move['uci'])
        if self._is_repetition(move):
            return

        self.opening_explorer_counter += 1
        public_message = f'Explore: {self._format_move(move):14}'
        private_message = (f'Performance: {top_move["performance"]}      '
                           f'WDL: {top_move["wins"]}/{top_move["draws"]}/{top_move["losses"]}')
        return Move_Response(move, public_message, private_message=private_message)

    def _get_opening_explorer_top_move(self, moves: list[dict[str, Any]]) -> dict[str, Any]:
        if self.config.online_moves.opening_explorer.selection == 'win_rate':
            def win_rate(move: dict[str, Any]) -> float:
                return move['wins'] / (move['white'] + move['draws'] + move['black'])

            def win_performance(move: dict[str, Any]) -> float:
                return (move['wins'] - move['losses']) / (move['white'] + move['draws'] + move['black'])

            moves.sort(key=win_rate, reverse=True)
            return max(moves, key=win_performance)

        if self.config.online_moves.opening_explorer.anti:
            return min(moves, key=lambda move: move['performance'])

        return max(moves, key=lambda move: move['performance'])

    async def _make_cloud_move(self) -> Move_Response | None:
        out_of_book = self.out_of_cloud_counter >= 5
        too_deep = (False
                    if self.config.online_moves.lichess_cloud.max_depth is None
                    else self.board.ply() >= self.config.online_moves.lichess_cloud.max_depth)
        too_many_moves = (False
                          if self.config.online_moves.lichess_cloud.max_moves is None
                          else self.cloud_counter >= self.config.online_moves.lichess_cloud.max_moves)
        has_time = self._has_time(self.config.online_moves.lichess_cloud.min_time)

        if out_of_book or too_deep or too_many_moves or not has_time:
            return

        start_time = time.perf_counter()
        response = await self.api.get_cloud_eval(self.board.fen().replace('[', '/').replace(']', ''),
                                                 self.game_info.variant,
                                                 self.config.online_moves.lichess_cloud.timeout)
        if response is None:
            self.out_of_cloud_counter += 1
            self._reduce_own_time(time.perf_counter() - start_time)
            return

        if 'error' in response:
            self.out_of_cloud_counter += 1
            return

        if response['depth'] < self.config.online_moves.lichess_cloud.min_eval_depth:
            self.out_of_cloud_counter += 1
            return

        self.out_of_cloud_counter = 0
        pv = [chess.Move.from_uci(uci_move) for uci_move in response['pvs'][0]['moves'].split()]
        if self._is_repetition(pv[0]):
            return

        if 'mate' in response['pvs'][0]:
            score = chess.engine.Mate(response['pvs'][0]['mate'])
        else:
            score = chess.engine.Cp(response['pvs'][0]['cp'])

        self.cloud_counter += 1
        message = (f'Cloud:   {self._format_move(pv[0]):14} '
                   f'{self._format_score(chess.engine.PovScore(score, chess.WHITE))}     '
                   f'Depth: {response["depth"]}')
        return Move_Response(pv[0], message, pv=pv)

    async def _make_chessdb_move(self) -> Move_Response | None:
        out_of_book = self.out_of_chessdb_counter >= 5
        too_deep = (False
                    if self.config.online_moves.chessdb.max_depth is None
                    else self.board.ply() >= self.config.online_moves.chessdb.max_depth)
        too_many_moves = (False
                          if self.config.online_moves.chessdb.max_moves is None
                          else self.chessdb_counter >= self.config.online_moves.chessdb.max_moves)
        has_time = self._has_time(self.config.online_moves.chessdb.min_time)
        is_endgame = chess.popcount(self.board.occupied) <= 7

        if out_of_book or too_deep or too_many_moves or not has_time or is_endgame:
            return

        start_time = time.perf_counter()
        response = await self.api.get_chessdb_eval(fen := self.board.fen(), self.config.online_moves.chessdb.timeout)
        if response is None:
            self.out_of_chessdb_counter += 1
            self._reduce_own_time(time.perf_counter() - start_time)
            return

        if response['status'] != 'ok':
            asyncio.create_task(self.api.queue_chessdb(fen))
            self.out_of_chessdb_counter += 1
            return

        self.out_of_chessdb_counter = 0
        if self.config.online_moves.chessdb.selection == 'optimal' or response['moves'][0]['rank'] == 0:
            candidate_moves = [chessdb_move for chessdb_move in response['moves']
                               if chessdb_move['score'] == response['moves'][0]['score']]
        elif self.config.online_moves.chessdb.selection == 'best':
            candidate_moves = [chessdb_move for chessdb_move in response['moves']
                               if chessdb_move['rank'] == response['moves'][0]['rank']]
        else:
            candidate_moves = [chessdb_move for chessdb_move in response['moves']
                               if chessdb_move['rank'] > 0]

        if len(candidate_moves) < self.config.online_moves.chessdb.min_candidates:
            return

        random.shuffle(candidate_moves)
        for chessdb_move in candidate_moves:
            move = chess.Move.from_uci(chessdb_move['uci'])
            if not self._is_repetition(move):
                break
        else:
            return

        self.chessdb_counter += 1
        pov_score = chess.engine.PovScore(chess.engine.Cp(chessdb_move['score']), self.board.turn)
        candidates = (f'Candidates: {", ".join(chessdb_move["san"] for chessdb_move in candidate_moves)}'
                      if len(candidate_moves) > 1 else '')
        message = f'ChessDB: {self._format_move(move):14} {self._format_score(pov_score)}     {candidates}'
        return Move_Response(move, message)

    def _probe_gaviota(self, moves: Iterable[chess.Move]) -> Gaviota_Result:
        assert self.gaviota_tablebase

        best_move = chess.Move.null()
        best_wdl = -2
        best_dtm = 1_000_000
        board_copy = self.board.copy(stack=False)
        for move in moves:
            board_copy.push(move)

            if board_copy.is_checkmate():
                return Gaviota_Result(move, 2, 0)

            dtm = -self.gaviota_tablebase.probe_dtm(board_copy)
            wdl = self._value_to_wdl(dtm, board_copy.halfmove_clock)

            if best_move:
                if wdl > best_wdl:
                    best_move = move
                    best_wdl = wdl
                    best_dtm = dtm
                elif wdl == best_wdl and dtm < best_dtm:
                    best_move = move
                    best_dtm = dtm
            else:
                best_move = move
                best_wdl = wdl
                best_dtm = dtm

            board_copy.pop()

        return Gaviota_Result(best_move, best_wdl, best_dtm)

    async def _make_gaviota_move(self) -> Move_Response | None:
        match chess.popcount(self.board.occupied):
            case pieces if pieces > self.config.gaviota.max_pieces + 1:
                return
            case pieces if pieces == self.config.gaviota.max_pieces + 1:
                if self._has_mate_score():
                    return

                try:
                    result = self._probe_gaviota(self.board.generate_legal_captures())
                except KeyError:
                    return

                if result.wdl < 2:
                    return
            case _:
                try:
                    result = self._probe_gaviota(self.board.generate_legal_moves())
                except KeyError:
                    return

        match result.wdl:
            case 2:
                egtb_info = self._format_egtb_info('win', dtm=result.dtm)
                offer_draw = False
                resign = False
            case 0:
                egtb_info = self._format_egtb_info('draw', dtm=0)
                offer_draw = True
                resign = False
            case -2:
                egtb_info = self._format_egtb_info('loss', dtm=result.dtm)
                offer_draw = False
                resign = True
            case _:
                return

        await self.engine.stop_pondering(self.board)
        message = f'Gaviota: {self._format_move(result.move):14} {egtb_info}'
        return Move_Response(result.move, message, is_drawish=offer_draw, is_resignable=resign)

    def _probe_syzygy(self, moves: Iterable[chess.Move]) -> Syzygy_Result:
        assert self.syzygy_tablebase

        best_move = chess.Move.null()
        best_wdl = -2
        best_dtz = 1_000_000
        best_real_dtz = 0
        board_copy = self.board.copy(stack=False)
        for move in moves:
            board_copy.push(move)

            dtz = -self.syzygy_tablebase.probe_dtz(board_copy)
            wdl = self._value_to_wdl(dtz, board_copy.halfmove_clock)

            real_dtz = dtz
            if board_copy.halfmove_clock == 0:
                if wdl < 0:
                    dtz += 10_000
                elif wdl > 0:
                    dtz -= 10_000

            if best_move:
                if wdl > best_wdl:
                    best_move = move
                    best_wdl = wdl
                    best_dtz = dtz
                    best_real_dtz = real_dtz
                elif wdl == best_wdl and dtz < best_dtz:
                    best_move = move
                    best_dtz = dtz
                    best_real_dtz = real_dtz
            else:
                best_move = move
                best_wdl = wdl
                best_dtz = dtz
                best_real_dtz = real_dtz

            board_copy.pop()

        return Syzygy_Result(best_move, best_wdl, best_real_dtz)

    async def _make_syzygy_move(self) -> Move_Response | None:
        match chess.popcount(self.board.occupied):
            case pieces if pieces > self.syzygy_config.max_pieces + 1 or self._has_mate_score():
                return
            case pieces if pieces == self.syzygy_config.max_pieces + 1:
                try:
                    result = self._probe_syzygy(self.board.generate_legal_captures())
                except KeyError:
                    return

                if result.wdl < 2:
                    return
            case _:
                try:
                    result = self._probe_syzygy(self.board.generate_legal_moves())
                except KeyError:
                    return

        match result.wdl:
            case 2:
                egtb_info = self._format_egtb_info('win', dtz=result.dtz)
                offer_draw = False
                resign = False
            case 1:
                egtb_info = self._format_egtb_info('cursed win', dtz=result.dtz)
                offer_draw = False
                resign = False
            case 0:
                egtb_info = self._format_egtb_info('draw', dtz=0)
                offer_draw = True
                resign = False
            case -1:
                egtb_info = self._format_egtb_info('blessed loss', dtz=result.dtz)
                offer_draw = True
                resign = False
            case -2:
                egtb_info = self._format_egtb_info('loss', dtz=result.dtz)
                offer_draw = False
                resign = True

        await self.engine.stop_pondering(self.board)
        message = f'Syzygy:  {self._format_move(result.move):14} {egtb_info}'
        return Move_Response(result.move, message, is_drawish=offer_draw, is_resignable=resign)

    def _value_to_wdl(self, value: int, halfmove_clock: int) -> Literal[-2, -1, 0, 1, 2]:
        if value > 0:
            if value + halfmove_clock <= 100:
                return 2

            return 1

        if value < 0:
            if value - halfmove_clock >= -100:
                return -2

            return -1

        return 0

    def _get_syzygy_tablebase(self) -> chess.syzygy.Tablebase | None:
        if not (self.syzygy_config.enabled and self.syzygy_config.instant_play):
            return

        tablebase = chess.syzygy.open_tablebase(self.syzygy_config.paths[0], VariantBoard=type(self.board))

        for path in self.syzygy_config.paths[1:]:
            tablebase.add_directory(path)

        return tablebase

    def _get_gaviota_tablebase(self) -> chess.gaviota.PythonTablebase | chess.gaviota.NativeTablebase | None:
        if not self.config.gaviota.enabled:
            return

        tablebase = chess.gaviota.open_tablebase(self.config.gaviota.paths[0])

        for path in self.config.gaviota.paths[1:]:
            tablebase.add_directory(path)

        return tablebase

    async def _make_egtb_move(self) -> Move_Response | None:
        max_pieces = 7 if self.board.uci_variant == 'chess' else 6
        match chess.popcount(self.board.occupied):
            case pieces if pieces > max_pieces + 1:
                return
            case pieces if pieces == max_pieces + 1:
                if not any(self.board.generate_legal_captures()):
                    return

        if not self._has_time(self.config.online_moves.online_egtb.min_time) or self._has_mate_score():
            return

        variant = 'standard' if self.board.uci_variant == 'chess' else self.board.uci_variant
        assert variant

        start_time = time.perf_counter()
        response = await self.api.get_egtb(self.board.fen(), variant, self.config.online_moves.online_egtb.timeout)
        if response is None:
            self._reduce_own_time(time.perf_counter() - start_time)
            return

        outcome: str = response['category']
        if outcome == 'unknown':
            return

        uci_move: str = response['moves'][0]['uci']
        dtz: int = response['dtz']
        dtm: int | None = response['dtm']
        offer_draw = outcome in ['draw', 'blessed loss']
        resign = outcome == 'loss'
        move = chess.Move.from_uci(uci_move)
        message = f'EGTB:    {self._format_move(move):14} {self._format_egtb_info(outcome, dtz, dtm)}'
        return Move_Response(move, message, is_drawish=offer_draw, is_resignable=resign)

    def _format_move(self, move: chess.Move) -> str:
        if self.board.turn:
            move_number = f'{self.board.fullmove_number}.'
            return f'{move_number:4} {self.board.san(move)}'

        move_number = f'{self.board.fullmove_number}...'
        return f'{move_number:6} {self.board.san(move)}'

    def _format_engine_info(self, info: chess.engine.InfoDict) -> str:
        info_score = info.get('score')
        score = f'{self._format_score(info_score):7}' if info_score else 7 * ' '

        info_depth = info.get('depth')
        info_seldepth = info.get('seldepth')
        depth_str = f'{info_depth}/{info_seldepth}'
        depth = f'{depth_str:6}' if info_depth and info_seldepth else 6 * ' '

        info_nodes = info.get('nodes')
        nodes = f'Nodes: {self._format_number(info_nodes)}' if info_nodes else 14 * ' '

        info_nps = info.get('nps')
        nps = f'NPS: {self._format_number(info_nps)}' if info_nps else 12 * ' '

        if info_time := info.get('time'):
            minutes, seconds = divmod(info_time, 60)
            time_str = f'MT: {minutes:02.0f}:{seconds:004.1f}'
        else:
            time_str = 11 * ' '

        info_hashfull = info.get('hashfull')
        hashfull = 13 * ' ' if info_hashfull is None else f'Hash: {info_hashfull / 10:5.1f} %'

        info_tbhits = info.get('tbhits')
        tbhits = f'TB: {self._format_number(info_tbhits)}' if info_tbhits else ''
        delimiter = 5 * ' '

        return delimiter.join((score, depth, nodes, nps, time_str, hashfull, tbhits))

    def _format_number(self, number: int) -> str:
        if number >= 1_000_000_000_000:
            return f'{number / 1_000_000_000_000:5.1f} T'

        if number >= 1_000_000_000:
            return f'{number / 1_000_000_000:5.1f} G'

        if number >= 1_000_000:
            return f'{number / 1_000_000:5.1f} M'

        if number >= 1_000:
            return f'{number / 1_000:5.1f} k'

        return f'{number:5}  '

    def _format_score(self, score: chess.engine.PovScore) -> str:
        if not score.is_mate():
            if cp_score := score.pov(self.board.turn).score():
                cp_score /= 100
                return format(cp_score, '+7.2f')

            return '   0.00'

        return str(score.pov(self.board.turn))

    def _format_egtb_info(self, outcome: str, dtz: int | None = None, dtm: int | None = None) -> str:
        outcome_str = f'{outcome:>7}'
        dtz_str = f'DTZ: {dtz}' if dtz else ''
        dtm_str = f'DTM: {dtm}' if dtm else ''
        delimiter = 5 * ' '

        return delimiter.join(filter(None, [outcome_str, dtz_str, dtm_str]))

    def _format_book_info(self, weight: float, learn: int) -> str:
        output = f'{weight:>5.0f} %'
        if learn:
            output += f'     Performance: {learn >> 20}'
            win = (learn >> 10 & 0b1111111111) / 10.2
            draw = (learn & 0b1111111111) / 10.2
            loss = max(100.0 - win - draw, 0.0)
            output += f'     WDL: {win:5.1f} % {draw:5.1f} % {loss:5.1f} %'

        return output

    def _get_move_sources(self) -> list[Callable[[], Awaitable[Move_Response | None]]]:
        move_sources: list[Callable[[], Awaitable[Move_Response | None]]] = []

        if self.config.gaviota.enabled:
            if self.board.uci_variant == 'chess':
                move_sources.append(self._make_gaviota_move)

        if self.syzygy_config.enabled and self.syzygy_config.instant_play:
            move_sources.append(self._make_syzygy_move)

        if self.config.online_moves.online_egtb.enabled:
            if self.board.uci_variant in ['chess', 'antichess', 'atomic']:
                move_sources.append(self._make_egtb_move)

        opening_sources: dict[Callable[[], Awaitable[Move_Response | None]], int] = {}

        if self.config.opening_books.enabled:
            opening_sources[self._make_book_move] = self.config.opening_books.priority

        opening_explorer_config = self.config.online_moves.opening_explorer
        if opening_explorer_config.enabled:
            if not opening_explorer_config.only_without_book or not self.book_settings.readers:
                if self.board.uci_variant == 'chess' or opening_explorer_config.use_for_variants:
                    opening_sources[self._make_opening_explorer_move] = opening_explorer_config.priority

        if self.config.online_moves.lichess_cloud.enabled:
            if not self.config.online_moves.lichess_cloud.only_without_book or not self.book_settings.readers:
                opening_sources[self._make_cloud_move] = self.config.online_moves.lichess_cloud.priority

        if self.config.online_moves.chessdb.enabled:
            if not self.config.online_moves.chessdb.only_without_book or not self.book_settings.readers:
                if self.board.uci_variant == 'chess':
                    opening_sources[self._make_chessdb_move] = self.config.online_moves.chessdb.priority

        move_sources += [opening_source
                         for opening_source, _
                         in sorted(opening_sources.items(), key=lambda item: item[1], reverse=True)]

        return move_sources

    def _get_move_overhead(self, engine_config: Engine_Config) -> float:
        return max(self.game_info.initial_time_ms / 60_000 * engine_config.move_overhead_multiplier, 1.0)

    def _has_time(self, min_time: float) -> bool:
        if len(self.board.move_stack) < 2:
            return True

        if not self.increment:
            min_time += 10.0

        return self.own_time >= min_time

    def _reduce_own_time(self, seconds: float) -> None:
        if len(self.board.move_stack) < 2:
            return

        if self.is_white:
            self.white_time -= seconds
        else:
            self.black_time -= seconds

    def _is_repetition(self, move: chess.Move) -> bool:
        board = self.board.copy()
        board.push(move)
        return board.is_repetition(count=2)

    def _has_mate_score(self) -> bool:
        if not self.scores:
            return False

        mate = self.scores[-1].relative.mate()
        return mate is not None and mate > 0
