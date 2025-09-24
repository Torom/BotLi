import asyncio
from typing import Any

from api import API
from botli_dataclasses import Challenge_Request, Game_Information
from config import Config
from enums import Challenge_Color, Variant


class Rematch_Manager:
    def __init__(self, api: API, config: Config, username: str) -> None:
        self.api = api
        self.config = config
        self.username = username

        # Track rematch history per opponent
        self.rematch_counts: dict[str, int] = {}
        self.last_game_info: Game_Information | None = None
        self.pending_rematch: str | None = None
        self.rematch_offered: bool = False  # Track if rematch was already offered

    def should_offer_rematch(self, game_info: Game_Information, game_result: str, winner: str | None) -> bool:
        """Determine if we should offer a rematch based on configuration and game outcome."""
        print(f"Checking rematch conditions for game result: {game_result}, winner: {winner}")

        if not self.config.rematch.enabled:
            print(f"Rematch disabled: enabled={self.config.rematch.enabled}")
            return False

        opponent_name = self._get_opponent_name(game_info)
        if not opponent_name:
            print("No opponent name found")
            return False

        # Check if we've reached max consecutive rematches with this opponent
        current_count = self.rematch_counts.get(opponent_name.lower(), 0)
        print(f"Rematch count for {opponent_name}: {current_count}/{self.config.rematch.max_consecutive}")

        if current_count >= self.config.rematch.max_consecutive:
            print(f"Max consecutive rematches reached for {opponent_name} - STOPPING")
            return False

        # Check if we already have a pending rematch with this opponent
        if self.pending_rematch == opponent_name.lower():
            print(f"Rematch already pending with {opponent_name}")
            return False

        # Check opponent type (human vs bot)
        is_opponent_bot = self._is_opponent_bot(game_info)
        if is_opponent_bot and not self.config.rematch.against_bots:
            print(f"Rematch against bots disabled")
            return False
        if not is_opponent_bot and not self.config.rematch.against_humans:
            print(f"Rematch against humans disabled")
            return False

        # Check rating difference constraints
        if not self._check_rating_constraints(game_info):
            print(f"Rating constraints not met")
            return False

        # Check game outcome preferences
        if winner == self.username and not self.config.rematch.offer_on_win:
            print(f"Rematch on win disabled")
            return False
        elif winner and winner != self.username and not self.config.rematch.offer_on_loss:
            print(f"Rematch on loss disabled")
            return False
        elif not winner and not self.config.rematch.offer_on_draw:
            print(f"Rematch on draw disabled")
            return False

        print(f"All rematch conditions met for {opponent_name}")
        return True

    async def offer_rematch(self, game_info: Game_Information) -> bool:
        """Offer a rematch to the opponent."""
        opponent_name = self._get_opponent_name(game_info)
        if not opponent_name:
            return False

        # Wait for the configured delay
        if self.config.rematch.delay_seconds > 0:
            await asyncio.sleep(self.config.rematch.delay_seconds)

        # Create rematch challenge request
        challenge_request = self._create_rematch_challenge(game_info, opponent_name)
        if not challenge_request:
            return False

        # Increment rematch count when we OFFER (not when accepted)
        opponent_key = opponent_name.lower()
        self.rematch_counts[opponent_key] = self.rematch_counts.get(opponent_key, 0) + 1
        print(f'Rematch count for {opponent_name} is now: {self.rematch_counts[opponent_key]}')

        # Store the pending rematch info
        self.pending_rematch = opponent_name.lower()
        self.last_game_info = game_info
        self.rematch_offered = False  # Reset for next cycle

        # The actual challenge creation will be handled by the game manager
        return True

    def on_rematch_accepted(self, opponent_name: str) -> None:
        """Called when a rematch is accepted."""
        self.pending_rematch = None
        self.rematch_offered = False
        opponent_key = opponent_name.lower()
        current_count = self.rematch_counts.get(opponent_key, 0)
        print(f'Rematch accepted by {opponent_name}. Current count: {current_count}')

    def on_rematch_declined(self, opponent_name: str) -> None:
        """Called when a rematch is declined."""
        self.pending_rematch = None
        self.rematch_offered = False
        # Keep the count when declined - don't reset it
        opponent_key = opponent_name.lower()
        current_count = self.rematch_counts.get(opponent_key, 0)
        print(f'Rematch declined by {opponent_name}. Count remains at: {current_count}')

    def on_game_finished(self, opponent_name: str) -> None:
        """Called when a game finishes to reset rematch count if needed."""
        # Don't reset counts anymore - let them persist
        self.rematch_offered = False
        print(f'Game finished with {opponent_name}. Rematch count preserved.')

    def clear_pending_rematch(self) -> None:
        """Clear the pending rematch after it's been processed."""
        if self.pending_rematch:
            opponent_key = self.pending_rematch
            current_count = self.rematch_counts.get(opponent_key, 0)
            print(f'Clearing pending rematch with {opponent_key}. Count remains at: {current_count}')

        self.pending_rematch = None
        self.last_game_info = None
        self.rematch_offered = False

    def get_rematch_challenge_request(self) -> Challenge_Request | None:
        """Get the challenge request for the pending rematch."""
        if not self.pending_rematch or not self.last_game_info:
            return None

        return self._create_rematch_challenge(self.last_game_info, self.pending_rematch)

    def _get_opponent_name(self, game_info: Game_Information) -> str | None:
        """Get the opponent's name from game info."""
        if game_info.white_name.lower() == self.username.lower():
            return game_info.black_name
        elif game_info.black_name.lower() == self.username.lower():
            return game_info.white_name
        return None

    def _is_opponent_bot(self, game_info: Game_Information) -> bool:
        """Check if the opponent is a bot."""
        if game_info.white_name.lower() == self.username.lower():
            return game_info.black_title == 'BOT'
        else:
            return game_info.white_title == 'BOT'

    def _check_rating_constraints(self, game_info: Game_Information) -> bool:
        """Check if rating difference constraints are satisfied."""
        our_rating = self._get_our_rating(game_info)
        opponent_rating = self._get_opponent_rating(game_info)

        if our_rating is None or opponent_rating is None:
            return True  # Allow if ratings are not available

        rating_diff = abs(our_rating - opponent_rating)

        if self.config.rematch.min_rating_diff is not None:
            if rating_diff < self.config.rematch.min_rating_diff:
                return False

        if self.config.rematch.max_rating_diff is not None:
            if rating_diff > self.config.rematch.max_rating_diff:
                return False

        return True

    def _get_our_rating(self, game_info: Game_Information) -> int | None:
        """Get our rating from game info."""
        if game_info.white_name.lower() == self.username.lower():
            return game_info.white_rating
        else:
            return game_info.black_rating

    def _get_opponent_rating(self, game_info: Game_Information) -> int | None:
        """Get opponent's rating from game info."""
        if game_info.white_name.lower() == self.username.lower():
            return game_info.black_rating
        else:
            return game_info.white_rating

    def _create_rematch_challenge(self, game_info: Game_Information, opponent_name: str) -> Challenge_Request | None:
        """Create a challenge request for a rematch."""
        try:
            # Determine color for rematch (swap colors)
            if game_info.white_name.lower() == self.username.lower():
                color = Challenge_Color.BLACK
            else:
                color = Challenge_Color.WHITE

            # Parse time control
            initial_time_str, increment_str = game_info.tc_str.split('+')
            initial_time = int(float(initial_time_str) * 60)
            increment = int(increment_str)

            # Get variant
            variant = Variant(game_info.variant)

            return Challenge_Request(
                opponent_name,
                initial_time,
                increment,
                game_info.rated,
                color,
                variant,
                self.config.rematch.timeout_seconds
            )
        except (ValueError, AttributeError) as e:
            print(f'Failed to create rematch challenge: {e}')
            return None