import asyncio
import os
import subprocess

import chess
from chess.engine import INFO_ALL, InfoDict, Limit, Opponent, Option, UciProtocol, popen_uci

from configs import Engine_Config, Syzygy_Config


class Engine:
    def __init__(self,
                 transport: asyncio.SubprocessTransport,
                 engine: UciProtocol,
                 ponder: bool,
                 opponent: Opponent) -> None:
        self.transport = transport
        self.engine = engine
        self.ponder = ponder
        self.opponent = opponent

    @classmethod
    async def from_config(cls,
                          engine_config: Engine_Config,
                          syzygy_config: Syzygy_Config,
                          opponent: Opponent) -> 'Engine':
        uci_options = cls._get_uci_options(engine_config, syzygy_config)
        stderr = subprocess.DEVNULL if engine_config.silence_stderr else None

        transport, engine = await popen_uci(engine_config.path, stderr=stderr)

        await cls._configure_engine(engine, uci_options)
        await engine.send_opponent_information(opponent=opponent)

        return cls(transport, engine, engine_config.ponder, opponent)

    @classmethod
    async def test(cls, engine_config: Engine_Config, syzygy_config: Syzygy_Config) -> None:
        uci_options = cls._get_uci_options(engine_config, syzygy_config)
        stderr = subprocess.DEVNULL if engine_config.silence_stderr else None

        transport, engine = await popen_uci(engine_config.path, stderr=stderr)
        await cls._configure_engine(engine, uci_options)
        result = await engine.play(chess.Board(), Limit(time=0.1), info=INFO_ALL)

        if not result.move:
            raise RuntimeError('Engine could not make a move!')

        await engine.quit()
        transport.close()

    @staticmethod
    def _get_uci_options(engine_config: Engine_Config, syzygy_config: Syzygy_Config) -> dict:
        if syzygy_config.enabled and engine_config.use_syzygy:
            delimiter = ';' if os.name == 'nt' else ':'
            syzygy_path = delimiter.join(syzygy_config.paths)
            engine_config.uci_options['SyzygyPath'] = syzygy_path
            engine_config.uci_options['SyzygyProbeLimit'] = syzygy_config.max_pieces

        return engine_config.uci_options

    @staticmethod
    async def _configure_engine(engine: UciProtocol, uci_options: dict) -> None:
        for name, value in uci_options.items():
            if Option(name, '', None, None, None, None).is_managed():
                print(f'UCI option "{name}" ignored as it is managed by the bot.')
            elif name in engine.options:
                await engine.configure({name: value})
            elif name == 'SyzygyProbeLimit':
                continue
            else:
                print(f'UCI option "{name}" ignored as it is not supported by the engine.')

    @property
    def name(self) -> str:
        return self.engine.id['name']

    async def make_move(self,
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

        result = await self.engine.play(board, limit, info=INFO_ALL, ponder=ponder)

        if not result.move:
            raise RuntimeError('Engine could not make a move!')

        return result.move, result.info

    async def start_pondering(self, board: chess.Board) -> None:
        if self.ponder:
            await self.engine.analysis(board)

    async def stop_pondering(self, board: chess.Board) -> None:
        if self.ponder:
            self.ponder = False
            await self.engine.analysis(board, Limit(time=0.001))

    async def close(self) -> None:
        try:
            await asyncio.wait_for(self.engine.quit(), 5.0)
        except TimeoutError:
            print('Engine could not be terminated cleanly.')

        self.transport.close()
