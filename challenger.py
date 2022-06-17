from typing import Iterable

from api import API
from challenge_request import Challenge_Request
from challenge_response import Challenge_Response


class Challenger:
    def __init__(self, config: dict, api: API) -> None:
        self.config = config
        self.api = api

    def create(self, challenge_request: Challenge_Request) -> Iterable[Challenge_Response]:
        api_challenge_response = self.api.create_challenge(challenge_request)

        challenge_id = None

        for response in api_challenge_response:
            if response.challenge_id:
                challenge_id = response.challenge_id
                yield Challenge_Response(challenge_id=challenge_id)
            elif response.was_accepted:
                yield Challenge_Response(success=True)
            elif response.error:
                print(response.error)
                yield Challenge_Response(success=False)
            elif response.was_declined:
                print(f'{challenge_request.opponent_username} has declined the challenge.')
                yield Challenge_Response(success=False)
            elif response.has_timed_out:
                print(f'Challenge against {challenge_request.opponent_username} has timed out.')
                if challenge_id is None:
                    print('Could not cancel challenge because the challenge_id was not set in "Challenger"!')
                else:
                    self.api.cancel_challenge(challenge_id)
                yield Challenge_Response(success=False)
            elif response.has_reached_rate_limit:
                print(f'Challenge against {challenge_request.opponent_username} failed due to Lichess rate limit.')
                yield Challenge_Response(success=False, has_reached_rate_limit=True)
