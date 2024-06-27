from threading import Event

from botli_dataclasses import Challenge_Response


class Pending_Challenge:
    def __init__(self) -> None:
        self._challenge_id_event = Event()
        self._challenge_id: str | None = None
        self._finished_event = Event()
        self._success: bool = False
        self._no_opponent: bool = False
        self._has_reached_rate_limit: bool = False
        self._is_misconfigured: bool = False

    def get_challenge_id(self) -> str | None:
        ''' This is blocking '''
        self._challenge_id_event.wait()
        return self._challenge_id

    def get_final_state(self) -> Challenge_Response:
        ''' This is blocking '''
        self._finished_event.wait()
        return Challenge_Response(challenge_id=self._challenge_id,
                                  success=self._success,
                                  no_opponent=self._no_opponent,
                                  has_reached_rate_limit=self._has_reached_rate_limit,
                                  is_misconfigured=self._is_misconfigured)

    def set_challenge_id(self, challenge_id: str) -> None:
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
