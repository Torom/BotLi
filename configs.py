from dataclasses import dataclass
from typing import Any, Literal


@dataclass
class Engine_Config:
    path: str
    ponder: bool
    silence_stderr: bool
    move_overhead_multiplier: float | None
    uci_options: dict[str, Any]


@dataclass
class Syzygy_Config:
    enabled: bool
    paths: list[str]
    max_pieces: int
    instant_play: bool


@dataclass
class Gaviota_Config:
    enabled: bool
    paths: list[str]
    max_pieces: int


@dataclass
class Books_Config:
    selection: Literal['weighted_random', 'uniform_random', 'best_move']
    max_depth: int | None
    names: dict[str, str]


@dataclass
class Opening_Books_Config:
    enabled: bool
    priority: int
    read_learn: bool | None
    books: dict[str, Books_Config]


@dataclass
class Opening_Explorer_Config:
    enabled: bool
    priority: int
    only_without_book: bool
    use_for_variants: bool
    min_time: int
    timeout: int
    min_games: int
    only_with_wins: bool
    selection: Literal['performance', 'win_rate']
    anti: bool
    max_depth: int | None
    max_moves: int | None


@dataclass
class Lichess_Cloud_Config:
    enabled: bool
    priority: int
    only_without_book: bool
    min_eval_depth: int
    min_time: int
    timeout: int
    max_depth: int | None
    max_moves: int | None


@dataclass
class ChessDB_Config:
    enabled: bool
    priority: int
    only_without_book: bool
    min_candidates: int
    min_time: int
    timeout: int
    selection: Literal['optimal', 'best', 'good']
    max_depth: int | None
    max_moves: int | None


@dataclass
class Online_EGTB_Config:
    enabled: bool
    min_time: int
    timeout: int


@dataclass
class Online_Moves_Config:
    opening_explorer: Opening_Explorer_Config
    lichess_cloud: Lichess_Cloud_Config
    chessdb: ChessDB_Config
    online_egtb: Online_EGTB_Config


@dataclass
class Offer_Draw_Config:
    enabled: bool
    score: int
    consecutive_moves: int
    min_game_length: int
    against_humans: bool


@dataclass
class Resign_Config:
    enabled: bool
    score: int
    consecutive_moves: int
    against_humans: bool


@dataclass
class Challenge_Config:
    concurrency: int
    bullet_with_increment_only: bool
    min_increment: int | None
    max_increment: int | None
    min_initial: int | None
    max_initial: int | None
    variants: list[str]
    time_controls: list[str]
    bot_modes: list[str]
    human_modes: list[str]


@dataclass
class Matchmaking_Type_Config:
    tc: str
    rated: bool | None
    variant: Literal['standard', 'chess960', 'crazyhouse', 'antichess', 'atomic',
                     'horde', 'kingOfTheHill', 'racingKings', 'threeCheck'] | None
    weight: int | None
    multiplier: int | None
    min_rating_diff: int | None
    max_rating_diff: int | None


@dataclass
class Matchmaking_Config:
    delay: int
    timeout: int
    selection: Literal['weighted_random', 'sequential']
    types: dict[str, Matchmaking_Type_Config]


@dataclass
class Messages_Config:
    greeting: str | None
    goodbye: str | None
    greeting_spectators: str | None
    goodbye_spectators: str | None
