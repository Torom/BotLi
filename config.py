import os
import os.path
import sys

import yaml


def load_config() -> dict:
    with open('config.yml') as stream:
        try:
            CONFIG = yaml.safe_load(stream)
        except Exception as e:
            print('There appears to be a syntax problem with your config.yml', file=sys.stderr)
            raise e

        # [section, type, error message]
        sections = [
            ['token', str, 'Section `token` must be a string wrapped in quotes.'],
            ['engine', dict, 'Section `engine` must be a dictionary with indented keys followed by colons..'],
            ['challenge', dict, 'Section `challenge` must be a dictionary with indented keys followed by colons..'],
            ['matchmaking', dict, 'Section `matchmaking` must be a dictionary with indented keys followed by colons..']]
        for section in sections:
            if section[0] not in CONFIG:
                raise Exception(f'Your config.yml does not have required section `{section[0]}`.')
            elif not isinstance(CONFIG[section[0]], section[1]):
                raise Exception(section[2])

        engine_sections = [['dir', str, '"dir" must be a string wrapped in quotes.'],
                           ['name', str, '"name" must be a string wrapped in quotes.']]
        for subsection in engine_sections:
            if subsection[0] not in CONFIG['engine']:
                raise Exception(f'Your config.yml does not have required `engine` subsection `{subsection[0]}`.')
            if not isinstance(CONFIG['engine'][subsection[0]], subsection[1]):
                raise Exception(f'`engine` subsection {subsection[2]}')

        if not os.path.isdir(CONFIG['engine']['dir']):
            raise Exception(f'Your engine directory "{CONFIG["engine"]["dir"]}" is not a directory.')

        CONFIG['engine']['path'] = os.path.join(CONFIG['engine']['dir'], CONFIG['engine']['name'])

        if not os.path.isfile(CONFIG['engine']['path']):
            raise Exception(f'The engine "{CONFIG["engine"]["path"]}" file does not exist.')

        if not os.access(CONFIG['engine']['path'], os.X_OK):
            raise Exception(
                f'The engine "{CONFIG["engine"]["path"]}" doesnt have execute (x) permission. Try: chmod +x {CONFIG["engine"]["path"]}')

        if CONFIG['engine']['polyglot']['enabled']:
            for key, book in CONFIG['engine']['polyglot']['books'].items():
                if book:
                    if not os.path.isfile(CONFIG['books'][book]):
                        raise Exception(f'The book "{book}" at "{CONFIG["books"][book]}" does not exist.')
                    CONFIG['engine']['polyglot']['books'][key] = CONFIG['books'][book]

        if CONFIG['engine']['pybook']['enabled']:
            if not os.path.isfile(CONFIG['engine']['pybook']['book']):
                raise Exception(f'The PyBook at "{CONFIG["engine"]["pybook"]["book"]}" does not exist.')

    return CONFIG
