import os
import random
import subprocess
from collections import deque
from typing import Callable

import chess
import chess.engine
import chess.gaviota
import chess.polyglot
import chess.syzygy
from chess.variant import find_variant

from aliases import DTM, DTZ, Message, Offer_Draw, Outcome, Performance, Resign, UCI_Move
from api import API
from botli_dataclasses import Game_Information
from enums import Game_Status, Variant


class Lichess_Game:
    def __init__(self, api: API, game_information: Game_Information, config: dict) -> None:
        self.config = config
        self.api = api
        self.game_info = game_information
        self.board = self._setup_board()
        self.white_time_ms = game_information.state['wtime']
        self.black_time_ms = game_information.state['btime']
        self.status = Game_Status(game_information.state['status'])
        self.draw_enabled: bool = config['engine']['offer_draw']['enabled']
        self.resign_enabled: bool = config['engine']['resign']['enabled']
        self.ponder_enabled: bool = True
        self.move_sources = self._get_move_sources()
        self.move_overhead_ms = self._get_move_overhead()
        self.book_readers = self._get_book_readers()
        self.syzygy_tablebase = self._get_syzygy_tablebase()
        self.gaviota_tablebase = self._get_gaviota_tablebase()
        self.out_of_book_counter = 0
        self.opening_explorer_counter = 0
        self.out_of_opening_explorer_counter = 0
        self.cloud_counter = 0
        self.out_of_cloud_counter = 0
        self.chessdb_counter = 0
        self.out_of_chessdb_counter = 0
        self.engine = self._get_engine()
        consecutive_draw_moves = config['engine']['offer_draw']['consecutive_moves']
        self.draw_scores: deque[chess.engine.PovScore] = deque(maxlen=consecutive_draw_moves)
        consecutive_resign_moves = config['engine']['resign']['consecutive_moves']
        self.resign_scores: deque[chess.engine.PovScore] = deque(maxlen=consecutive_resign_moves)
        self.last_message = 'No eval available yet.'

    def make_move(self) -> tuple[UCI_Move, Offer_Draw, Resign]:
        for move_source in self.move_sources:
            if response := move_source():
                move, message, offer_draw, resign = response
                engine_move = False
                break
        else:
            move, info = self._make_engine_move()
            message = f'Engine:  {self._format_move(move):14} {self._format_engine_info(info)}'
            offer_draw = self._is_drawish()
            resign = self._is_resignable()
            engine_move = len(self.board.move_stack) > 1

        print(message)
        self.last_message = message
        self.board.push(move)
        if not engine_move:
            self.start_pondering()
        return move.uci(), offer_draw and self.draw_enabled, resign and self.resign_enabled

    def update(self, gameState_event: dict) -> bool:
        self.status = Game_Status(gameState_event['status'])

        moves = gameState_event['moves'].split()
        if len(moves) <= len(self.board.move_stack):
            return False

        self.board.push(chess.Move.from_uci(moves[-1]))
        self.white_time_ms = gameState_event['wtime']
        self.black_time_ms = gameState_event['btime']

        return True

    @property
    def is_our_turn(self) -> bool:
        return self.game_info.is_white == self.board.turn

    @property
    def is_game_over(self) -> bool:
        return self.board.is_checkmate() or \
            self.board.is_stalemate() or \
            self.board.is_insufficient_material() or \
            self.board.is_fifty_moves() or \
            self.board.is_repetition()

    @property
    def is_abortable(self) -> bool:
        return len(self.board.move_stack) < 2

    @property
    def is_finished(self) -> bool:
        return self.status != Game_Status.STARTED

    def start_pondering(self) -> None:
        if self.ponder_enabled:
            self.engine.analysis(self.board)

    def stop_pondering(self) -> None:
        if self.ponder_enabled:
            self.ponder_enabled = False
            self.engine.analysis(self.board, chess.engine.Limit(time=0.001))

    def end_game(self) -> None:
        try:
            self.engine.quit()
        except TimeoutError:
            print('Enginge could not be terminated cleanly.')

        self.engine.close()

        for book_reader in self.book_readers:
            book_reader.close()

        if self.syzygy_tablebase:
            self.syzygy_tablebase.close()

        if self.gaviota_tablebase:
            self.gaviota_tablebase.close()

    def _is_drawish(self) -> bool:
        if not self.draw_enabled:
            return False

        too_shallow = self.board.fullmove_number < self.config['engine']['offer_draw']['min_game_length']
        too_few_scores = len(self.draw_scores) < self.config['engine']['offer_draw']['consecutive_moves']

        if too_shallow or too_few_scores:
            return False

        max_score = self.config['engine']['offer_draw']['score']

        for score in self.draw_scores:
            if abs(score.relative.score(mate_score=40000)) > max_score:
                return False

        return True

    def _is_resignable(self) -> bool:
        if not self.resign_enabled:
            return False

        if len(self.resign_scores) < self.config['engine']['resign']['consecutive_moves']:
            return False

        max_score = self.config['engine']['resign']['score']

        for score in self.resign_scores:
            if score.relative.score(mate_score=40000) > max_score:
                return False

        return True

    def _make_book_move(self) -> tuple[chess.Move, Message, Offer_Draw, Resign] | None:
        out_of_book = self.out_of_book_counter >= 10
        max_depth = self.config['engine']['opening_books'].get('max_depth', float('inf'))
        too_deep = self.board.ply() >= max_depth

        if out_of_book or too_deep:
            return

        read_learn = self.config['engine']['opening_books'].get('read_learn')
        selection = self.config['engine']['opening_books']['selection']
        for book_reader in self.book_readers:
            entries = list(book_reader.find_all(self.board))
            if entries:
                if selection == 'weighted_random':
                    entry, = random.choices(entries, [entry.weight for entry in entries], k=1)
                elif selection == 'uniform_random':
                    entry = random.choice(entries)
                else:
                    entry = max(entries, key=lambda entry: entry.weight)

                if not self._is_repetition(entry.move):
                    self.out_of_book_counter = 0
                    weight = entry.weight / sum(entry.weight for entry in entries) * 100.0
                    learn = entry.learn if read_learn else 0
                    message = f'Book:    {self._format_move(entry.move):14} {self._format_book_info(weight, learn)}'
                    return entry.move, message, False, False

        self.out_of_book_counter += 1

    def _get_book_readers(self) -> list[chess.polyglot.MemoryMappedReader]:
        enabled = self.config['engine']['opening_books']['enabled']

        if not enabled:
            return []

        books: dict[str, list[str]] = self.config['engine']['opening_books']['books']

        if self.board.chess960 and 'chess960' in books:
            return [chess.polyglot.open_reader(book) for book in books['chess960']]
        elif self.board.uci_variant == 'chess':
            if self.game_info.is_white and 'white' in books:
                return [chess.polyglot.open_reader(book) for book in books['white']]
            elif not self.game_info.is_white and 'black' in books:
                return [chess.polyglot.open_reader(book) for book in books['black']]

            return [chess.polyglot.open_reader(book) for book in books['standard']] if 'standard' in books else []
        else:
            for key in books:
                if key.lower() in [alias.lower() for alias in self.board.aliases]:
                    return [chess.polyglot.open_reader(book) for book in books[key]]

            return []

    def _make_opening_explorer_move(self) -> tuple[chess.Move, Message, Offer_Draw, Resign] | None:
        out_of_book = self.out_of_opening_explorer_counter >= 5
        max_depth = self.config['engine']['online_moves']['opening_explorer'].get('max_depth', float('inf'))
        too_deep = self.board.ply() >= max_depth
        max_moves = self.config['engine']['online_moves']['opening_explorer'].get('max_moves', float('inf'))
        too_many_moves = self.opening_explorer_counter >= max_moves
        has_time = self._has_time(self.config['engine']['online_moves']['opening_explorer']['min_time'])
        is_variant = self.board.uci_variant != 'chess'
        use_for_variants = self.config['engine']['online_moves']['opening_explorer']['use_for_variants']
        forbidden_variant = is_variant and not use_for_variants

        if out_of_book or too_deep or too_many_moves or not has_time or forbidden_variant:
            return

        timeout = self.config['engine']['online_moves']['opening_explorer']['timeout']
        min_games = max(self.config['engine']['online_moves']['opening_explorer']['min_games'], 1)
        only_with_wins = self.config['engine']['online_moves']['opening_explorer']['only_with_wins']
        anti = self.config['engine']['online_moves']['opening_explorer']['anti']

        if anti:
            color = 'black' if self.board.turn else 'white'
            username = self.game_info.black_name if self.board.turn else self.game_info.white_name
        else:
            color = 'white' if self.board.turn else 'black'
            username = self.game_info.white_name if self.board.turn else self.game_info.black_name

        if response := self.api.get_opening_explorer(username, self.board.fen(), self.game_info.variant, color, timeout):
            game_count = response['white'] + response['draws'] + response['black']
            if game_count >= min_games:
                top_move = self._get_opening_explorer_top_move(response['moves'])
                missing_win = only_with_wins and not bool(top_move['wins'])
                if not missing_win:
                    self.out_of_opening_explorer_counter = 0
                    move = chess.Move.from_uci(top_move['uci'])
                    if not self._is_repetition(move):
                        self.opening_explorer_counter += 1
                        message = f'Explore: {self._format_move(move):14} Performance: {top_move["performance"]}' \
                                  f'      WDL: {top_move["wins"]}/{top_move["draws"]}/{top_move["losses"]}'
                        return move, message, False, False

            self.out_of_opening_explorer_counter += 1
        else:
            self._reduce_own_time(timeout * 1000)

    def _get_opening_explorer_top_move(self, moves: list[dict]) -> dict:
        selection = self.config['engine']['online_moves']['opening_explorer']['selection']
        anti = self.config['engine']['online_moves']['opening_explorer']['anti']

        if selection == 'win_rate':
            for move in moves:
                move['wins'] = move['white'] if self.board.turn else move['black']
                move['losses'] = move['black'] if self.board.turn else move['white']

            return max(moves, key=lambda move: (move['wins'] - move['losses']) / (move['white'] + move['draws'] + move['black']))
        else:
            min_or_max = min if anti else max
            top_move = min_or_max(moves, key=lambda move: move['performance'])
            top_move['wins'] = top_move['white'] if self.board.turn else top_move['black']
            top_move['losses'] = top_move['black'] if self.board.turn else top_move['white']
            return top_move

    def _make_cloud_move(self) -> tuple[chess.Move, Message, Offer_Draw, Resign] | None:
        out_of_book = self.out_of_cloud_counter >= 5
        max_depth = self.config['engine']['online_moves']['lichess_cloud'].get('max_depth', float('inf'))
        too_deep = self.board.ply() >= max_depth
        max_moves = self.config['engine']['online_moves']['lichess_cloud'].get('max_moves', float('inf'))
        too_many_moves = self.cloud_counter >= max_moves
        has_time = self._has_time(self.config['engine']['online_moves']['lichess_cloud']['min_time'])
        only_without_book = self.config['engine']['online_moves']['lichess_cloud'].get('only_without_book', False)
        blocking_book = only_without_book and bool(self.book_readers)

        if out_of_book or too_deep or too_many_moves or not has_time or blocking_book:
            return

        timeout = self.config['engine']['online_moves']['lichess_cloud']['timeout']
        min_eval_depth = self.config['engine']['online_moves']['lichess_cloud']['min_eval_depth']

        if response := self.api.get_cloud_eval(
                self.board.fen().replace('[', '/').replace(']', ''),
                self.game_info.variant, timeout):
            if 'error' not in response:
                if response['depth'] >= min_eval_depth:
                    self.out_of_cloud_counter = 0
                    move = chess.Move.from_uci(response['pvs'][0]['moves'].split()[0])
                    if not self._is_repetition(move):
                        self.cloud_counter += 1
                        pov_score = chess.engine.PovScore(chess.engine.Cp(response['pvs'][0]['cp']), chess.WHITE)
                        message = f'Cloud:   {self._format_move(move):14} {self._format_score(pov_score)}     Depth: {response["depth"]}'
                        return move, message, False, False

            self.out_of_cloud_counter += 1
        else:
            self._reduce_own_time(timeout * 1000)

    def _make_chessdb_move(self) -> tuple[chess.Move, Message, Offer_Draw, Resign] | None:
        out_of_book = self.out_of_chessdb_counter >= 5
        max_depth = self.config['engine']['online_moves']['chessdb'].get('max_depth', float('inf'))
        too_deep = self.board.ply() >= max_depth
        max_moves = self.config['engine']['online_moves']['chessdb'].get('max_moves', float('inf'))
        too_many_moves = self.chessdb_counter >= max_moves
        has_time = self._has_time(self.config['engine']['online_moves']['chessdb']['min_time'])
        incompatible_variant = self.board.uci_variant != 'chess'
        is_endgame = chess.popcount(self.board.occupied) <= 7

        if out_of_book or too_deep or too_many_moves or not has_time or incompatible_variant or is_endgame:
            return

        timeout = self.config['engine']['online_moves']['chessdb']['timeout']
        min_eval_depth = self.config['engine']['online_moves']['chessdb']['min_eval_depth']

        if response := self.api.get_chessdb_eval(self.board.fen(), timeout):
            if response['status'] == 'ok':
                if response['depth'] >= min_eval_depth:
                    self.out_of_chessdb_counter = 0
                    move = chess.Move.from_uci(response['pv'][0])
                    if not self._is_repetition(move):
                        self.chessdb_counter += 1
                        pov_score = chess.engine.PovScore(chess.engine.Cp(response['score']), self.board.turn)
                        message = f'ChessDB: {self._format_move(move):14} {self._format_score(pov_score)}     Depth: {response["depth"]}'
                        return move, message, False, False

            self.out_of_chessdb_counter += 1
        else:
            self._reduce_own_time(timeout * 1000)

    def _make_gaviota_move(self) -> tuple[chess.Move, Message, Offer_Draw, Resign] | None:
        assert self.gaviota_tablebase
        is_endgame = chess.popcount(self.board.occupied) <= self.config['engine']['gaviota']['max_pieces']
        incompatible_variant = self.board.uci_variant != 'chess'

        if not is_endgame or incompatible_variant:
            return

        best_moves: list[chess.Move] = []
        best_wdl = -2
        best_dtm = 1_000_000
        for move in self.board.legal_moves:
            board_copy = self.board.copy(stack=False)
            board_copy.push(move)

            if board_copy.is_checkmate():
                wdl = 2
                dtm = 0
            else:
                try:
                    dtm = -self.gaviota_tablebase.probe_dtm(board_copy)
                    wdl = self._value_to_wdl(dtm, board_copy.halfmove_clock)
                except chess.gaviota.MissingTableError:
                    return

            if wdl == 0:
                if board_copy.is_check():
                    dtm -= 1

                if board_copy.halfmove_clock == 0:
                    dtm -= 2

            if best_moves:
                if wdl > best_wdl:
                    best_moves = [move]
                    best_wdl = wdl
                    best_dtm = dtm
                elif wdl == best_wdl:
                    if dtm < best_dtm:
                        best_moves = [move]
                        best_dtm = dtm
                    elif dtm == best_dtm:
                        best_moves.append(move)
            else:
                best_moves.append(move)
                best_wdl = wdl
                best_dtm = dtm

        if best_wdl == 2:
            move = random.choice(best_moves)
            egtb_info = self._format_egtb_info('win', dtm=best_dtm)
            offer_draw = False
            resign = False
        elif best_wdl == 0:
            move = best_moves[0]
            egtb_info = self._format_egtb_info('draw', dtm=0)
            offer_draw = True
            resign = False
        elif best_wdl == -2:
            move = random.choice(best_moves)
            egtb_info = self._format_egtb_info('loss', dtm=best_dtm)
            offer_draw = False
            resign = True
        else:
            return

        self.stop_pondering()
        return move, f'Gaviota: {self._format_move(move):14} {egtb_info}', offer_draw, resign

    def _make_syzygy_move(self) -> tuple[chess.Move, Message, Offer_Draw, Resign] | None:
        assert self.syzygy_tablebase
        is_endgame = chess.popcount(self.board.occupied) <= self.config['engine']['syzygy']['max_pieces']
        incompatible_variant = self.board.uci_variant not in ['chess', 'antichess', 'atomic']

        if not is_endgame or incompatible_variant:
            return

        best_moves: list[chess.Move] = []
        best_wdl = -2
        best_dtz = 1_000_000
        best_real_dtz = best_dtz
        for move in self.board.legal_moves:
            board_copy = self.board.copy(stack=False)
            board_copy.push(move)

            try:
                dtz = -self.syzygy_tablebase.probe_dtz(board_copy)
            except chess.syzygy.MissingTableError:
                return

            wdl = self._value_to_wdl(dtz, board_copy.halfmove_clock)

            real_dtz = dtz
            if board_copy.halfmove_clock == 0:
                if wdl < 0:
                    dtz += 10_000
                elif wdl > 0:
                    dtz -= 10_000

            if wdl == 0:
                if board_copy.is_check():
                    dtz -= 1

                if board_copy.halfmove_clock == 0:
                    dtz -= 2

            if best_moves:
                if wdl > best_wdl:
                    best_moves = [move]
                    best_wdl = wdl
                    best_dtz = dtz
                    best_real_dtz = real_dtz
                elif wdl == best_wdl:
                    if dtz < best_dtz:
                        best_moves = [move]
                        best_dtz = dtz
                        best_real_dtz = real_dtz
                    elif dtz == best_dtz:
                        best_moves.append(move)
            else:
                best_moves.append(move)
                best_wdl = wdl
                best_dtz = dtz
                best_real_dtz = real_dtz

        if best_wdl == 2:
            move = random.choice(best_moves)
            egtb_info = self._format_egtb_info('win', dtz=best_real_dtz)
            offer_draw = False
            resign = False
        elif best_wdl == 1:
            move = random.choice(best_moves)
            egtb_info = self._format_egtb_info('cursed win', dtz=best_real_dtz)
            offer_draw = False
            resign = False
        elif best_wdl == 0:
            move = best_moves[0]
            egtb_info = self._format_egtb_info('draw', dtz=best_real_dtz)
            offer_draw = True
            resign = False
        elif best_wdl == -1:
            move = best_moves[0]
            egtb_info = self._format_egtb_info('blessed loss', dtz=best_real_dtz)
            offer_draw = True
            resign = False
        else:
            move = random.choice(best_moves)
            egtb_info = self._format_egtb_info('loss', dtz=best_real_dtz)
            offer_draw = False
            resign = True

        self.stop_pondering()
        return move, f'Syzygy:  {self._format_move(move):14} {egtb_info}', offer_draw, resign

    def _value_to_wdl(self, value: int, halfmove_clock: int) -> int:
        if value > 0:
            if value + halfmove_clock <= 100:
                return 2
            else:
                return 1
        elif value < 0:
            if value - halfmove_clock >= -100:
                return -2
            else:
                return -1
        else:
            return 0

    def _get_syzygy_tablebase(self) -> chess.syzygy.Tablebase | None:
        enabled = self.config['engine']['syzygy']['enabled'] and self.config['engine']['syzygy']['instant_play']

        if not enabled:
            return

        paths = self.config['engine']['syzygy']['paths']
        tablebase = chess.syzygy.open_tablebase(paths[0], VariantBoard=type(self.board))

        for path in paths[1:]:
            tablebase.add_directory(path)

        return tablebase

    def _get_gaviota_tablebase(self) -> chess.gaviota.PythonTablebase | chess.gaviota.NativeTablebase | None:
        enabled = self.config['engine']['gaviota']['enabled']

        if not enabled:
            return

        paths = self.config['engine']['gaviota']['paths']
        tablebase = chess.gaviota.open_tablebase(paths[0])

        for path in paths[1:]:
            tablebase.add_directory(path)

        return tablebase

    def _make_egtb_move(self) -> tuple[chess.Move, Message, Offer_Draw, Resign] | None:
        max_pieces = 7 if self.board.uci_variant == 'chess' else 6
        is_endgame = chess.popcount(self.board.occupied) <= max_pieces
        has_time = self._has_time(self.config['engine']['online_moves']['online_egtb']['min_time'])
        incompatible_variant = self.board.uci_variant not in ['chess', 'antichess', 'atomic']

        if not is_endgame or not has_time or incompatible_variant:
            return

        timeout = self.config['engine']['online_moves']['online_egtb']['timeout']
        variant = 'standard' if self.board.uci_variant == 'chess' else self.board.uci_variant
        assert variant

        if response := self.api.get_egtb(self.board.fen(), variant, timeout):
            uci_move: str = response['moves'][0]['uci']
            outcome: str = response['category']
            dtz: int = -response['moves'][0]['dtz']
            dtm: int | None = response['dtm']
            offer_draw = outcome in ['draw', 'blessed loss']
            resign = outcome == 'loss'
            move = chess.Move.from_uci(uci_move)
            message = f'EGTB:    {self._format_move(move):14} {self._format_egtb_info(outcome, dtz, dtm)}'
            return move, message, offer_draw, resign
        else:
            self._reduce_own_time(timeout * 1000)

    def _make_engine_move(self) -> tuple[chess.Move, chess.engine.InfoDict]:
        if len(self.board.move_stack) < 2:
            limit = chess.engine.Limit(time=15)
            ponder = False
        else:
            if self.game_info.is_white:
                white_time = self.white_time_ms - self.move_overhead_ms if self.white_time_ms > self.move_overhead_ms else self.white_time_ms / 2
                white_time /= 1000
                black_time = self.black_time_ms / 1000
            else:
                black_time = self.black_time_ms - self.move_overhead_ms if self.black_time_ms > self.move_overhead_ms else self.black_time_ms / 2
                black_time /= 1000
                white_time = self.white_time_ms / 1000
            increment = self.game_info.increment_ms / 1000

            limit = chess.engine.Limit(white_clock=white_time, white_inc=increment,
                                       black_clock=black_time, black_inc=increment)
            ponder = self.ponder_enabled

        result = self.engine.play(self.board, limit, info=chess.engine.INFO_ALL, ponder=ponder)
        if result.move:
            score = result.info.get('score', chess.engine.PovScore(chess.engine.Mate(1), self.board.turn))
            self.draw_scores.append(score)
            self.resign_scores.append(score)
            return result.move, result.info
        raise RuntimeError('Engine could not make a move!')

    def _format_move(self, move: chess.Move) -> str:
        if self.board.turn:
            move_number = str(self.board.fullmove_number) + '.'
            return f'{move_number:4} {self.board.san(move)}'
        else:
            move_number = str(self.board.fullmove_number) + '...'
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
            time = f'MT: {minutes:02.0f}:{seconds:004.1f}'
        else:
            time = 11 * ' '

        info_hashfull = info.get('hashfull')
        hashfull = f'Hash: {info_hashfull/10:5.1f} %' if info_hashfull else 13 * ' '

        info_tbhits = info.get('tbhits')
        tbhits = f'TB: {self._format_number(info_tbhits)}' if info_tbhits else ''
        delimiter = 5 * ' '

        return delimiter.join((score, depth, nodes, nps, time, hashfull, tbhits))

    def _format_number(self, number: int) -> str:
        if number >= 1_000_000_000_000:
            return f'{number/1_000_000_000_000:5.1f} T'
        elif number >= 1_000_000_000:
            return f'{number/1_000_000_000:5.1f} G'
        elif number >= 1_000_000:
            return f'{number/1_000_000:5.1f} M'
        elif number >= 1_000:
            return f'{number/1_000:5.1f} k'
        else:
            return f'{number:5}  '

    def _format_score(self, score: chess.engine.PovScore) -> str:
        if not score.is_mate():
            if cp_score := score.pov(self.board.turn).score():
                cp_score /= 100
                return format(cp_score, '+7.2f')
            else:
                return '   0.00'
        else:
            return str(score.pov(self.board.turn))

    def _format_egtb_info(self, outcome: Outcome, dtz: DTZ | None = None, dtm: DTM | None = None) -> str:
        outcome_str = f'{outcome:>7}'
        dtz_str = f'DTZ: {dtz}' if dtz else ''
        dtm_str = f'DTM: {dtm}' if dtm else ''
        delimiter = 5 * ' '

        return delimiter.join(filter(None, [outcome_str, dtz_str, dtm_str]))

    def _format_book_info(self, weight: float, learn: int) -> str:
        weight_str = f'{weight:>5.0f} %'
        performance, wdl = self._deserialize_learn(learn)
        performance_str = f'Performance: {performance}' if learn else ''
        wdl_str = f'WDL: {wdl[0]:5.1f} % {wdl[1]:5.1f} % {wdl[2]:5.1f} %' if learn else ''
        delimiter = 5 * ' '

        return delimiter.join([weight_str, performance_str, wdl_str])

    def _deserialize_learn(self, learn: int) -> tuple[Performance, tuple[float, float, float]]:
        performance = (learn >> 20) & 0b111111111111
        win = ((learn >> 10) & 0b1111111111) / 1020.0 * 100.0
        draw = (learn & 0b1111111111) / 1020.0 * 100.0
        loss = max(100.0 - win - draw, 0.0)

        return performance, (win, draw, loss)

    def _get_engine(self) -> chess.engine.SimpleEngine:
        if self.board.uci_variant != 'chess' and self.config['engine']['variants']['enabled']:
            engine_path = self.config['engine']['variants']['path']
            engine_options = self.config['engine']['variants']['uci_options']
            self.ponder_enabled = self.config['engine']['variants']['ponder']
            stderr = subprocess.DEVNULL if self.config['engine']['variants'].get('silence_stderr') else None
        else:
            engine_path = self.config['engine']['path']
            engine_options = self.config['engine']['uci_options']
            self.ponder_enabled = self.config['engine']['ponder']
            stderr = subprocess.DEVNULL if self.config['engine'].get('silence_stderr') else None

            if self.config['engine']['syzygy']['enabled']:
                delimiter = ';' if os.name == 'nt' else ':'
                syzygy_path = delimiter.join(self.config['engine']['syzygy']['paths'])
                engine_options['SyzygyPath'] = syzygy_path
                engine_options['SyzygyProbeLimit'] = self.config['engine']['syzygy']['max_pieces']

        engine = chess.engine.SimpleEngine.popen_uci(engine_path, stderr=stderr)

        for name, value in engine_options.items():
            if chess.engine.Option(name, '', None, None, None, None).is_managed():
                print(f'UCI option "{name}" ignored as it is managed by the bot.')
            elif name in engine.options:
                engine.configure({name: value})
            elif name == 'SyzygyProbeLimit':
                continue
            else:
                print(f'UCI option "{name}" ignored as it is not supported by the engine.')

        return engine

    def _setup_board(self) -> chess.Board:
        if self.game_info.variant == Variant.CHESS960:
            board = chess.Board(self.game_info.initial_fen, chess960=True)
        elif self.game_info.variant == Variant.FROM_POSITION:
            board = chess.Board(self.game_info.initial_fen)
        else:
            VariantBoard = find_variant(self.game_info.variant_name)
            board = VariantBoard()

        for uci_move in self.game_info.state['moves'].split():
            board.push_uci(uci_move)

        return board

    def _get_move_sources(self) -> list[Callable[[], tuple[chess.Move, Message, Offer_Draw, Resign] | None]]:
        opening_sources: dict[Callable[[], tuple[chess.Move, Message, Offer_Draw, Resign] | None], int] = {}

        if self.config['engine']['opening_books']['enabled']:
            opening_sources[self._make_book_move] = self.config['engine']['opening_books'].get('priority', 400)

        if self.config['engine']['online_moves']['opening_explorer']['enabled']:
            opening_sources[self._make_opening_explorer_move] = self.config['engine']['online_moves']['opening_explorer'].get(
                'priority', 300)

        if self.config['engine']['online_moves']['lichess_cloud']['enabled']:
            opening_sources[self._make_cloud_move] = self.config['engine']['online_moves']['lichess_cloud'].get(
                'priority', 200)

        if self.config['engine']['online_moves']['chessdb']['enabled']:
            opening_sources[self._make_chessdb_move] = self.config['engine']['online_moves']['chessdb'].get(
                'priority', 100)

        move_sources = [opening_source for opening_source, _ in sorted(
            opening_sources.items(), key=lambda item: item[1], reverse=True)]

        if self.config['engine']['gaviota']['enabled']:
            move_sources.append(self._make_gaviota_move)

        if self.config['engine']['syzygy']['enabled'] and self.config['engine']['syzygy']['instant_play']:
            move_sources.append(self._make_syzygy_move)

        if self.config['engine']['online_moves']['online_egtb']['enabled']:
            move_sources.append(self._make_egtb_move)

        return move_sources

    def _get_move_overhead(self) -> int:
        multiplier = self.config.get('move_overhead_multiplier', 1.0)
        return max(int(self.game_info.initial_time_ms / 60 * multiplier), 1000)

    def _has_time(self, min_time: int) -> bool:
        if len(self.board.move_stack) < 2:
            return True

        min_time *= 1000
        return self.white_time_ms >= min_time if self.game_info.is_white else self.black_time_ms >= min_time

    def _reduce_own_time(self, milliseconds: int) -> None:
        if self.game_info.is_white:
            self.white_time_ms -= milliseconds
        else:
            self.black_time_ms -= milliseconds

    def _is_repetition(self, move: chess.Move) -> bool:
        board = self.board.copy()
        board.push(move)
        return board.is_repetition(count=2)
