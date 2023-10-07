import os
import os.path
import subprocess
import sys

import yaml


def load_config(config_path: str) -> dict:
    with open(config_path, encoding='utf-8') as yml_input:
        try:
            config = yaml.safe_load(yml_input)
        except Exception as e:
            print(f'There appears to be a syntax problem with your {config_path}', file=sys.stderr)
            raise e

    if 'LICHESS_BOT_TOKEN' in os.environ:
        config['token'] = os.environ['LICHESS_BOT_TOKEN']

    _check_sections(config)
    _check_engines_sections(config['engines'])
    _check_syzygy_sections(config['syzygy'])
    _check_gaviota_sections(config['gaviota'])
    _check_opening_books_sections(config['opening_books'])
    _check_online_moves_sections(config['online_moves'])
    _check_offer_draw_sections(config['offer_draw'])
    _check_resign_sections(config['resign'])
    _check_matchmaking_sections(config['matchmaking'])
    _check_messages(config['messages'])
    _init_lists(config)
    _init_engines(config['engines'])
    _init_opening_books(config)
    config['version'] = _get_version()

    return config


def _check_sections(config: dict) -> None:
    # [section, type, error message]
    sections = [
        ['token', str, 'Section `token` must be a string wrapped in quotes.'],
        ['engines', dict, 'Section `engines` must be a dictionary with indented keys followed by colons.'],
        ['syzygy', dict, 'Section `syzygy` must be a dictionary with indented keys followed by colons.'],
        ['gaviota', dict, 'Section `gaviota` must be a dictionary with indented keys followed by colons.'],
        ['opening_books', dict, 'Section `opening_books` must be a dictionary with indented keys followed by colons.'],
        ['online_moves', dict, 'Section `online_moves` must be a dictionary with indented keys followed by colons.'],
        ['offer_draw', dict, 'Section `offer_draw` must be a dictionary with indented keys followed by colons.'],
        ['resign', dict, 'Section `resign` must be a dictionary with indented keys followed by colons.'],
        ['challenge', dict, 'Section `challenge` must be a dictionary with indented keys followed by colons.'],
        ['matchmaking', dict, 'Section `matchmaking` must be a dictionary with indented keys followed by colons.'],
        ['messages', dict, 'Section `messages` must be a dictionary with indented keys followed by colons.'],
        ['books', dict, 'Section `books` must be a dictionary with indented keys followed by colons.']]
    for section in sections:
        if section[0] not in config:
            raise RuntimeError(f'Your config does not have required section `{section[0]}`.')

        if not isinstance(config[section[0]], section[1]):
            raise TypeError(section[2])


def _check_engines_sections(engines_section: dict) -> None:
    engines_sections = [
        ['dir', str, '"dir" must be a string wrapped in quotes.'],
        ['name', str, '"name" must be a string wrapped in quotes.'],
        ['ponder', bool, '"ponder" must be a bool.'],
        ['use_syzygy', bool, '"use_syzygy" must be a bool.'],
        ['silence_stderr', bool, '"silence_stderr" must be a bool.'],
        ['uci_options', dict, '"uci_options" must be a dictionary with indented keys followed by colons.']]
    for key, settings in engines_section.items():
        for subsection in engines_sections:
            if subsection[0] not in settings:
                raise RuntimeError(f'Your "{key}" engine does not have required field `{subsection[0]}`.')

            if not isinstance(settings[subsection[0]], subsection[1]):
                raise TypeError(f'`engines` `{key}` subsection {subsection[2]}')


def _check_syzygy_sections(syzygy_section: dict) -> None:
    syzygy_sections = [
        ['enabled', bool, '"enabled" must be a bool.'],
        ['paths', list, '"paths" must be a list.'],
        ['max_pieces', int, '"max_pieces" must be an integer.'],
        ['instant_play', bool, '"instant_play" must be a bool.']]
    for subsection in syzygy_sections:
        if subsection[0] not in syzygy_section:
            raise RuntimeError(f'Your config does not have required `engine` `syzygy` subsection `{subsection[0]}`.')

        if not isinstance(syzygy_section[subsection[0]], subsection[1]):
            raise TypeError(f'`engine` `syzygy` subsection {subsection[2]}')

    if syzygy_section['enabled']:
        for path in syzygy_section['paths']:
            if not os.path.isdir(path):
                raise RuntimeError(f'Your syzygy directory "{path}" is not a directory.')


def _check_gaviota_sections(gaviota_section: dict) -> None:
    gaviota_sections = [
        ['enabled', bool, '"enabled" must be a bool.'],
        ['paths', list, '"paths" must be a list.'],
        ['max_pieces', int, '"max_pieces" must be an integer.']]
    for subsection in gaviota_sections:
        if subsection[0] not in gaviota_section:
            raise RuntimeError(f'Your config does not have required `engine` `gaviota` subsection `{subsection[0]}`.')

        if not isinstance(gaviota_section[subsection[0]], subsection[1]):
            raise TypeError(f'`engine` `gaviota` subsection {subsection[2]}')

    if gaviota_section['enabled']:
        for path in gaviota_section['paths']:
            if not os.path.isdir(path):
                raise RuntimeError(f'Your gaviota directory "{path}" is not a directory.')


def _check_opening_books_sections(opening_books_section: dict) -> None:
    opening_books_sections = [
        ['enabled', bool, '"enabled" must be a bool.'],
        ['priority', int, '"priority" must be an integer.'],
        ['books', dict, '"books" must be a dictionary with indented keys followed by colons.']]
    for subsection in opening_books_sections:
        if subsection[0] not in opening_books_section:
            raise RuntimeError(f'Your config does not have required `opening_books` subsection `{subsection[0]}`.')

        if not isinstance(opening_books_section[subsection[0]], subsection[1]):
            raise TypeError(f'`opening_books` subsection {subsection[2]}')


def _check_online_moves_sections(online_moves_section: dict) -> None:
    online_moves_sections = [
        ['opening_explorer', dict, '"opening_explorer" must be a dictionary with indented keys followed by colons.'],
        ['chessdb', dict, '"chessdb" must be a dictionary with indented keys followed by colons.'],
        ['lichess_cloud', dict, '"lichess_cloud" must be a dictionary with indented keys followed by colons.'],
        ['online_egtb', dict, '"online_egtb" must be a dictionary with indented keys followed by colons.']]
    for subsection in online_moves_sections:
        if subsection[0] not in online_moves_section:
            raise RuntimeError('Your config does not have required '
                               f'`engine` `online_moves` subsection `{subsection[0]}`.')

        if not isinstance(online_moves_section[subsection[0]], subsection[1]):
            raise TypeError(f'`engine` `online_moves` subsection {subsection[2]}')


def _check_offer_draw_sections(offer_draw_section: dict) -> None:
    offer_draw_sections = [
        ['enabled', bool, '"enabled" must be a bool.'],
        ['score', int, '"score" must be an integer.'],
        ['consecutive_moves', int, '"consecutive_moves" must be an integer.'],
        ['min_game_length', int, '"min_game_length" must be an integer.']]
    for subsection in offer_draw_sections:
        if subsection[0] not in offer_draw_section:
            raise RuntimeError(f'Your config does not have required `offer_draw` subsection `{subsection[0]}`.')

        if not isinstance(offer_draw_section[subsection[0]], subsection[1]):
            raise TypeError(f'`offer_draw` subsection {subsection[2]}')


def _check_resign_sections(resign_section: dict) -> None:
    resign_sections = [
        ['enabled', bool, '"enabled" must be a bool.'],
        ['score', int, '"score" must be an integer.'],
        ['consecutive_moves', int, '"consecutive_moves" must be an integer.']]
    for subsection in resign_sections:
        if subsection[0] not in resign_section:
            raise RuntimeError(f'Your config does not have required `resign` subsection `{subsection[0]}`.')

        if not isinstance(resign_section[subsection[0]], subsection[1]):
            raise TypeError(f'`resign` subsection {subsection[2]}')


def _check_matchmaking_sections(matchmaking_section: dict) -> None:
    matchmaking_sections = [
        ['delay', int, '"delay" must be an integer.'],
        ['timeout', int, '"timeout" must be an integer.'],
        ['types', dict, '"types" must be a dictionary with indented keys followed by colons.']]
    for subsection in matchmaking_sections:
        if subsection[0] not in matchmaking_section:
            raise RuntimeError(f'Your config does not have required `matchmaking` subsection `{subsection[0]}`.')

        if not isinstance(matchmaking_section[subsection[0]], subsection[1]):
            raise TypeError(f'`matchmaking` subsection {subsection[2]}')

    matchmaking_types_sections = [
        ['tc', str, '"tc" must be a string in initial_minutes+increment_seconds format.'],
        ['rated', bool, '"rated" must be a bool.'],
        ['variant', str, '"variant" must be a variant name from "https://lichess.org/variant".'],
        ['multiplier', int, '"multiplier" must be an integer.'],
        ['weight', int, '"weight" must be an integer.'],
        ['min_rating_diff', int, '"min_rating_diff" must be an integer.'],
        ['max_rating_diff', int, '"max_rating_diff" must be an integer.']]
    for matchmaking_type, matchmaking_options in matchmaking_section['types'].items():
        if not isinstance(matchmaking_options, dict):
            raise TypeError(f'`matchmaking` `types` subsection "{matchmaking_type}" must be a dictionary with '
                            'indented keys followed by colons.')

        if 'tc' not in matchmaking_options:
            raise RuntimeError(f'Your matchmaking type "{matchmaking_type}" does not have required `tc` field.')

        for key, value in matchmaking_options.items():
            for subsection in matchmaking_types_sections:
                if key == subsection[0]:
                    if not isinstance(value, subsection[1]):
                        raise TypeError(f'`matchmaking` `types` `{matchmaking_type}` field {subsection[2]}')

                    break
            else:
                raise RuntimeError(f'Unknown field "{key}" in matchmaking type "{matchmaking_type}".')


def _check_messages(messages_section: dict) -> None:
    for message_name, message in messages_section.items():
        if message.strip() == '!printeval':
            print(f'Ignoring message "{message_name}": "!printeval" is not allowed in messages.')
            messages_section[message_name] = None


def _init_lists(config: dict) -> None:
    if 'whitelist' in config:
        if not isinstance(config['whitelist'], list):
            raise TypeError('If uncommented, "whitelist" must be a list of usernames.')

        config['whitelist'] = [username.lower() for username in config['whitelist']]

    if 'blacklist' in config:
        if not isinstance(config['blacklist'], list):
            raise TypeError('If uncommented, "blacklist" must be a list of usernames.')

        config['blacklist'] = [username.lower() for username in config['blacklist']]


def _init_engines(engines_section: dict) -> None:
    for settings in engines_section.values():
        if not os.path.isdir(settings['dir']):
            raise RuntimeError(f'Your engine directory "{settings["dir"]}" is not a directory.')

        settings['path'] = os.path.join(settings['dir'], settings['name'])

        if not os.path.isfile(settings['path']):
            raise RuntimeError(f'The engine "{settings["path"]}" file does not exist.')

        if not os.access(settings['path'], os.X_OK):
            raise RuntimeError(f'The engine "{settings["path"]}" doesnt have execute (x) permission. '
                               f'Try: chmod +x {settings["path"]}')


def _init_opening_books(config: dict) -> None:
    if not config['opening_books']['enabled']:
        return

    opening_book_types_sections = [
        ['selection', str, '"selection" must be one of "weighted_random", "uniform_random" or "best_move".'],
        ['names', list, '"names" must be a list.']]
    for section, settings in config['opening_books']['books'].items():
        for subsection in opening_book_types_sections:
            if subsection[0] not in settings:
                raise RuntimeError(f'Your `opening_books` `books` `{section}` section'
                                   f'does not have required subsection `{subsection[0]}`.')

            if not isinstance(settings[subsection[0]], subsection[1]):
                raise TypeError(f'`opening_books` `books` `{section}` subsection {subsection[2]}')

    for settings in config['opening_books']['books'].values():
        for book_name in settings['names']:
            if book_name not in config['books']:
                raise RuntimeError(f'The book "{book_name}" is not defined in the books section.')

            if not os.path.isfile(config['books'][book_name]):
                raise RuntimeError(f'The book "{book_name}" at "{config["books"][book_name]}" does not exist.')

        settings['names'] = {book_name: config['books'][book_name] for book_name in settings['names']}


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
