from asyncio import Task
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import chess
import chess.engine
from chess.polyglot import MemoryMappedReader

from enums import Challenge_Color, Perf_Type, Variant


@dataclass
class API_Challenge_Reponse:
    challenge_id: str | None = None
    was_accepted: bool = False
    error: str | None = None
    was_declined: bool = False
    invalid_initial: bool = False
    invalid_increment: bool = False
    has_reached_rate_limit: bool = False
    has_timed_out: bool = False


@dataclass
class Book_Settings:
    selection: Literal['weighted_random', 'uniform_random', 'best_move'] = 'best_move'
    max_depth: int | None = None
    readers: dict[str, MemoryMappedReader] = field(default_factory=dict)


@dataclass
class Bot:
    username: str
    rating_diffs: dict[Perf_Type, int]

    def __eq__(self, __o: object) -> bool:
        if isinstance(__o, Bot):
            return __o.username == self.username

        return NotImplemented


@dataclass
class Challenge:
    challenge_id: str
    opponent_username: str

    def __eq__(self, __o: object) -> bool:
        if isinstance(__o, Challenge):
            return __o.challenge_id == self.challenge_id

        return NotImplemented


@dataclass
class Challenge_Request:
    opponent_username: str
    initial_time: int
    increment: int
    rated: bool
    color: Challenge_Color
    variant: Variant
    timeout: int

    def __eq__(self, __o: object) -> bool:
        if isinstance(__o, Challenge_Request):
            return __o.opponent_username == self.opponent_username

        return NotImplemented


@dataclass(kw_only=True)
class Challenge_Response:
    challenge_id: str | None = None
    success: bool = False
    no_opponent: bool = False
    has_reached_rate_limit: bool = False
    is_misconfigured: bool = False


@dataclass
class Chat_Message:
    username: str
    text: str
    room: Literal['player', 'spectator']

    @classmethod
    def from_chatLine_event(cls, chatLine_event: dict[str, Any]) -> 'Chat_Message':
        username = chatLine_event['username']
        text = chatLine_event['text']
        room = chatLine_event['room']

        return cls(username, text, room)


@dataclass(frozen=True)
class Game_Information:
    id_: str
    white_title: str | None
    white_name: str
    white_rating: int | None
    white_ai_level: int | None
    white_provisional: bool
    black_title: str | None
    black_name: str
    black_rating: int | None
    black_ai_level: int | None
    black_provisional: bool
    initial_time_ms: int
    increment_ms: int
    speed: str
    rated: bool
    variant: Variant
    variant_name: str
    initial_fen: str
    state: dict[str, Any]

    @classmethod
    def from_gameFull_event(cls, gameFull_event: dict[str, Any]) -> 'Game_Information':
        assert gameFull_event['type'] == 'gameFull'

        id_ = gameFull_event['id']
        white_title = gameFull_event['white'].get('title')
        white_name = gameFull_event['white'].get('name', 'AI')
        white_rating = gameFull_event['white'].get('rating')
        white_ai_level = gameFull_event['white'].get('aiLevel')
        white_provisional = gameFull_event['white'].get('provisional', False)
        black_title = gameFull_event['black'].get('title')
        black_name = gameFull_event['black'].get('name', 'AI')
        black_rating = gameFull_event['black'].get('rating')
        black_ai_level = gameFull_event['black'].get('aiLevel')
        black_provisional = gameFull_event['black'].get('provisional', False)
        initial_time_ms = gameFull_event['clock']['initial']
        increment_ms = gameFull_event['clock']['increment']
        speed = gameFull_event['speed']
        rated = gameFull_event['rated']
        variant = Variant(gameFull_event['variant']['key'])
        variant_name = gameFull_event['variant']['name']
        initial_fen = gameFull_event['initialFen']
        state = gameFull_event['state']

        return cls(id_, white_title, white_name, white_rating, white_ai_level, white_provisional, black_title,
                   black_name, black_rating, black_ai_level, black_provisional, initial_time_ms, increment_ms, speed,
                   rated, variant, variant_name, initial_fen, state)

    @property
    def id_str(self) -> str:
        return f'ID: {self.id_}'

    @property
    def white_name_str(self) -> str:
        title_str = f'{self.white_title} ' if self.white_title else ''
        return f'{title_str}{self.white_name}'

    @property
    def white_str(self) -> str:
        provisional_str = '?' if self.white_provisional else ''
        rating_str = f'{self.white_rating}{provisional_str}' if self.white_rating else f'Level {self.white_ai_level}'
        return f'{self.white_name_str} ({rating_str})'

    @property
    def black_name_str(self) -> str:
        title_str = f'{self.black_title} ' if self.black_title else ''
        return f'{title_str}{self.black_name}'

    @property
    def black_str(self) -> str:
        provisional_str = '?' if self.black_provisional else ''
        rating_str = f'{self.black_rating}{provisional_str}' if self.black_rating else f'Level {self.black_ai_level}'
        return f'{self.black_name_str} ({rating_str})'

    @property
    def tc_str(self) -> str:
        initial_time_min = self.initial_time_ms / 60_000
        if initial_time_min.is_integer():
            initial_time_str = str(int(initial_time_min))
        elif initial_time_min == 0.25:
            initial_time_str = '¼'
        elif initial_time_min == 0.5:
            initial_time_str = '½'
        elif initial_time_min == 0.75:
            initial_time_str = '¾'
        else:
            initial_time_str = str(initial_time_min)
        increment_sec = self.increment_ms // 1000
        return f'TC: {initial_time_str}+{increment_sec}'

    @property
    def rated_str(self) -> str:
        return 'Rated' if self.rated else 'Casual'

    @property
    def variant_str(self) -> str:
        return f'Variant: {self.variant_name}'

    @property
    def white_opponent(self) -> chess.engine.Opponent:
        return chess.engine.Opponent(self.white_name, self.white_title, self.white_rating, self.white_title == 'BOT')

    @property
    def black_opponent(self) -> chess.engine.Opponent:
        return chess.engine.Opponent(self.black_name, self.black_title, self.black_rating, self.black_title == 'BOT')


@dataclass
class Gaviota_Result:
    move: chess.Move
    wdl: Literal[-2, -1, 0, 1, 2]
    dtm: int


@dataclass
class Lichess_Move:
    uci_move: str
    offer_draw: bool
    resign: bool


@dataclass
class Matchmaking_Data:
    release_time: datetime = datetime.now()
    multiplier: int = 1
    color: Challenge_Color = Challenge_Color.WHITE

    @classmethod
    def from_dict(cls, dict_: dict[str, Any]) -> 'Matchmaking_Data':
        release_time = datetime.fromisoformat(dict_['release_time']) if 'release_time' in dict_ else datetime.now()
        multiplier = dict_.get('multiplier', 1)
        color = Challenge_Color(dict_['color']) if 'color' in dict_ else Challenge_Color.WHITE

        return Matchmaking_Data(release_time, multiplier, color)

    def to_dict(self) -> dict[str, Any]:
        dict_ = {}
        if self.release_time > datetime.now():
            dict_['release_time'] = self.release_time.isoformat(timespec='seconds')

        if self.multiplier > 1:
            dict_['multiplier'] = self.multiplier

        if self.color == Challenge_Color.BLACK:
            dict_['color'] = Challenge_Color.BLACK

        return dict_


@dataclass
class Matchmaking_Type:
    name: str
    initial_time: int
    increment: int
    rated: bool
    variant: Variant
    perf_type: Perf_Type
    config_multiplier: int | None
    multiplier: int
    weight: float
    min_rating_diff: int | None
    max_rating_diff: int | None

    def __post_init__(self) -> None:
        self.estimated_game_duration = timedelta(seconds=max(self.initial_time, 3) * 1.33 + self.increment * 94.48)

    def __str__(self) -> str:
        initial_time_min = self.initial_time / 60
        if initial_time_min.is_integer():
            initial_time_str = str(int(initial_time_min))
        elif initial_time_min == 0.25:
            initial_time_str = '¼'
        elif initial_time_min == 0.5:
            initial_time_str = '½'
        elif initial_time_min == 0.75:
            initial_time_str = '¾'
        else:
            initial_time_str = str(initial_time_min)
        tc_str = f'TC: {initial_time_str}+{self.increment}'
        rated_str = 'Rated' if self.rated else 'Casual'
        variant_str = f'Variant: {self.variant}'
        delimiter = 5 * ' '

        return delimiter.join([self.name, tc_str, rated_str, variant_str])

    def __eq__(self, __o: object) -> bool:
        if isinstance(__o, Matchmaking_Type):
            return __o.name == self.name

        return NotImplemented


@dataclass
class Move_Response:
    move: chess.Move
    public_message: str
    private_message: str = field(default='', kw_only=True)
    pv: list[chess.Move] = field(default_factory=list, kw_only=True)
    is_drawish: bool = field(default=False, kw_only=True)
    is_resignable: bool = field(default=False, kw_only=True)
    is_engine_move: bool = field(default=False, kw_only=True)


@dataclass
class Syzygy_Result:
    move: chess.Move
    wdl: Literal[-2, -1, 0, 1, 2]
    dtz: int


@dataclass
class Tournament_Request:
    id_: str
    team: str | None
    password: str | None


@dataclass
class Tournament:
    id_: str
    start_time: datetime
    end_time: datetime
    name: str
    initial_time: int
    bots_allowed: bool
    team: str | None = None
    password: str | None = None
    start_task: Task[None] | None = None
    end_task: Task[None] | None = None

    @classmethod
    def from_tournament_info(cls, tournament_info: dict[str, Any]) -> 'Tournament':
        return cls(tournament_info['id'],
                   start_time := datetime.fromisoformat(tournament_info['startsAt']),
                   start_time + timedelta(minutes=tournament_info['minutes']),
                   tournament_info.get('fullName', ''),
                   tournament_info['clock']['limit'],
                   tournament_info.get('botsAllowed', False))

    @property
    def seconds_to_start(self) -> float:
        return (self.start_time - datetime.now(UTC)).total_seconds() - 60.0

    @property
    def seconds_to_finish(self) -> float:
        return (self.end_time - datetime.now(UTC)).total_seconds() - max(30.0, min(self.initial_time / 2, 120.0))

    def cancel(self) -> None:
        if self.start_task:
            self.start_task.cancel()

        if self.end_task:
            self.end_task.cancel()
