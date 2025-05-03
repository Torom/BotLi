import asyncio
import os
import subprocess

import chess
import chess.engine

from configs import Engine_Config, Syzygy_Config


class Engine:
    def __init__(self,
                 transport: asyncio.SubprocessTransport,
                 engine: chess.engine.UciProtocol,
                 ponder: bool,
                 opponent: chess.engine.Opponent) -> None:
        self.transport = transport
        self.engine = engine
        self.ponder = ponder
        self.opponent = opponent

    @classmethod
    async def from_config(cls,
                          engine_config: Engine_Config,
                          syzygy_config: Syzygy_Config,
                          opponent: chess.engine.Opponent) -> 'Engine':
        stderr = subprocess.DEVNULL if engine_config.silence_stderr else None

        transport, engine = await chess.engine.popen_uci(engine_config.path, stderr=stderr)

        await cls._configure_engine(engine, engine_config, syzygy_config)
        await engine.send_opponent_information(opponent=opponent)

        return cls(transport, engine, engine_config.ponder, opponent)

    @classmethod
    async def test(cls, engine_config: Engine_Config) -> None:
        stderr = subprocess.DEVNULL if engine_config.silence_stderr else None

        transport, engine = await chess.engine.popen_uci(engine_config.path, stderr=stderr)
        await cls._configure_engine(engine, engine_config, Syzygy_Config(False, [], 0, False))
        result = await engine.play(chess.Board(), chess.engine.Limit(time=0.1), info=chess.engine.INFO_ALL)

        if not result.move:
            raise RuntimeError('Engine could not make a move!')

        await engine.quit()
        transport.close()

    @staticmethod
    async def _configure_engine(engine: chess.engine.UciProtocol,
                                engine_config: Engine_Config,
                                syzygy_config: Syzygy_Config) -> None:
        for name, value in engine_config.uci_options.items():
            if name.lower() in chess.engine.MANAGED_OPTIONS:
                print(f'UCI option "{name}" ignored as it is managed by the bot.')
            elif name in engine.options:
                await engine.configure({name: value})
            else:
                print(f'UCI option "{name}" ignored as it is not supported by the engine.')

        if not syzygy_config.enabled:
            return

        if 'SyzygyPath' in engine.options and 'SyzygyPath' not in engine_config.uci_options:
            delimiter = ';' if os.name == 'nt' else ':'
            await engine.configure({'SyzygyPath': delimiter.join(syzygy_config.paths)})

        if 'SyzygyProbeLimit' in engine.options and 'SyzygyProbeLimit' not in engine_config.uci_options:
            await engine.configure({'SyzygyProbeLimit': syzygy_config.max_pieces})

    @property
    def name(self) -> str:
        return self.engine.id['name']

    async def make_move(self,
                        board: chess.Board,
                        white_time: float,
                        black_time: float,
                        increment: float
                        ) -> tuple[chess.Move, chess.engine.InfoDict]:
        if len(board.move_stack) < 2:
            limit = chess.engine.Limit(time=15.0) if self.opponent.is_engine else chess.engine.Limit(time=5.0)
            ponder = False
        else:
            limit = chess.engine.Limit(white_clock=white_time, white_inc=increment,
                                       black_clock=black_time, black_inc=increment)
            ponder = self.ponder

        result = await self.engine.play(board, limit, info=chess.engine.INFO_ALL, ponder=ponder)

        if not result.move:
            raise RuntimeError('Engine could not make a move!')

        return result.move, result.info

    async def start_pondering(self, board: chess.Board) -> None:
        if self.ponder:
            await self.engine.analysis(board)

    async def stop_pondering(self, board: chess.Board) -> None:
        if self.ponder:
            self.ponder = False
            await self.engine.analysis(board, chess.engine.Limit(time=0.001))

    async def close(self) -> None:
        try:
            await asyncio.wait_for(self.engine.quit(), 5.0)
        except TimeoutError:
            print('Engine could not be terminated cleanly.')

        self.transport.close()
