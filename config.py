import os
import os.path
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

import yaml

from configs import (Auto_Rematch_Config, Books_Config, Challenge_Config, ChessDB_Config, Engine_Config, Gaviota_Config,
                     Lichess_Cloud_Config, Limit_Config, Matchmaking_Config, Matchmaking_Type_Config, Messages_Config,
                     Offer_Draw_Config, Online_EGTB_Config, Online_Moves_Config, Opening_Books_Config,
                     Opening_Explorer_Config, Resign_Config, Syzygy_Config)


@dataclass
class Config:
    url: str
    token: str
    engines: dict[str, Engine_Config]
    syzygy: dict[str, Syzygy_Config]
    gaviota: Gaviota_Config
    opening_books: Opening_Books_Config
    online_moves: Online_Moves_Config
    offer_draw: Offer_Draw_Config
    resign: Resign_Config
    challenge: Challenge_Config
    matchmaking: Matchmaking_Config
    messages: Messages_Config
    auto_rematch: Auto_Rematch_Config
    whitelist: list[str]
    blacklist: list[str]
    version: str

    @classmethod
    def from_yaml(cls, yaml_path: str) -> 'Config':
        with open(yaml_path, encoding='utf-8') as yaml_input:
            try:
                yaml_config = yaml.safe_load(yaml_input)
            except Exception as e:
                print(f'There appears to be a syntax problem with your {yaml_path}', file=sys.stderr)
                raise e

        if 'token' not in yaml_config and 'LICHESS_BOT_TOKEN' in os.environ:
            yaml_config['token'] = os.environ['LICHESS_BOT_TOKEN']

        cls._check_sections(yaml_config)

        engine_configs = cls._get_engine_configs(yaml_config['engines'])
        syzygy_config = cls._get_syzygy_configs(yaml_config['syzygy'])
        gaviota_config = cls._get_gaviota_config(yaml_config['gaviota'])
        opening_books_config = cls._get_opening_books_config(yaml_config)
        online_moves_config = cls._get_online_moves_config(yaml_config['online_moves'])
        offer_draw_config = cls._get_offer_draw_config(yaml_config['offer_draw'])
        resign_config = cls._get_resign_config(yaml_config['resign'])
        challenge_config = cls._get_challenge_config(yaml_config['challenge'])
        matchmaking_config = cls._get_matchmaking_config(yaml_config['matchmaking'])
        messages_config = cls._get_messages_config(yaml_config['messages'] or {})
        auto_rematch_config = cls._get_auto_rematch_config(yaml_config.get('auto_rematch', {}))
        whitelist = [string.lower() for string in yaml_config.get('whitelist') or []]
        blacklist = [string.lower() for string in yaml_config.get('blacklist') or []]

        return cls(yaml_config.get('url', 'https://lichess.org'),
                   yaml_config['token'],
                   engine_configs,
                   syzygy_config,
                   gaviota_config,
                   opening_books_config,
                   online_moves_config,
                   offer_draw_config,
                   resign_config,
                   challenge_config,
                   matchmaking_config,
                   messages_config,
                   auto_rematch_config,
                   whitelist,
                   blacklist,
                   cls._get_version())

    @staticmethod
    def _check_sections(config: dict[str, Any]) -> None:
        # [section, type, error message]
        sections = [
            ['token', str, 'Section `token` must be a string wrapped in quotes.'],
            ['engines', dict, 'Section `engines` must be a dictionary with indented keys followed by colons.'],
            ['syzygy', dict, 'Section `syzygy` must be a dictionary with indented keys followed by colons.'],
            ['gaviota', dict, 'Section `gaviota` must be a dictionary with indented keys followed by colons.'],
            ['opening_books', dict, ('Section `opening_books` must be a dictionary '
                                     'with indented keys followed by colons.')],
            ['online_moves', dict, ('Section `online_moves` must be a dictionary '
                                    'with indented keys followed by colons.')],
            ['offer_draw', dict, 'Section `offer_draw` must be a dictionary with indented keys followed by colons.'],
            ['resign', dict, 'Section `resign` must be a dictionary with indented keys followed by colons.'],
            ['challenge', dict, 'Section `challenge` must be a dictionary with indented keys followed by colons.'],
            ['matchmaking', dict, 'Section `matchmaking` must be a dictionary with indented keys followed by colons.'],
            ['messages', dict | None, 'Section `messages` must be a dictionary with indented keys followed by colons.'],
            ['auto_rematch', dict | None, 'Section `auto_rematch` must be a dictionary with indented keys followed by colons.'],
            ['books', dict, 'Section `books` must be a dictionary with indented keys followed by colons.']]
        for section in sections:
            if section[0] not in config:
                raise RuntimeError(f'Your config does not have required section `{section[0]}`.')

            if not isinstance(config[section[0]], section[1]):
                raise TypeError(section[2])

    @staticmethod
    def _get_engine_configs(engines_section: dict[str, dict[str, Any]]) -> dict[str, Engine_Config]:
        engines_sections = [
            ['dir', str, '"dir" must be a string wrapped in quotes.'],
            ['name', str, '"name" must be a string wrapped in quotes.'],
            ['ponder', bool, '"ponder" must be a bool.'],
            ['silence_stderr', bool, '"silence_stderr" must be a bool.'],
            ['move_overhead_multiplier', float, '"move_overhead_multiplier" must be a float.'],
            ['uci_options', dict | None, '"uci_options" must be a dictionary with indented keys followed by colons.'],
            ['limits', dict | None, '"limits" must be a dictionary with indented keys followed by colons.']]

        engine_configs: dict[str, Engine_Config] = {}
        for key, settings in engines_section.items():
            for subsection in engines_sections:
                if subsection[0] not in settings:
                    raise RuntimeError(f'Your "{key}" engine does not have required field `{subsection[0]}`.')

                if not isinstance(settings[subsection[0]], subsection[1]):
                    raise TypeError(f'`engines` `{key}` subsection {subsection[2]}')

            if not os.path.isdir(settings['dir']):
                raise RuntimeError(f'Your engine dir "{settings["dir"]}" is not a directory.')

            settings['path'] = os.path.join(settings['dir'], settings['name'])

            if not os.path.isfile(settings['path']):
                raise RuntimeError(f'The engine "{settings["path"]}" file does not exist.')

            if not os.access(settings['path'], os.X_OK):
                raise RuntimeError(f'The engine "{settings["path"]}" doesnt have execute (x) permission. '
                                   f'Try: chmod +x {settings["path"]}')

            limits_settings = settings['limits'] or {}

            engine_configs[key] = Engine_Config(settings['path'],
                                                settings['ponder'],
                                                settings['silence_stderr'],
                                                settings['move_overhead_multiplier'],
                                                settings['uci_options'] or {},
                                                Limit_Config(limits_settings.get('time'),
                                                             limits_settings.get('depth'),
                                                             limits_settings.get('nodes')))

        return engine_configs

    @staticmethod
    def _get_syzygy_configs(syzygy_section: dict[str, dict[str, Any]]) -> dict[str, Syzygy_Config]:
        syzygy_sections = [
            ['enabled', bool, '"enabled" must be a bool.'],
            ['paths', list, '"paths" must be a list.'],
            ['max_pieces', int, '"max_pieces" must be an integer.'],
            ['instant_play', bool, '"instant_play" must be a bool.']]

        syzygy_configs: dict[str, Syzygy_Config] = {}
        for key, settings in syzygy_section.items():
            for subsection in syzygy_sections:
                if subsection[0] not in settings:
                    raise RuntimeError('Your config does not have required '
                                       f'`syzygy` `{key}` subsection `{subsection[0]}`.')

                if not isinstance(settings[subsection[0]], subsection[1]):
                    raise TypeError(f'`syzygy` `{key}` subsection {subsection[2]}')

            if not settings['enabled']:
                syzygy_configs[key] = Syzygy_Config(False, [], 0, False)
                continue

            for path in settings['paths']:
                if not os.path.isdir(path):
                    raise RuntimeError(f'Your {key} syzygy path "{path}" is not a directory.')

            syzygy_configs[key] = Syzygy_Config(settings['enabled'],
                                                settings['paths'],
                                                settings['max_pieces'],
                                                settings['instant_play'])

        return syzygy_configs

    @staticmethod
    def _get_gaviota_config(gaviota_section: dict[str, Any]) -> Gaviota_Config:
        gaviota_sections = [
            ['enabled', bool, '"enabled" must be a bool.'],
            ['paths', list, '"paths" must be a list.'],
            ['max_pieces', int, '"max_pieces" must be an integer.']]

        for subsection in gaviota_sections:
            if subsection[0] not in gaviota_section:
                raise RuntimeError(f'Your config does not have required `gaviota` subsection `{subsection[0]}`.')

            if not isinstance(gaviota_section[subsection[0]], subsection[1]):
                raise TypeError(f'`gaviota` subsection {subsection[2]}')

        if gaviota_section['enabled']:
            for path in gaviota_section['paths']:
                if not os.path.isdir(path):
                    raise RuntimeError(f'Your gaviota directory "{path}" is not a directory.')

        return Gaviota_Config(gaviota_section['enabled'], gaviota_section['paths'], gaviota_section['max_pieces'])

    @staticmethod
    def _get_opening_books_config(config: dict[str, Any]) -> Opening_Books_Config:
        opening_books_sections = [
            ['enabled', bool, '"enabled" must be a bool.'],
            ['priority', int, '"priority" must be an integer.'],
            ['books', dict, '"books" must be a dictionary with indented keys followed by colons.']]

        for subsection in opening_books_sections:
            if subsection[0] not in config['opening_books']:
                raise RuntimeError(f'Your config does not have required `opening_books` subsection `{subsection[0]}`.')

            if not isinstance(config['opening_books'][subsection[0]], subsection[1]):
                raise TypeError(f'`opening_books` subsection {subsection[2]}')

        if not config['opening_books']['enabled']:
            return Opening_Books_Config(False, 0, None, {})

        opening_book_types_sections = [
            ['selection', str, '"selection" must be one of "weighted_random", "uniform_random" or "best_move".'],
            ['names', list, '"names" must be a list of book names.']]

        books: dict[str, Books_Config] = {}
        for section, settings in config['opening_books']['books'].items():
            for subsection in opening_book_types_sections:
                if subsection[0] not in settings:
                    raise RuntimeError(f'Your `opening_books` `books` `{section}` section'
                                       f'does not have required field `{subsection[0]}`.')

                if not isinstance(settings[subsection[0]], subsection[1]):
                    raise TypeError(f'`opening_books` `books` `{section}` field {subsection[2]}')

            names: dict[str, str] = {}
            for book_name in settings['names']:
                if book_name not in config['books']:
                    raise RuntimeError(f'The book "{book_name}" is not defined in the books section.')

                if not os.path.isfile(config['books'][book_name]):
                    raise RuntimeError(f'The book "{book_name}" at "{config["books"][book_name]}" does not exist.')

                names[book_name] = config['books'][book_name]

            books[section] = Books_Config(settings['selection'], settings.get('max_depth'), names)

        return Opening_Books_Config(config['opening_books']['enabled'],
                                    config['opening_books']['priority'],
                                    config['opening_books'].get('read_learn'),
                                    books)

    @staticmethod
    def _get_opening_explorer_config(opening_explorer_section: dict[str, Any]) -> Opening_Explorer_Config:
        opening_explorer_sections = [
            ['enabled', bool, '"enabled" must be a bool.'],
            ['priority', int, '"priority" must be an integer.'],
            ['only_without_book', bool, '"only_without_book" must be a bool.'],
            ['use_for_variants', bool, '"use_for_variants" must be a bool.'],
            ['min_time', int, '"min_time" must be an integer.'],
            ['timeout', int, '"timeout" must be an integer.'],
            ['min_games', int, '"min_games" must be an integer.'],
            ['only_with_wins', bool, '"only_with_wins" must be a bool.'],
            ['selection', str, '"selection" must be "performance" or "win_rate".'],
            ['anti', bool, '"anti" must be a bool.']]

        for subsection in opening_explorer_sections:
            if subsection[0] not in opening_explorer_section:
                raise RuntimeError('Your config does not have required '
                                   f'`online_moves` `opening_explorer` field `{subsection[0]}`.')

            if not isinstance(opening_explorer_section[subsection[0]], subsection[1]):
                raise TypeError(f'`online_moves` `opening_explorer` field {subsection[2]}')

        return Opening_Explorer_Config(opening_explorer_section['enabled'],
                                       opening_explorer_section['priority'],
                                       opening_explorer_section['only_without_book'],
                                       opening_explorer_section['use_for_variants'],
                                       opening_explorer_section['min_time'],
                                       opening_explorer_section['timeout'],
                                       opening_explorer_section['min_games'],
                                       opening_explorer_section['only_with_wins'],
                                       opening_explorer_section['selection'],
                                       opening_explorer_section['anti'],
                                       opening_explorer_section.get('max_depth'),
                                       opening_explorer_section.get('max_moves'))

    @staticmethod
    def _get_lichess_cloud_config(lichess_cloud_section: dict[str, Any]) -> Lichess_Cloud_Config:
        lichess_cloud_sections = [
            ['enabled', bool, '"enabled" must be a bool.'],
            ['priority', int, '"priority" must be an integer.'],
            ['only_without_book', bool, '"only_without_book" must be a bool.'],
            ['min_eval_depth', int, '"min_eval_depth" must be an integer.'],
            ['min_time', int, '"min_time" must be an integer.'],
            ['timeout', int, '"timeout" must be an integer.']]

        for subsection in lichess_cloud_sections:
            if subsection[0] not in lichess_cloud_section:
                raise RuntimeError('Your config does not have required '
                                   f'`online_moves` `lichess_cloud` field `{subsection[0]}`.')

            if not isinstance(lichess_cloud_section[subsection[0]], subsection[1]):
                raise TypeError(f'`online_moves` `lichess_cloud` field {subsection[2]}')

        return Lichess_Cloud_Config(lichess_cloud_section['enabled'],
                                    lichess_cloud_section['priority'],
                                    lichess_cloud_section['only_without_book'],
                                    lichess_cloud_section['min_eval_depth'],
                                    lichess_cloud_section['min_time'],
                                    lichess_cloud_section['timeout'],
                                    lichess_cloud_section.get('max_depth'),
                                    lichess_cloud_section.get('max_moves'))

    @staticmethod
    def _get_chessdb_config(chessdb_section: dict[str, Any]) -> ChessDB_Config:
        chessdb_sections = [
            ['enabled', bool, '"enabled" must be a bool.'],
            ['priority', int, '"priority" must be an integer.'],
            ['only_without_book', bool, '"only_without_book" must be a bool.'],
            ['min_candidates', int, '"min_candidates" must be an integer.'],
            ['min_time', int, '"min_time" must be an integer.'],
            ['timeout', int, '"timeout" must be an integer.'],
            ['selection', str, '"selection" must be one of "optimal", "best" or "good".']]

        for subsection in chessdb_sections:
            if subsection[0] not in chessdb_section:
                raise RuntimeError('Your config does not have required '
                                   f'`online_moves` `chessdb` field `{subsection[0]}`.')

            if not isinstance(chessdb_section[subsection[0]], subsection[1]):
                raise TypeError(f'`online_moves` `chessdb` field {subsection[2]}')

        return ChessDB_Config(chessdb_section['enabled'],
                              chessdb_section['priority'],
                              chessdb_section['only_without_book'],
                              chessdb_section['min_candidates'],
                              chessdb_section['min_time'],
                              chessdb_section['timeout'],
                              chessdb_section['selection'],
                              chessdb_section.get('max_depth'),
                              chessdb_section.get('max_moves'))

    @staticmethod
    def _get_online_egtb_config(online_egtb_section: dict[str, Any]) -> Online_EGTB_Config:
        online_egtb_sections = [
            ['enabled', bool, '"enabled" must be a bool.'],
            ['min_time', int, '"min_time" must be an integer.'],
            ['timeout', int, '"timeout" must be an integer.']]

        for subsection in online_egtb_sections:
            if subsection[0] not in online_egtb_section:
                raise RuntimeError('Your config does not have required '
                                   f'`online_moves` `online_egtb` field `{subsection[0]}`.')

            if not isinstance(online_egtb_section[subsection[0]], subsection[1]):
                raise TypeError(f'`online_moves` `online_egtb` field {subsection[2]}')

        return Online_EGTB_Config(online_egtb_section['enabled'],
                                  online_egtb_section['min_time'],
                                  online_egtb_section['timeout'])

    @staticmethod
    def _get_online_moves_config(online_moves_section: dict[str, dict[str, Any]]) -> Online_Moves_Config:
        online_moves_sections = [
            ['opening_explorer', dict, ('"opening_explorer" must be a dictionary '
                                        'with indented keys followed by colons.')],
            ['chessdb', dict, '"chessdb" must be a dictionary with indented keys followed by colons.'],
            ['lichess_cloud', dict, '"lichess_cloud" must be a dictionary with indented keys followed by colons.'],
            ['online_egtb', dict, '"online_egtb" must be a dictionary with indented keys followed by colons.']]

        for subsection in online_moves_sections:
            if subsection[0] not in online_moves_section:
                raise RuntimeError('Your config does not have required '
                                   f'`online_moves` subsection `{subsection[0]}`.')

            if not isinstance(online_moves_section[subsection[0]], subsection[1]):
                raise TypeError(f'`online_moves` subsection {subsection[2]}')

        return Online_Moves_Config(Config._get_opening_explorer_config(online_moves_section['opening_explorer']),
                                   Config._get_lichess_cloud_config(online_moves_section['lichess_cloud']),
                                   Config._get_chessdb_config(online_moves_section['chessdb']),
                                   Config._get_online_egtb_config(online_moves_section['online_egtb']))

    @staticmethod
    def _get_offer_draw_config(offer_draw_section: dict[str, Any]) -> Offer_Draw_Config:
        offer_draw_sections = [
            ['enabled', bool, '"enabled" must be a bool.'],
            ['score', int, '"score" must be an integer.'],
            ['consecutive_moves', int, '"consecutive_moves" must be an integer.'],
            ['min_game_length', int, '"min_game_length" must be an integer.'],
            ['against_humans', bool, '"against_humans" must be a bool.']]

        for subsection in offer_draw_sections:
            if subsection[0] not in offer_draw_section:
                raise RuntimeError(f'Your config does not have required `offer_draw` subsection `{subsection[0]}`.')

            if not isinstance(offer_draw_section[subsection[0]], subsection[1]):
                raise TypeError(f'`offer_draw` subsection {subsection[2]}')

        return Offer_Draw_Config(offer_draw_section['enabled'],
                                 offer_draw_section['score'],
                                 offer_draw_section['consecutive_moves'],
                                 offer_draw_section['min_game_length'],
                                 offer_draw_section['against_humans'])

    @staticmethod
    def _get_resign_config(resign_section: dict[str, Any]) -> Resign_Config:
        resign_sections = [
            ['enabled', bool, '"enabled" must be a bool.'],
            ['score', int, '"score" must be an integer.'],
            ['consecutive_moves', int, '"consecutive_moves" must be an integer.'],
            ['against_humans', bool, '"against_humans" must be a bool.']]

        for subsection in resign_sections:
            if subsection[0] not in resign_section:
                raise RuntimeError(f'Your config does not have required `resign` subsection `{subsection[0]}`.')

            if not isinstance(resign_section[subsection[0]], subsection[1]):
                raise TypeError(f'`resign` subsection {subsection[2]}')

        return Resign_Config(resign_section['enabled'],
                             resign_section['score'],
                             resign_section['consecutive_moves'],
                             resign_section['against_humans'])

    @staticmethod
    def _get_challenge_config(challenge_section: dict[str, Any]) -> Challenge_Config:
        challenge_sections = [
            ['concurrency', int, '"concurrency" must be an integer.'],
            ['bullet_with_increment_only', bool, '"bullet_with_increment_only" must be a bool.'],
            ['variants', list, '"variants" must be a list of variants.'],
            ['time_controls', list | None, '"time_controls" must be a list of speeds or time controls.'],
            ['bot_modes', list | None, '"bot_modes" must be a list of game modes.'],
            ['human_modes', list | None, '"human_modes" must be a list of game modes.']]

        for subsection in challenge_sections:
            if subsection[0] not in challenge_section:
                raise RuntimeError(f'Your config does not have required `challenge` subsection `{subsection[0]}`.')

            if not isinstance(challenge_section[subsection[0]], subsection[1]):
                raise TypeError(f'`challenge` subsection {subsection[2]}')

        return Challenge_Config(challenge_section['concurrency'],
                                challenge_section['bullet_with_increment_only'],
                                challenge_section.get('min_increment'),
                                challenge_section.get('max_increment'),
                                challenge_section.get('min_initial'),
                                challenge_section.get('max_initial'),
                                challenge_section['variants'],
                                challenge_section['time_controls'] or [],
                                challenge_section['bot_modes'] or [],
                                challenge_section['human_modes'] or [])

    @staticmethod
    def _get_matchmaking_config(matchmaking_section: dict[str, Any]) -> Matchmaking_Config:
        matchmaking_sections = [
            ['delay', int, '"delay" must be an integer.'],
            ['timeout', int, '"timeout" must be an integer.'],
            ['selection', str, '"selection" must be "weighted_random" or "sequential".'],
            ['types', dict, '"types" must be a dictionary with indented keys followed by colons.']]

        for subsection in matchmaking_sections:
            if subsection[0] not in matchmaking_section:
                raise RuntimeError(f'Your config does not have required `matchmaking` subsection `{subsection[0]}`.')

            if not isinstance(matchmaking_section[subsection[0]], subsection[1]):
                raise TypeError(f'`matchmaking` subsection {subsection[2]}')

        types: dict[str, Matchmaking_Type_Config] = {}
        for matchmaking_type, matchmaking_options in matchmaking_section['types'].items():
            if not isinstance(matchmaking_options, dict):
                raise TypeError(f'`matchmaking` `types` subsection "{matchmaking_type}" must be a dictionary with '
                                'indented keys followed by colons.')

            if 'tc' not in matchmaking_options:
                raise RuntimeError(f'Your matchmaking type "{matchmaking_type}" does not have required `tc` field.')

            if not isinstance(matchmaking_options['tc'], str):
                raise TypeError(f'`matchmaking` `types` `{matchmaking_type}` field `tc` must be a string in '
                                'initial_minutes+increment_seconds format.')

            types[matchmaking_type] = Matchmaking_Type_Config(matchmaking_options['tc'],
                                                              matchmaking_options.get('rated'),
                                                              matchmaking_options.get('variant'),
                                                              matchmaking_options.get('weight'),
                                                              matchmaking_options.get('multiplier'),
                                                              matchmaking_options.get('min_rating_diff'),
                                                              matchmaking_options.get('max_rating_diff'))

        return Matchmaking_Config(matchmaking_section['delay'],
                                  matchmaking_section['timeout'],
                                  matchmaking_section['selection'],
                                  types)

    @staticmethod
    def _get_messages_config(messages_section: dict[str, str]) -> Messages_Config:
        messages_sections = [
            ['greeting', str, '"greeting" must be a string wrapped in quotes.'],
            ['goodbye', str, '"goodbye" must be a string wrapped in quotes.'],
            ['greeting_spectators', str, '"greeting_spectators" must be a string wrapped in quotes.'],
            ['goodbye_spectators', str, '"goodbye_spectators" must be a string wrapped in quotes.']]

        for subsection in messages_sections:
            if subsection[0] in messages_section:
                if not isinstance(messages_section[subsection[0]], subsection[1]):
                    raise TypeError(f'`messages` subsection {subsection[2]}')

                if messages_section[subsection[0]].strip() == '!printeval':
                    print(f'Ignoring message "{subsection[0]}": "!printeval" is not allowed in messages.')
                    del messages_section[messages_section[subsection[0]]]

        return Messages_Config(messages_section.get('greeting'),
                               messages_section.get('goodbye'),
                               messages_section.get('greeting_spectators'),
                               messages_section.get('goodbye_spectators'))

    @staticmethod
    def _get_auto_rematch_config(auto_rematch_section: dict[str, Any]) -> Auto_Rematch_Config:
        # If auto_rematch section is empty or not present, return default config
        if not auto_rematch_section:
            return Auto_Rematch_Config(False, 3, 2, None, True, False, False, False, False)
            
        auto_rematch_sections = [
            ['enabled', bool, '"enabled" must be a bool.'],
            ['max_rematches', int, '"max_rematches" must be an integer.'],
            ['delay', int, '"delay" must be an integer.'],
            ['alternate_colors', bool, '"alternate_colors" must be a bool.'],
            ['only_after_wins', bool, '"only_after_wins" must be a bool.'],
            ['only_after_losses', bool, '"only_after_losses" must be a bool.'],
            ['only_against_bots', bool, '"only_against_bots" must be a bool.'],
            ['only_against_humans', bool, '"only_against_humans" must be a bool.']]

        for subsection in auto_rematch_sections:
            if subsection[0] in auto_rematch_section and not isinstance(auto_rematch_section[subsection[0]], subsection[1]):
                raise TypeError(f'`auto_rematch` subsection {subsection[2]}')

        return Auto_Rematch_Config(
            auto_rematch_section.get('enabled', False),
            auto_rematch_section.get('max_rematches', 3),
            auto_rematch_section.get('delay', 2),
            auto_rematch_section.get('message'),
            auto_rematch_section.get('alternate_colors', True),
            auto_rematch_section.get('only_after_wins', False),
            auto_rematch_section.get('only_after_losses', False),
            auto_rematch_section.get('only_against_bots', False),
            auto_rematch_section.get('only_against_humans', False)
        )

    @staticmethod
    def _get_version() -> str:
        try:
            output = subprocess.check_output(['git', 'show', '-s', '--date=format:%Y%m%d',
                                              '--format=%cd', 'HEAD'], stderr=subprocess.DEVNULL)
            commit_date = output.decode('utf-8').strip()
            output = subprocess.check_output(['git', 'rev-parse', 'HEAD'], stderr=subprocess.DEVNULL)
            commit_SHA = output.decode('utf-8').strip()[:7]
            return f'{commit_date}-{commit_SHA}'
        except (FileNotFoundError, subprocess.CalledProcessError):
            return 'nogit'
