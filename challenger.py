from collections.abc import Iterator
from queue import Empty, Queue
from threading import Thread

from api import API
from botli_dataclasses import API_Challenge_Reponse, Challenge_Request, Challenge_Response


class Challenger:
    def __init__(self, config: dict, api: API) -> None:
        self.config = config
        self.api = api

    def create(self, challenge_request: Challenge_Request) -> Iterator[Challenge_Response]:
        response_queue: Queue[API_Challenge_Reponse] = Queue()
        Thread(target=self.api.create_challenge, args=(challenge_request, response_queue), daemon=True).start()

        challenge_id = None
        try:
            while response := response_queue.get(timeout=challenge_request.timeout):
                if response.challenge_id:
                    challenge_id = response.challenge_id
                    yield Challenge_Response(challenge_id=challenge_id)

                    # More api challenge responses expected
                    continue
                elif response.was_accepted:
                    yield Challenge_Response(success=True)
                elif response.error:
                    print(response.error)
                    yield Challenge_Response(success=False)
                elif response.was_declined:
                    yield Challenge_Response(success=False)
                elif response.has_reached_rate_limit:
                    print(f'Challenge against {challenge_request.opponent_username} failed due to Lichess rate limit.')
                    yield Challenge_Response(success=False, has_reached_rate_limit=True)
                elif response.invalid_initial:
                    print('Challenge failed due to invalid initial time.')
                    yield Challenge_Response(success=False, is_misconfigured=True)
                elif response.invalid_increment:
                    print('Challenge failed due to invalid increment time.')
                    yield Challenge_Response(success=False, is_misconfigured=True)

                # End of api challenge response
                return
        except Empty:
            print(f'Challenge against {challenge_request.opponent_username} has timed out.')
            if challenge_id is None:
                print('Could not cancel challenge because the challenge_id was not set in "Challenger"!')
            else:
                self.api.cancel_challenge(challenge_id)
            yield Challenge_Response(success=False)
