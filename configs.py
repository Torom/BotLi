from dataclasses import dataclass
from typing import Any, Literal


@dataclass
class LimitConfig:
    time: float | None
    depth: int | None
    nodes: int | None


@dataclass
class EngineConfig:
    path: str
    ponder: bool
    silence_stderr: bool
    move_overhead_multiplier: float
    uci_options: dict[str, Any]
    limits: LimitConfig


@dataclass
class SyzygyConfig:
    enabled: bool
    paths: list[str]
    max_pieces: int
    instant_play: bool


@dataclass
class GaviotaConfig:
    enabled: bool
    paths: list[str]
    max_pieces: int


@dataclass
class BooksConfig:
    selection: Literal["weighted_random", "uniform_random", "best_move"]
    max_depth: int | None
    allow_repetitions: bool | None
    names: dict[str, str]


@dataclass
class OpeningBooksConfig:
    enabled: bool
    priority: int
    read_learn: bool | None
    books: dict[str, BooksConfig]


@dataclass
class OpeningExplorerConfig:
    enabled: bool
    priority: int
    player: str | None
    only_without_book: bool
    use_for_variants: bool
    allow_repetitions: bool
    min_time: int
    timeout: int
    min_games: int
    only_with_wins: bool
    selection: Literal["performance", "win_rate"]
    anti: bool
    max_depth: int | None
    max_moves: int | None


@dataclass
class LichessCloudConfig:
    enabled: bool
    priority: int
    only_without_book: bool
    use_for_variants: bool
    allow_repetitions: bool
    trust_eval: bool
    min_eval_depth: int
    min_time: int
    timeout: int
    max_depth: int | None
    max_moves: int | None


@dataclass
class ChessDBConfig:
    enabled: bool
    priority: int
    only_without_book: bool
    allow_repetitions: bool
    trust_eval: bool
    min_time: int
    timeout: int
    best_move: bool
    max_depth: int | None
    max_moves: int | None


@dataclass
class OnlineEGTBConfig:
    enabled: bool
    min_time: int
    timeout: int


@dataclass
class OnlineMovesConfig:
    opening_explorer: OpeningExplorerConfig
    lichess_cloud: LichessCloudConfig
    chessdb: ChessDBConfig
    online_egtb: OnlineEGTBConfig


@dataclass
class OfferDrawConfig:
    enabled: bool
    score: int
    consecutive_moves: int
    min_game_length: int
    against_humans: bool
    min_rating: int | None


@dataclass
class ResignConfig:
    enabled: bool
    score: int
    consecutive_moves: int
    against_humans: bool
    min_rating: int | None


@dataclass
class ChallengeConfig:
    concurrency: int
    max_takebacks: int
    bullet_with_increment_only: bool
    min_increment: int | None
    max_increment: int | None
    min_initial: int | None
    max_initial: int | None
    variants: list[str]
    bot_time_controls: list[str]
    human_time_controls: list[str]
    bot_modes: list[str]
    human_modes: list[str]


@dataclass
class MatchmakingTypeConfig:
    tc: str
    rated: bool | None
    variant: (
        Literal[
            "standard",
            "chess960",
            "crazyhouse",
            "antichess",
            "atomic",
            "horde",
            "kingOfTheHill",
            "racingKings",
            "threeCheck",
        ]
        | None
    )
    weight: int | None
    multiplier: int | None
    min_rating_diff: int | None
    max_rating_diff: int | None


@dataclass
class MatchmakingConfig:
    delay: int
    timeout: int
    selection: Literal["weighted_random", "sequential"]
    types: dict[str, MatchmakingTypeConfig]


@dataclass
class MessagesConfig:
    greeting: str | None
    goodbye: str | None
    greeting_spectators: str | None
    goodbye_spectators: str | None
