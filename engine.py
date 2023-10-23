import os
import subprocess

import chess
import chess.engine

from botli_dataclasses import Game_Information


class Engine:
    def __init__(self, engine: chess.engine.SimpleEngine, ponder: bool) -> None:
        self.engine = engine
        self.ponder = ponder

    @classmethod
    def from_config(cls,
                    engine_config: dict,
                    syzygy_config: dict,
                    game_info: Game_Information | None = None
                    ) -> 'Engine':
        engine_path, ponder, stderr, uci_options = cls._get_engine_settings(engine_config, syzygy_config)

        engine = chess.engine.SimpleEngine.popen_uci(engine_path, stderr=stderr)

        cls._configure_engine(engine, uci_options)

        if game_info:
            engine.send_opponent_information(opponent=chess.engine.Opponent(game_info.opponent_username,
                                                                            game_info.opponent_title,
                                                                            game_info.opponent_rating,
                                                                            game_info.opponent_is_bot))

        return cls(engine, ponder)

    @classmethod
    def test(cls, engine_config: dict, syzygy_config: dict) -> None:
        engine_path, _, stderr, uci_options = cls._get_engine_settings(engine_config, syzygy_config)

        with chess.engine.SimpleEngine.popen_uci(engine_path, stderr=stderr) as engine:
            cls._configure_engine(engine, uci_options)
            result = engine.play(chess.Board(), chess.engine.Limit(time=0.1), info=chess.engine.INFO_ALL)

            if not result.move:
                raise RuntimeError('Engine could not make a move!')

    @staticmethod
    def _get_engine_settings(engine_config: dict, syzygy_config: dict) -> tuple[str, bool, int | None, dict]:
        engine_path = engine_config['path']
        ponder = engine_config['ponder']
        use_syzygy = engine_config['use_syzygy']
        stderr = subprocess.DEVNULL if engine_config['silence_stderr'] else None
        uci_options = engine_config['uci_options']

        if syzygy_config['enabled'] and use_syzygy:
            delimiter = ';' if os.name == 'nt' else ':'
            syzygy_path = delimiter.join(syzygy_config['paths'])
            uci_options['SyzygyPath'] = syzygy_path
            uci_options['SyzygyProbeLimit'] = syzygy_config['max_pieces']

        return engine_path, ponder, stderr, uci_options

    @staticmethod
    def _configure_engine(engine: chess.engine.SimpleEngine, uci_options: dict) -> None:
        for name, value in uci_options.items():
            if chess.engine.Option(name, '', None, None, None, None).is_managed():
                print(f'UCI option "{name}" ignored as it is managed by the bot.')
            elif name in engine.options:
                engine.configure({name: value})
            elif name == 'SyzygyProbeLimit':
                continue
            else:
                print(f'UCI option "{name}" ignored as it is not supported by the engine.')

    @property
    def name(self) -> str:
        return self.engine.id['name']

    def make_move(self,
                  board: chess.Board,
                  white_time: float,
                  black_time: float,
                  increment: float
                  ) -> tuple[chess.Move, chess.engine.InfoDict]:
        if len(board.move_stack) < 2:
            limit = chess.engine.Limit(time=15.0)
            ponder = False
        else:
            limit = chess.engine.Limit(white_clock=white_time, white_inc=increment,
                                       black_clock=black_time, black_inc=increment)
            ponder = self.ponder

        result = self.engine.play(board, limit, info=chess.engine.INFO_ALL, ponder=ponder)

        if not result.move:
            raise RuntimeError('Engine could not make a move!')

        return result.move, result.info

    def start_pondering(self, board: chess.Board) -> None:
        if self.ponder:
            self.engine.analysis(board)

    def stop_pondering(self) -> None:
        if self.ponder:
            self.ponder = False
            self.engine.analysis(chess.Board(), chess.engine.Limit(time=0.001))

    def close(self) -> None:
        try:
            self.engine.quit()
        except TimeoutError:
            print('Engine could not be terminated cleanly.')

        self.engine.close()
