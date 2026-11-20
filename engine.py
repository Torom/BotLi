import asyncio
import os
import subprocess

import chess
import chess.engine
import chess.variant

from configs import EngineConfig, LimitConfig, SyzygyConfig
from utils import UCI_VARIANTS


class Engine:
    def __init__(
        self,
        transport: asyncio.SubprocessTransport,
        engine: chess.engine.UciProtocol,
        ponder: bool,
        opponent: chess.engine.Opponent,
        limit_config: LimitConfig,
        is_correspondence: bool = False,
    ) -> None:
        self.transport = transport
        self.engine = engine
        self.ponder = ponder
        self.opponent = opponent
        self.limit_config = limit_config
        self.is_correspondence = is_correspondence

    @classmethod
    async def from_config(
        cls,
        engine_config: EngineConfig,
        syzygy_config: SyzygyConfig,
        opponent: chess.engine.Opponent,
        is_correspondence: bool = False,
        correspondence_limits: LimitConfig | None = None,
    ) -> "Engine":
        stderr = subprocess.DEVNULL if engine_config.silence_stderr else None

        transport, engine = await chess.engine.popen_uci(engine_config.path, cwd=engine_config.dir, stderr=stderr)

        await cls._configure_engine(engine, engine_config, syzygy_config)
        await engine.send_opponent_information(opponent=opponent)
        engine_config.name = engine.id.get("name")

        if is_correspondence:
            ponder = False
            if engine_config.limits.is_configured:
                limit_config = engine_config.limits
            elif correspondence_limits and correspondence_limits.is_configured:
                limit_config = correspondence_limits
            else:
                limit_config = LimitConfig(10.0, None, None)
        else:
            ponder = engine_config.ponder
            limit_config = engine_config.limits

        return cls(transport, engine, ponder, opponent, limit_config, is_correspondence)

    @classmethod
    async def test(cls, engine_config: EngineConfig) -> None:
        if engine_config.skip_test:
            print(f'Testing engine "{engine_config.key}" ... SKIPPED')
            return

        stderr = subprocess.DEVNULL if engine_config.silence_stderr else None

        transport, engine = await chess.engine.popen_uci(engine_config.path, cwd=engine_config.dir, stderr=stderr)
        await cls._configure_engine(engine, engine_config, SyzygyConfig(False, [], 0, False))
        engine_config.name = engine.id.get("name")

        variants: list[type[chess.Board]] = []

        for key_part in engine_config.key.split("_"):
            if key_part in {"standard", "variants"}:
                break
            try:
                variants = [chess.variant.find_variant(key_part)]
                break
            except ValueError:
                pass

        if not variants:
            if "UCI_Variant" in engine.options and engine.options["UCI_Variant"].var:
                variants = [v for u in engine.options["UCI_Variant"].var if (v := UCI_VARIANTS.get(u))]
            else:
                variants = [chess.Board]

        try:
            for variant in variants:
                print(f'Testing engine "{engine_config.key}" in {variant.aliases[0]} ... ', end="", flush=True)
                result = await engine.play(variant(), chess.engine.Limit(depth=1), info=chess.engine.INFO_ALL)

                if not result.move:
                    raise RuntimeError("Engine could not make a move!")

                print("OK")
        finally:
            await engine.quit()
            transport.close()

    @staticmethod
    async def _configure_engine(
        engine: chess.engine.UciProtocol, engine_config: EngineConfig, syzygy_config: SyzygyConfig
    ) -> None:
        for name, value in engine_config.uci_options.items():
            if name.lower() in chess.engine.MANAGED_OPTIONS:
                print(f'UCI option "{name}" ignored as it is managed by the bot.')
            elif name in engine.options:
                await engine.configure({name: value})
            else:
                print(f'UCI option "{name}" ignored as it is not supported by the engine.')

        if not syzygy_config.enabled:
            return

        if "SyzygyPath" in engine.options and "SyzygyPath" not in engine_config.uci_options:
            delimiter = ";" if os.name == "nt" else ":"
            await engine.configure({"SyzygyPath": delimiter.join(syzygy_config.paths)})

        if "SyzygyProbeLimit" in engine.options and "SyzygyProbeLimit" not in engine_config.uci_options:
            await engine.configure({"SyzygyProbeLimit": syzygy_config.max_pieces})

    async def make_move(
        self, board: chess.Board, white_time: float, black_time: float, increment: float
    ) -> tuple[chess.Move, chess.engine.InfoDict]:
        if self.is_correspondence:
            limit = chess.engine.Limit(
                time=self.limit_config.time, depth=self.limit_config.depth, nodes=self.limit_config.nodes
            )
            ponder = self.ponder
        elif len(board.move_stack) < 2:
            time_limit = 10.0 if self.opponent.is_engine else 5.0
            if self.limit_config.time:
                time_limit = min(time_limit, self.limit_config.time)

            limit = chess.engine.Limit(time=time_limit, depth=self.limit_config.depth, nodes=self.limit_config.nodes)
            ponder = False
        else:
            limit = chess.engine.Limit(
                white_clock=white_time,
                white_inc=increment,
                black_clock=black_time,
                black_inc=increment,
                time=self.limit_config.time,
                depth=self.limit_config.depth,
                nodes=self.limit_config.nodes,
            )
            ponder = self.ponder

        result = await self.engine.play(board, limit, info=chess.engine.INFO_ALL, ponder=ponder)

        if not result.move:
            raise chess.engine.EngineTerminatedError("Engine could not make a move!")

        return result.move, result.info

    async def stop_pondering(self, board: chess.Board) -> None:
        if self.ponder:
            self.ponder = False
            await self.engine.play(board, chess.engine.Limit(depth=1), ponder=False)

    async def close(self) -> None:
        try:
            await asyncio.wait_for(self.engine.quit(), 5.0)
        except TimeoutError:
            print("Engine could not be terminated cleanly.")
        except chess.engine.EngineTerminatedError:
            pass

        self.transport.close()
