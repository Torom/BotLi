from dataclasses import dataclass

from aliases import Challenge_ID
from enums import Challenge_Color, Variant


@dataclass
class API_Challenge_Reponse:
    challenge_id: Challenge_ID | None = None
    was_accepted: bool = False
    error: str | None = None
    was_declined: bool = False
    invalid_initial: bool = False
    invalid_increment: bool = False
    has_reached_rate_limit: bool = False


@dataclass
class Bot:
    username: str
    rating_diff: int

    def __eq__(self, __o: object) -> bool:
        if isinstance(__o, Bot):
            return __o.username == self.username

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


@dataclass
class Challenge_Response:
    challenge_id: Challenge_ID | None = None
    success: bool = False
    has_reached_rate_limit: bool = False
    is_misconfigured: bool = False


@dataclass
class Game_Information:
    id_: str
    white_title: str
    white_name: str
    white_rating: int
    white_provisional: str
    black_title: str
    black_name: str
    black_rating: int
    black_provisional: str
    initial_time_ms: int
    increment_ms: int
    rated: bool
    variant_name: str

    @classmethod
    def from_gameFull_event(cls, gameFull_event: dict) -> 'Game_Information':
        id_ = gameFull_event['id']
        white_title = gameFull_event['white'].get('title') or ''
        white_name = gameFull_event['white'].get('name', 'AI')
        white_rating = gameFull_event['white'].get('rating') or gameFull_event['white']['aiLevel']
        white_provisional = '?' if gameFull_event['white'].get('provisional') else ''
        black_title = gameFull_event['black'].get('title') or ''
        black_name = gameFull_event['black'].get('name', 'AI')
        black_rating = gameFull_event['black'].get('rating') or gameFull_event['black']['aiLevel']
        black_provisional = '?' if gameFull_event['black'].get('provisional') else ''
        initial_time_ms = gameFull_event['clock']['initial']
        increment_ms = gameFull_event['clock']['increment']
        rated = gameFull_event['rated']
        variant_name = gameFull_event['variant']['name']

        return Game_Information(id_, white_title, white_name, white_rating, white_provisional, black_title, black_name,
                                black_rating, black_provisional, initial_time_ms, increment_ms, rated, variant_name)

    @property
    def id_str(self) -> str:
        return f'ID: {self.id_}'

    @property
    def white_str(self) -> str:
        return f'{self.white_title}{" " if self.white_title else ""}{self.white_name} ({self.white_rating}{self.white_provisional})'

    @property
    def black_str(self) -> str:
        return f'{self.black_title}{" " if self.black_title else ""}{self.black_name} ({self.black_rating}{self.black_provisional})'

    @property
    def tc_str(self) -> str:
        initial_time_min = self.initial_time_ms / 60_000
        initial_time_str = str(int(initial_time_min)) if int(
            initial_time_min) == initial_time_min else str(initial_time_min)
        increment_sec = self.increment_ms // 1000
        return f'TC: {initial_time_str}+{increment_sec}'

    @property
    def rated_str(self) -> str:
        return 'Rated' if self.rated else 'Unrated'

    @property
    def variant_str(self) -> str:
        return f'Variant: {self.variant_name}'
