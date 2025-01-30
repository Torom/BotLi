from api import API
from botli_dataclasses import Challenge_Request, Challenge_Response


class Challenger:
    def __init__(self, api: API) -> None:
        self.api = api

    async def create(self, challenge_request: Challenge_Request) -> Challenge_Response:
        challenge_id = None

        async for response in self.api.create_challenge(challenge_request):
            if response.challenge_id:
                challenge_id = response.challenge_id

            if response.was_accepted:
                return Challenge_Response(challenge_id=challenge_id, success=True)

            if response.was_declined:
                return Challenge_Response(success=False)

            if response.has_reached_rate_limit:
                print(f'Challenge against {challenge_request.opponent_username} failed due to Lichess rate limit.')
                return Challenge_Response(success=False, has_reached_rate_limit=True)

            if response.invalid_initial:
                print('Challenge failed due to invalid initial time.')
                return Challenge_Response(success=False, is_misconfigured=True)

            if response.invalid_increment:
                print('Challenge failed due to invalid increment time.')
                return Challenge_Response(success=False, is_misconfigured=True)

            if response.has_timed_out:
                print(f'Challenge against {challenge_request.opponent_username} has timed out.')
                if challenge_id is not None:
                    await self.api.cancel_challenge(challenge_id)
                return Challenge_Response(success=False)

            if response.error:
                print(response.error)
                return Challenge_Response(success=False)

        return Challenge_Response(success=False)
