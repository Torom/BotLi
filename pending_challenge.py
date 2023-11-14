from threading import Event

from aliases import Challenge_ID, Has_Reached_Rate_Limit, Is_Misconfigured, No_Opponent, Success
from botli_dataclasses import Challenge_Response


class Pending_Challenge:
    def __init__(self) -> None:
        self._challenge_id_event = Event()
        self._challenge_id: Challenge_ID | None = None
        self._finished_event = Event()
        self._success: Success = False
        self._no_opponent: No_Opponent = False
        self._has_reached_rate_limit: Has_Reached_Rate_Limit = False
        self._is_misconfigured: Is_Misconfigured = False

    def get_challenge_id(self) -> Challenge_ID | None:
        ''' This is blocking '''
        self._challenge_id_event.wait()
        return self._challenge_id

    def get_final_state(self) -> tuple[Success, No_Opponent, Has_Reached_Rate_Limit, Is_Misconfigured]:
        ''' This is blocking '''
        self._finished_event.wait()
        return self._success, self._no_opponent, self._has_reached_rate_limit, self._is_misconfigured

    def set_challenge_id(self, challenge_id: Challenge_ID) -> None:
        self._challenge_id = challenge_id
        self._challenge_id_event.set()

    def set_final_state(self, challenge_response: Challenge_Response) -> None:
        self._success = challenge_response.success
        self._no_opponent = challenge_response.no_opponent
        self._has_reached_rate_limit = challenge_response.has_reached_rate_limit
        self._is_misconfigured = challenge_response.is_misconfigured
        self._finished_event.set()
        self._challenge_id_event.set()

    def return_early(self) -> None:
        self._finished_event.set()
        self._challenge_id_event.set()
