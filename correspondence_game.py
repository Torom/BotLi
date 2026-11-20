import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from api import API
from botli_dataclasses import GameInformation
from chatter import Chatter
from config import Config
from game import Game
from lichess_game import LichessGame


class CorrespondenceGame(Game):
    def __init__(
        self,
        api: API,
        config: Config,
        username: str,
        game_stream_queue: asyncio.Queue[dict[str, Any]],
        game_stream_task: asyncio.Task[None],
        info: GameInformation,
        lichess_game: LichessGame,
        chatter: Chatter,
        correspondence_slot: Callable[[], AbstractAsyncContextManager[None]],
        color: str | None = None,
    ) -> None:
        super().__init__(api, config, username, game_stream_queue, game_stream_task, info, lichess_game, chatter, color)
        self._correspondence_slot = correspondence_slot

    @classmethod
    async def create(
        cls,
        api: API,
        config: Config,
        username: str,
        game_id: str,
        correspondence_slot: Callable[[], AbstractAsyncContextManager[None]],
        color: str | None = None,
    ) -> "CorrespondenceGame":
        game_stream_queue, game_stream_task, info, lichess_game, chatter = await cls._setup(
            api, config, username, game_id
        )
        return cls(
            api,
            config,
            username,
            game_stream_queue,
            game_stream_task,
            info,
            lichess_game,
            chatter,
            correspondence_slot,
            color,
        )

    def stop(self) -> None:
        if self.move_task and not self.move_task.done():
            self.move_task.cancel()
        self.game_stream_queue.put_nowait({})

    def _on_game_start(self) -> None:
        pass

    async def _play_initial_move(self) -> None:
        self.move_task = asyncio.create_task(self._make_move())

    def _start_abortion_task(self) -> None:
        pass

    async def _execute_move(self) -> None:
        if lichess_move := await self.lichess_game.make_source_move():
            self._print_game_information()
            self._print_move(lichess_move, footer=True)
            await self._send_move(lichess_move)
            return

        async with self._correspondence_slot():
            self._print_game_information()
            try:
                lichess_move = await self._compute_move(self.lichess_game.make_engine_move)
                if lichess_move is not None:
                    self._print_move(lichess_move)
            finally:
                print(123 * "‾")
                await self.lichess_game.close_engine()

        if lichess_move is not None:
            await self._send_move(lichess_move)
