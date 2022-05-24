from threading import Event
from typing import Tuple

from aliases import Challenge_ID, Has_Reached_Rate_Limit, Success


class Pending_Challenge:
    def __init__(self) -> None:
        self._challenge_id_event = Event()
        self._challenge_id: Challenge_ID | None = None
        self._finished_event = Event()
        self._success: Success | None = None
        self._has_reached_rate_limit: Has_Reached_Rate_Limit | None = None

    def get_challenge_id(self) -> Challenge_ID | None:
        ''' This is blocking '''
        self._challenge_id_event.wait()
        return self._challenge_id

    def get_final_state(self) -> Tuple[Success, Has_Reached_Rate_Limit]:
        ''' This is blocking '''
        self._finished_event.wait()
        return bool(self._success), bool(self._has_reached_rate_limit)

    def set_challenge_id(self, challenge_id: Challenge_ID) -> None:
        self._challenge_id = challenge_id
        self._challenge_id_event.set()

    def set_final_state(self, success: Success, has_reached_rate_limit: Has_Reached_Rate_Limit) -> None:
        self._success = success
        self._has_reached_rate_limit = has_reached_rate_limit
        self._finished_event.set()
        self._challenge_id_event.set()
