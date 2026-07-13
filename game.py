import asyncio
from typing import Any

from chess.engine import EngineTerminatedError

from api import API
from botli_dataclasses import GameInformation
from chatter import Chatter
from config import Config
from lichess_game import LichessGame


class Game:
    def __init__(
        self,
        api: API,
        config: Config,
        username: str,
        game_stream_queue: asyncio.Queue[dict[str, Any]],
        game_stream_task: asyncio.Task,
        info: GameInformation,
        lichess_game: LichessGame,
        chatter: Chatter,
    ) -> None:
        self.api = api
        self.config = config
        self.username = username

        self.game_stream_queue = game_stream_queue
        self.game_stream_task = game_stream_task
        self.info = info
        self.lichess_game = lichess_game
        self.chatter = chatter

        self.takeback_count = 0
        self.was_aborted = False
        self.ejected_tournament: str | None = None

        self.move_task: asyncio.Task[None] | None = None
        self.abortion_task: asyncio.Task[None] | None = None

    @classmethod
    async def acreate(cls, api: API, config: Config, username: str, game_id: str) -> "Game":
        game_stream_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        game_stream_task = asyncio.create_task(api.get_game_stream(game_id, game_stream_queue))
        info = GameInformation.from_game_full_event(await game_stream_queue.get())
        lichess_game = await LichessGame.acreate(api, config, username, info)
        chatter = Chatter(api, config, username, info, lichess_game)

        return cls(api, config, username, game_stream_queue, game_stream_task, info, lichess_game, chatter)

    async def run(self) -> None:
        self._print_game_information()

        if self.info.state["status"] != "started":
            self._print_result_message(self.info.state)
            await self.chatter.send_goodbyes()
            await self.lichess_game.close()
            return

        await self.chatter.send_greetings()

        if self.lichess_game.is_our_turn:
            await self._make_move()

        max_takebacks = 0 if self.info.opponent_is_bot else self.config.challenge.max_takebacks
        if self.info.tournament_id is None:
            abortion_seconds = 30 if self.info.opponent_is_bot else 60
            self.abortion_task = asyncio.create_task(self._abortion_task(abortion_seconds))

        while event := await self.game_stream_queue.get():
            match event["type"]:
                case "chatLine":
                    await self.chatter.handle_chat_message(event, self.takeback_count, max_takebacks)
                    continue
                case "opponentGone":
                    if not self.move_task and event.get("claimWinInSeconds") == 0:
                        if self.lichess_game.has_insufficient_material:
                            await self.api.claim_draw(self.info.id_)
                        else:
                            await self.api.claim_victory(self.info.id_)
                    continue
                case "gameFull":
                    event = event["state"]

            if event.get("wtakeback") or event.get("btakeback"):
                if self.takeback_count >= max_takebacks:
                    await self.api.handle_takeback(self.info.id_, False)
                    continue

                if await self.api.handle_takeback(self.info.id_, True):
                    if self.move_task:
                        self.move_task.cancel()
                        self.move_task = None
                    await self.lichess_game.takeback()
                    self.takeback_count += 1
                continue

            has_updated = self.lichess_game.update(event)

            if event["status"] != "started":
                if self.move_task:
                    self.move_task.cancel()

                self._print_result_message(event)
                await self.chatter.send_goodbyes()
                break

            if has_updated:
                self.move_task = asyncio.create_task(self._make_move())

        if self.abortion_task:
            self.abortion_task.cancel()

        self.game_stream_task.cancel()
        await self.lichess_game.close()

    async def _make_move(self) -> None:
        try:
            lichess_move = await self.lichess_game.make_move()
        except EngineTerminatedError:
            if not self.lichess_game.is_abortable:
                raise

            print("Engine crashed. Aborting game ...")
            await self.api.abort_game(self.info.id_)
            await self.chatter.send_crash_message()
            self.move_task = None
            return

        if lichess_move.resign:
            await self.api.resign_game(self.info.id_)
        else:
            await self.api.send_move(self.info.id_, lichess_move.uci_move, lichess_move.offer_draw)
            await self.chatter.print_eval()
        self.move_task = None

    async def _abortion_task(self, abortion_seconds: int) -> None:
        await asyncio.sleep(abortion_seconds)

        if not self.lichess_game.is_our_turn and self.lichess_game.is_abortable:
            print("Aborting game ...")
            await self.api.abort_game(self.info.id_)
            await self.chatter.send_abortion_message()

        self.abortion_task = None

    def _print_game_information(self) -> None:
        opponents_str = f"{self.info.white_str}   -   {self.info.black_str}"
        message = " • ".join(
            [self.info.id_str, opponents_str, self.info.tc_format, self.info.rated_str, self.info.variant_str]
        )

        print(f"\n{message}\n{123 * '‾'}")

    def _print_result_message(self, game_state: dict[str, Any]) -> None:
        if winner := game_state.get("winner"):
            if winner == "white":
                message = f"{self.info.white_name} won"
                loser = self.info.black_name
                white_result = "1"
                black_result = "0"
            else:
                message = f"{self.info.black_name} won"
                loser = self.info.white_name
                white_result = "0"
                black_result = "1"

            match game_state["status"]:
                case "mate":
                    message += " by checkmate!"
                case "outoftime":
                    message += f"! {loser} ran out of time."
                case "resign":
                    message += f"! {loser} resigned."
                case "variantEnd":
                    message += " by variant rules!"
                case "timeout":
                    message += f"! {loser} timed out."
                case "noStart":
                    if loser == self.username:
                        self.ejected_tournament = self.info.tournament_id
                    message += f"! {loser} has not started the game."
        else:
            white_result = "½"
            black_result = "½"

            match game_state["status"]:
                case "draw":
                    if self.lichess_game.board.is_fifty_moves():
                        message = "Game drawn by 50-move rule."
                    elif self.lichess_game.board.is_repetition():
                        message = "Game drawn by threefold repetition."
                    elif self.lichess_game.board.is_insufficient_material():
                        message = "Game drawn due to insufficient material."
                    elif self.lichess_game.board.is_variant_draw():
                        message = "Game drawn by variant rules."
                    else:
                        message = "Game drawn by agreement."
                case "stalemate":
                    message = "Game drawn by stalemate."
                case "outoftime":
                    out_of_time_player = self.info.black_name if game_state["wtime"] else self.info.white_name
                    message = f"Game drawn. {out_of_time_player} ran out of time."
                case "insufficientMaterialClaim":
                    message = "Game drawn due to insufficient material claim."
                case "timeout":
                    message = "Game drawn. One player left the game."
                case _:
                    self.was_aborted = True
                    message = "Game aborted."

                    white_result = "X"
                    black_result = "X"

        opponents_str = f"{self.info.white_str} {white_result} - {black_result} {self.info.black_str}"
        message = " • ".join([self.info.id_str, opponents_str, message])

        print(f"{message}\n{123 * '‾'}")
