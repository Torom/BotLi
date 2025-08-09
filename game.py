import asyncio
from typing import Any

from api import API
from botli_dataclasses import Game_Information
from chatter import Chatter
from config import Config
from lichess_game import Lichess_Game


class Game:
    def __init__(self, api: API, config: Config, username: str, game_id: str, game_manager=None) -> None:
        self.api = api
        self.config = config
        self.username = username
        self.game_id = game_id
        self.game_manager = game_manager
        self.was_aborted = False
        self.rematch_count = 0
        self.move_task: asyncio.Task[None] | None = None

    async def run(self) -> None:
        game_stream_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        asyncio.create_task(self.api.get_game_stream(self.game_id, game_stream_queue))
        info = Game_Information.from_gameFull_event(await game_stream_queue.get())
        lichess_game = await Lichess_Game.acreate(self.api, self.config, self.username, info)
        chatter = Chatter(self.api, self.config, self.username, info, lichess_game)

        self._print_game_information(info)

        if info.state['status'] != 'started':
            self._print_result_message(info.state, lichess_game, info)
            await chatter.send_goodbyes()
            await lichess_game.close()
            return

        await chatter.send_greetings()

        if lichess_game.is_our_turn:
            await self._make_move(lichess_game, chatter)
        else:
            await lichess_game.start_pondering()

        opponent_title = info.black_title if lichess_game.is_white else info.white_title
        abortion_seconds = 30 if opponent_title == 'BOT' else 60
        abortion_task = asyncio.create_task(self._abortion_task(lichess_game, chatter, abortion_seconds))

        while event := await game_stream_queue.get():
            match event['type']:
                case 'chatLine':
                    await chatter.handle_chat_message(event)
                    continue
                case 'opponentGone':
                    if event.get('claimWinInSeconds') == 0:
                        await self.api.claim_victory(self.game_id)
                    continue
                case 'gameFull':
                    event = event['state']

            lichess_game.update(event)

            if event['status'] != 'started':
                if self.move_task:
                    self.move_task.cancel()

                self._print_result_message(event, lichess_game, info)
                await chatter.send_goodbyes()
                
                # Check if we should offer a rematch
                try:
                    if self._should_offer_rematch(event, info):
                        await self._create_rematch_challenge(info, chatter)
                except Exception as e:
                    print(f"Error creating rematch challenge for game {self.game_id}: {e}")
                
                break

            if lichess_game.is_our_turn and not lichess_game.board.is_repetition():
                self.move_task = asyncio.create_task(self._make_move(lichess_game, chatter))

        abortion_task.cancel()
        self.was_aborted = lichess_game.is_abortable
        await lichess_game.close()

    async def _make_move(self, lichess_game: Lichess_Game, chatter: Chatter) -> None:
        lichess_move = await lichess_game.make_move()
        if lichess_move.resign:
            await self.api.resign_game(self.game_id)
        else:
            await self.api.send_move(self.game_id, lichess_move.uci_move, lichess_move.offer_draw)
            await chatter.print_eval()
        self.move_task = None

    async def _abortion_task(self, lichess_game: Lichess_Game, chatter: Chatter, abortion_seconds: int) -> None:
        await asyncio.sleep(abortion_seconds)

        if not lichess_game.is_our_turn and lichess_game.is_abortable:
            print('Aborting game ...')
            await self.api.abort_game(self.game_id)
            await chatter.send_abortion_message()

    def _print_game_information(self, info: Game_Information) -> None:
        opponents_str = f'{info.white_str}   -   {info.black_str}'
        message = (5 * ' ').join([info.id_str, opponents_str, info.tc_str,
                                  info.rated_str, info.variant_str])

        print(f'\n{message}\n{128 * "‾"}')

    def _print_result_message(self,
                              game_state: dict[str, Any],
                              lichess_game: Lichess_Game,
                              info: Game_Information) -> None:
        if winner := game_state.get('winner'):
            if winner == 'white':
                message = f'{info.white_name} won'
                loser = info.black_name
                white_result = '1'
                black_result = '0'
            else:
                message = f'{info.black_name} won'
                loser = info.white_name
                white_result = '0'
                black_result = '1'

            match game_state['status']:
                case 'mate':
                    message += ' by checkmate!'
                case 'outoftime':
                    message += f'! {loser} ran out of time.'
                case 'resign':
                    message += f'! {loser} resigned.'
                case 'variantEnd':
                    message += ' by variant rules!'
                case 'timeout':
                    message += f'! {loser} timed out.'
                case 'noStart':
                    message += f'! {loser} has not started the game.'
        else:
            white_result = '½'
            black_result = '½'

            if game_state['status'] == 'draw':
                if lichess_game.board.is_fifty_moves():
                    message = 'Game drawn by 50-move rule.'
                elif lichess_game.board.is_repetition():
                    message = 'Game drawn by threefold repetition.'
                elif lichess_game.board.is_insufficient_material():
                    message = 'Game drawn due to insufficient material.'
                elif lichess_game.board.is_variant_draw():
                    message = 'Game drawn by variant rules.'
                else:
                    message = 'Game drawn by agreement.'
            elif game_state['status'] == 'stalemate':
                message = 'Game drawn by stalemate.'
            elif game_state['status'] == 'outoftime':
                out_of_time_player = info.black_name if game_state['wtime'] else info.white_name
                message = f'Game drawn. {out_of_time_player} ran out of time.'
            else:
                message = 'Game aborted.'

                white_result = 'X'
                black_result = 'X'

        opponents_str = f'{info.white_str} {white_result} - {black_result} {info.black_str}'
        message = (5 * ' ').join([info.id_str, opponents_str, message])

        print(f'{message}\n{128 * "‾"}')
        
    def _should_offer_rematch(self, game_state: dict[str, Any], info: Game_Information) -> bool:
        """Determine if a rematch should be offered based on configuration."""
        # Check if auto-rematch is enabled in the configuration
        if hasattr(self.config, 'auto_rematch'):
            if not self.config.auto_rematch.enabled:
                return False
        else:
            # If auto_rematch is not in the config, don't offer rematch
            return False
            
        # Don't rematch aborted games
        if self.was_aborted:
            return False
            
        # Get our color from the game info
        is_white = info.white_name.lower() == self.username.lower()
        opponent_username = info.black_name if is_white else info.white_name
        
        # Check rematch count if game manager is available
        if self.game_manager:
            player_pair = frozenset([self.username.lower(), opponent_username.lower()])
            rematch_count = self.game_manager.rematch_counts.get(player_pair, 0)
            max_rematches = 3
            if hasattr(self.config, 'auto_rematch'):
                max_rematches = self.config.auto_rematch.max_rematches
            if rematch_count >= max_rematches:
                print(f"Maximum rematches ({max_rematches}) reached with {opponent_username}")
                return False
        # Fall back to instance variable if game manager not available
        elif self.rematch_count >= 3:
            return False
            
        # Check if we should only rematch after wins
        if hasattr(self.config, 'auto_rematch') and self.config.auto_rematch.only_after_wins:
            winner = game_state.get('winner')
            if not winner or (winner == 'white' and not is_white) or (winner == 'black' and is_white):
                return False
                
        # Check if we should only rematch after losses
        if hasattr(self.config, 'auto_rematch') and self.config.auto_rematch.only_after_losses:
            winner = game_state.get('winner')
            if not winner or (winner == 'white' and is_white) or (winner == 'black' and not is_white):
                return False
                
        # Check if we should only rematch against bots
        opponent_title = info.black_title if is_white else info.white_title
        if hasattr(self.config, 'auto_rematch') and self.config.auto_rematch.only_against_bots and opponent_title != 'BOT':
            return False
            
        # Check if we should only rematch against humans
        if hasattr(self.config, 'auto_rematch') and self.config.auto_rematch.only_against_humans and opponent_title == 'BOT':
            return False
            
        return True
        
    async def _create_rematch_challenge(self, info: Game_Information, chatter: Chatter) -> None:
        """Create a rematch challenge against the opponent."""
        # Get our color from the game info
        is_white = info.white_name.lower() == self.username.lower()
        opponent_username = info.black_name if is_white else info.white_name
        
        # Send rematch message if configured
        rematch_message = None
        if hasattr(self.config, 'auto_rematch'):
            rematch_message = self.config.auto_rematch.message
        if rematch_message:
            await self.api.send_chat_message(self.game_id, 'player', rematch_message)
        
        # Wait for configured delay
        delay = 2
        if hasattr(self.config, 'auto_rematch'):
            delay = self.config.auto_rematch.delay
        await asyncio.sleep(delay)
        
        # Use the dedicated rematch API which opens in the same tab
        success = await self.api.create_rematch(self.game_id)
        
        # Update rematch count
        self.rematch_count += 1
        
        # Update rematch count in game manager if available
        if self.game_manager:
            player_pair = frozenset([self.username.lower(), opponent_username.lower()])
            current_count = self.game_manager.rematch_counts.get(player_pair, 0)
            self.game_manager.rematch_counts[player_pair] = current_count + 1
            max_rematches = 3
            if hasattr(self.config, 'auto_rematch'):
                max_rematches = self.config.auto_rematch.max_rematches
            print(f'Rematch {current_count + 1}/{max_rematches} with {opponent_username}')
            
            # Set a flag in game manager to indicate we're in a rematch
            self.game_manager.in_rematch = True
            self.game_manager.rematch_opponent = opponent_username
        
        if success:
            print(f'Rematch created for game {self.game_id}')
        else:
            print(f'Failed to create rematch for game {self.game_id}, falling back to regular challenge')
            
            # Fall back to regular challenge if rematch API fails
            if not self.game_manager:
                print("Cannot create fallback rematch: game manager not available")
                return
                
            from botli_dataclasses import Challenge_Request
            from enums import Challenge_Color
            
            # Determine color for rematch
            alternate_colors = True
            if hasattr(self.config, 'auto_rematch'):
                alternate_colors = self.config.auto_rematch.alternate_colors
            if alternate_colors:
                color = Challenge_Color.BLACK if is_white else Challenge_Color.WHITE
            else:
                color = Challenge_Color.WHITE if is_white else Challenge_Color.BLACK
            
            # Create challenge request
            challenge_request = Challenge_Request(
                opponent_username=opponent_username,
                initial_time=info.initial_time_ms // 1000,
                increment=info.increment_ms // 1000,
                rated=info.rated,
                color=color,
                variant=info.variant,
                timeout=300
            )
            
            # Create challenge
            self.game_manager.request_challenge(challenge_request)
            
            print(f'Fallback rematch challenge against {opponent_username} added to the queue.')
