import os
import subprocess

import chess
from chess.engine import INFO_ALL, InfoDict, Limit, Opponent, Option, SimpleEngine

from configs import Engine_Config, Syzygy_Config


class Engine:
    def __init__(self, engine: SimpleEngine, ponder: bool, opponent: Opponent) -> None:
        self.engine = engine
        self.ponder = ponder
        self.opponent = opponent

    @classmethod
    def from_config(cls, engine_config: Engine_Config, syzygy_config: Syzygy_Config, opponent: Opponent) -> 'Engine':
        uci_options = cls._get_uci_options(engine_config, syzygy_config)
        stderr = subprocess.DEVNULL if engine_config.silence_stderr else None

        engine = SimpleEngine.popen_uci(engine_config.path, stderr=stderr)

        cls._configure_engine(engine, uci_options)
        engine.send_opponent_information(opponent=opponent)

        return cls(engine, engine_config.ponder, opponent)

    @classmethod
    def test(cls, engine_config: Engine_Config, syzygy_config: Syzygy_Config) -> None:
        uci_options = cls._get_uci_options(engine_config, syzygy_config)
        stderr = subprocess.DEVNULL if engine_config.silence_stderr else None

        with SimpleEngine.popen_uci(engine_config.path, stderr=stderr) as engine:
            cls._configure_engine(engine, uci_options)
            result = engine.play(chess.Board(), Limit(time=0.1), info=INFO_ALL)

            if not result.move:
                raise RuntimeError('Engine could not make a move!')

    @staticmethod
    def _get_uci_options(engine_config: Engine_Config, syzygy_config: Syzygy_Config) -> dict:
        if syzygy_config.enabled and engine_config.use_syzygy:
            delimiter = ';' if os.name == 'nt' else ':'
            syzygy_path = delimiter.join(syzygy_config.paths)
            engine_config.uci_options['SyzygyPath'] = syzygy_path
            engine_config.uci_options['SyzygyProbeLimit'] = syzygy_config.max_pieces

        return engine_config.uci_options

    @staticmethod
    def _configure_engine(engine: SimpleEngine, uci_options: dict) -> None:
        for name, value in uci_options.items():
            if Option(name, '', None, None, None, None).is_managed():
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
                  ) -> tuple[chess.Move, InfoDict]:
        if len(board.move_stack) < 2:
            limit = Limit(time=15.0) if self.opponent.is_engine else Limit(time=5.0)
            ponder = False
        else:
            limit = Limit(white_clock=white_time, white_inc=increment,
                          black_clock=black_time, black_inc=increment)
            ponder = self.ponder

        result = self.engine.play(board, limit, info=INFO_ALL, ponder=ponder)

        if not result.move:
            raise RuntimeError('Engine could not make a move!')

        return result.move, result.info

    def start_pondering(self, board: chess.Board) -> None:
        if self.ponder:
            self.engine.analysis(board)

    def stop_pondering(self) -> None:
        if self.ponder:
            self.ponder = False
            self.engine.analysis(chess.Board(), Limit(time=0.001))

    def close(self) -> None:
        try:
            self.engine.quit()
        except TimeoutError:
            print('Engine could not be terminated cleanly.')

        self.engine.close()
