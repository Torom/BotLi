import os
import os.path
import subprocess
import sys
from dataclasses import dataclass
from types import UnionType
from typing import Any

import yaml

from configs import (
    BooksConfig,
    ChallengeConfig,
    ChessDBConfig,
    EngineConfig,
    GaviotaConfig,
    LichessCloudConfig,
    LimitConfig,
    MatchmakingConfig,
    MatchmakingTypeConfig,
    MessagesConfig,
    OfferDrawConfig,
    OnlineEGTBConfig,
    OnlineMovesConfig,
    OpeningBooksConfig,
    OpeningExplorerConfig,
    ResignConfig,
    SyzygyConfig,
)


@dataclass
class Config:
    url: str
    token: str
    engines: dict[str, EngineConfig]
    syzygy: dict[str, SyzygyConfig]
    gaviota: GaviotaConfig
    opening_books: OpeningBooksConfig
    online_moves: OnlineMovesConfig
    offer_draw: OfferDrawConfig
    resign: ResignConfig
    challenge: ChallengeConfig
    matchmaking: MatchmakingConfig
    messages: MessagesConfig
    whitelist: list[str]
    blacklist: list[str]
    online_blacklists: list[str]
    version: str

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "Config":
        with open(yaml_path, encoding="utf-8") as yaml_input:
            try:
                yaml_config = yaml.safe_load(yaml_input)
            except Exception as e:
                print(f"There appears to be a syntax problem with your {yaml_path}", file=sys.stderr)
                raise e

        if not yaml_config.get("token") and "LICHESS_BOT_TOKEN" in os.environ:
            yaml_config["token"] = os.environ["LICHESS_BOT_TOKEN"]

        cls._check_sections(yaml_config)

        engine_configs = cls._get_engine_configs(yaml_config["engines"])
        syzygy_config = cls._get_syzygy_configs(yaml_config["syzygy"])
        gaviota_config = cls._get_gaviota_config(yaml_config["gaviota"])
        opening_books_config = cls._get_opening_books_config(yaml_config)
        online_moves_config = cls._get_online_moves_config(yaml_config["online_moves"])
        offer_draw_config = cls._get_offer_draw_config(yaml_config["offer_draw"])
        resign_config = cls._get_resign_config(yaml_config["resign"])
        challenge_config = cls._get_challenge_config(yaml_config["challenge"])
        matchmaking_config = cls._get_matchmaking_config(yaml_config["matchmaking"])
        messages_config = cls._get_messages_config(yaml_config["messages"] or {})
        whitelist = [username.lower() for username in yaml_config.get("whitelist") or []]
        blacklist = [username.lower() for username in yaml_config.get("blacklist") or []]
        online_blacklists = yaml_config.get("online_blacklists") or []

        return cls(
            yaml_config.get("url", "https://lichess.org"),
            yaml_config["token"],
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
            whitelist,
            blacklist,
            online_blacklists,
            cls._get_version(),
        )

    @staticmethod
    def _validate_config_section(
        config: dict[str, Any], section_name: str, required_fields: list[tuple[str, type | UnionType, str]]
    ) -> None:
        for field_name, field_type, error_msg in required_fields:
            if field_name not in config:
                raise RuntimeError(f"Your config does not have required `{section_name}` subsection `{field_name}`.")

            if not isinstance(config[field_name], field_type):
                raise TypeError(f"`{section_name}` subsection {error_msg}")

    @staticmethod
    def _check_sections(config: dict[str, Any]) -> None:
        sections: list[tuple[str, type | UnionType, str]] = [
            ("token", str, "Section `token` must be a string wrapped in quotes."),
            ("engines", dict, "Section `engines` must be a dictionary with indented keys followed by colons."),
            ("syzygy", dict, "Section `syzygy` must be a dictionary with indented keys followed by colons."),
            ("gaviota", dict, "Section `gaviota` must be a dictionary with indented keys followed by colons."),
            (
                "opening_books",
                dict,
                ("Section `opening_books` must be a dictionary with indented keys followed by colons."),
            ),
            (
                "online_moves",
                dict,
                ("Section `online_moves` must be a dictionary with indented keys followed by colons."),
            ),
            ("offer_draw", dict, "Section `offer_draw` must be a dictionary with indented keys followed by colons."),
            ("resign", dict, "Section `resign` must be a dictionary with indented keys followed by colons."),
            ("challenge", dict, "Section `challenge` must be a dictionary with indented keys followed by colons."),
            ("matchmaking", dict, "Section `matchmaking` must be a dictionary with indented keys followed by colons."),
            ("messages", dict | None, "Section `messages` must be a dictionary with indented keys followed by colons."),
            ("whitelist", list | None, "Section `whitelist` must be a list."),
            ("blacklist", list | None, "Section `blacklist` must be a list."),
            ("online_blacklists", list | None, "Section `online_blacklists` must be a list."),
            ("books", dict, "Section `books` must be a dictionary with indented keys followed by colons."),
        ]

        Config._validate_config_section(config, "config", sections)

    @staticmethod
    def _get_engine_configs(engines_section: dict[str, dict[str, Any]]) -> dict[str, EngineConfig]:
        engines_sections: list[tuple[str, type | UnionType, str]] = [
            ("dir", str, '"dir" must be a string wrapped in quotes.'),
            ("name", str, '"name" must be a string wrapped in quotes.'),
            ("ponder", bool, '"ponder" must be a bool.'),
            ("silence_stderr", bool, '"silence_stderr" must be a bool.'),
            ("move_overhead_multiplier", float, '"move_overhead_multiplier" must be a float.'),
            ("uci_options", dict | None, '"uci_options" must be a dictionary with indented keys followed by colons.'),
            ("limits", dict | None, '"limits" must be a dictionary with indented keys followed by colons.'),
        ]

        engine_configs: dict[str, EngineConfig] = {}
        for key, settings in engines_section.items():
            Config._validate_config_section(settings, f"engine.{key}", engines_sections)

            if not os.path.isdir(settings["dir"]):
                raise RuntimeError(f'Your engine dir "{settings["dir"]}" is not a directory.')

            settings["path"] = os.path.join(settings["dir"], settings["name"])

            if not os.path.isfile(settings["path"]):
                raise RuntimeError(f'The engine "{settings["path"]}" file does not exist.')

            if not os.access(settings["path"], os.X_OK):
                raise RuntimeError(
                    f'The engine "{settings["path"]}" doesnt have execute (x) permission. '
                    f"Try: chmod +x {settings['path']}"
                )

            limits_settings = settings["limits"] or {}

            engine_configs[key] = EngineConfig(
                settings["path"],
                settings["ponder"],
                settings["silence_stderr"],
                settings["move_overhead_multiplier"],
                settings["uci_options"] or {},
                LimitConfig(limits_settings.get("time"), limits_settings.get("depth"), limits_settings.get("nodes")),
            )

        return engine_configs

    @staticmethod
    def _get_syzygy_configs(syzygy_section: dict[str, dict[str, Any]]) -> dict[str, SyzygyConfig]:
        syzygy_sections: list[tuple[str, type | UnionType, str]] = [
            ("enabled", bool, '"enabled" must be a bool.'),
            ("paths", list, '"paths" must be a list.'),
            ("max_pieces", int, '"max_pieces" must be an integer.'),
            ("instant_play", bool, '"instant_play" must be a bool.'),
        ]

        syzygy_configs: dict[str, SyzygyConfig] = {}
        for key, settings in syzygy_section.items():
            Config._validate_config_section(settings, f"syzygy.{key}", syzygy_sections)

            if not settings["enabled"]:
                syzygy_configs[key] = SyzygyConfig(False, [], 0, False)
                continue

            for path in settings["paths"]:
                if not os.path.isdir(path):
                    raise RuntimeError(f'Your {key} syzygy path "{path}" is not a directory.')

            syzygy_configs[key] = SyzygyConfig(
                settings["enabled"], settings["paths"], settings["max_pieces"], settings["instant_play"]
            )

        return syzygy_configs

    @staticmethod
    def _get_gaviota_config(gaviota_section: dict[str, Any]) -> GaviotaConfig:
        gaviota_sections: list[tuple[str, type | UnionType, str]] = [
            ("enabled", bool, '"enabled" must be a bool.'),
            ("paths", list, '"paths" must be a list.'),
            ("max_pieces", int, '"max_pieces" must be an integer.'),
        ]

        Config._validate_config_section(gaviota_section, "gaviota", gaviota_sections)

        if gaviota_section["enabled"]:
            for path in gaviota_section["paths"]:
                if not os.path.isdir(path):
                    raise RuntimeError(f'Your gaviota directory "{path}" is not a directory.')

        return GaviotaConfig(gaviota_section["enabled"], gaviota_section["paths"], gaviota_section["max_pieces"])

    @staticmethod
    def _get_opening_books_config(config: dict[str, Any]) -> OpeningBooksConfig:
        opening_books_sections: list[tuple[str, type | UnionType, str]] = [
            ("enabled", bool, '"enabled" must be a bool.'),
            ("priority", int, '"priority" must be an integer.'),
            ("books", dict, '"books" must be a dictionary with indented keys followed by colons.'),
        ]

        Config._validate_config_section(config["opening_books"], "opening_books", opening_books_sections)

        if not config["opening_books"]["enabled"]:
            return OpeningBooksConfig(False, 0, None, {})

        opening_book_types_sections: list[tuple[str, type | UnionType, str]] = [
            ("selection", str, '"selection" must be one of "weighted_random", "uniform_random" or "best_move".'),
            ("names", list, '"names" must be a list of book names.'),
        ]

        books: dict[str, BooksConfig] = {}
        for section, settings in config["opening_books"]["books"].items():
            Config._validate_config_section(settings, f"opening_books.{section}", opening_book_types_sections)

            names: dict[str, str] = {}
            for book_name in settings["names"]:
                if book_name not in config["books"]:
                    raise RuntimeError(f'The book "{book_name}" is not defined in the books section.')

                if not os.path.isfile(config["books"][book_name]):
                    raise RuntimeError(f'The book "{book_name}" at "{config["books"][book_name]}" does not exist.')

                names[book_name] = config["books"][book_name]

            books[section] = BooksConfig(
                settings["selection"],
                settings.get("max_depth"),
                settings.get("max_moves"),
                settings.get("allow_repetitions"),
                names,
            )

        return OpeningBooksConfig(
            config["opening_books"]["enabled"],
            config["opening_books"]["priority"],
            config["opening_books"].get("read_learn"),
            books,
        )

    @staticmethod
    def _get_opening_explorer_config(opening_explorer_section: dict[str, Any]) -> OpeningExplorerConfig:
        opening_explorer_sections: list[tuple[str, type | UnionType, str]] = [
            ("enabled", bool, '"enabled" must be a bool.'),
            ("priority", int, '"priority" must be an integer.'),
            ("only_without_book", bool, '"only_without_book" must be a bool.'),
            ("use_for_variants", bool, '"use_for_variants" must be a bool.'),
            ("allow_repetitions", bool, '"allow_repetitions" must be a bool.'),
            ("min_time", int, '"min_time" must be an integer.'),
            ("timeout", int, '"timeout" must be an integer.'),
            ("min_games", int, '"min_games" must be an integer.'),
            ("only_with_wins", bool, '"only_with_wins" must be a bool.'),
            ("selection", str, '"selection" must be "performance" or "win_rate".'),
            ("anti", bool, '"anti" must be a bool.'),
        ]

        Config._validate_config_section(
            opening_explorer_section, "online_moves.opening_explorer", opening_explorer_sections
        )

        return OpeningExplorerConfig(
            opening_explorer_section["enabled"],
            opening_explorer_section["priority"],
            opening_explorer_section.get("player"),
            opening_explorer_section["only_without_book"],
            opening_explorer_section["use_for_variants"],
            opening_explorer_section["allow_repetitions"],
            opening_explorer_section["min_time"],
            opening_explorer_section["timeout"],
            opening_explorer_section["min_games"],
            opening_explorer_section["only_with_wins"],
            opening_explorer_section["selection"],
            opening_explorer_section["anti"],
            opening_explorer_section.get("max_depth"),
            opening_explorer_section.get("max_moves"),
        )

    @staticmethod
    def _get_lichess_cloud_config(lichess_cloud_section: dict[str, Any]) -> LichessCloudConfig:
        lichess_cloud_sections: list[tuple[str, type | UnionType, str]] = [
            ("enabled", bool, '"enabled" must be a bool.'),
            ("priority", int, '"priority" must be an integer.'),
            ("only_without_book", bool, '"only_without_book" must be a bool.'),
            ("use_for_variants", bool, '"use_for_variants" must be a bool.'),
            ("allow_repetitions", bool, '"allow_repetitions" must be a bool.'),
            ("trust_eval", bool, '"trust_eval" must be a bool.'),
            ("min_eval_depth", int, '"min_eval_depth" must be an integer.'),
            ("min_time", int, '"min_time" must be an integer.'),
            ("timeout", int, '"timeout" must be an integer.'),
        ]

        Config._validate_config_section(lichess_cloud_section, "online_moves.lichess_cloud", lichess_cloud_sections)

        return LichessCloudConfig(
            lichess_cloud_section["enabled"],
            lichess_cloud_section["priority"],
            lichess_cloud_section["only_without_book"],
            lichess_cloud_section["use_for_variants"],
            lichess_cloud_section["allow_repetitions"],
            lichess_cloud_section["trust_eval"],
            lichess_cloud_section["min_eval_depth"],
            lichess_cloud_section["min_time"],
            lichess_cloud_section["timeout"],
            lichess_cloud_section.get("max_depth"),
            lichess_cloud_section.get("max_moves"),
        )

    @staticmethod
    def _get_chessdb_config(chessdb_section: dict[str, Any]) -> ChessDBConfig:
        chessdb_sections: list[tuple[str, type | UnionType, str]] = [
            ("enabled", bool, '"enabled" must be a bool.'),
            ("priority", int, '"priority" must be an integer.'),
            ("only_without_book", bool, '"only_without_book" must be a bool.'),
            ("allow_repetitions", bool, '"allow_repetitions" must be a bool.'),
            ("trust_eval", bool, '"trust_eval" must be a bool.'),
            ("min_time", int, '"min_time" must be an integer.'),
            ("timeout", int, '"timeout" must be an integer.'),
            ("best_move", bool, '"best_move" must be a bool.'),
        ]

        Config._validate_config_section(chessdb_section, "online_moves.chessdb", chessdb_sections)

        return ChessDBConfig(
            chessdb_section["enabled"],
            chessdb_section["priority"],
            chessdb_section["only_without_book"],
            chessdb_section["allow_repetitions"],
            chessdb_section["trust_eval"],
            chessdb_section["min_time"],
            chessdb_section["timeout"],
            chessdb_section["best_move"],
            chessdb_section.get("max_depth"),
            chessdb_section.get("max_moves"),
        )

    @staticmethod
    def _get_online_egtb_config(online_egtb_section: dict[str, Any]) -> OnlineEGTBConfig:
        online_egtb_sections: list[tuple[str, type | UnionType, str]] = [
            ("enabled", bool, '"enabled" must be a bool.'),
            ("min_time", int, '"min_time" must be an integer.'),
            ("timeout", int, '"timeout" must be an integer.'),
        ]

        Config._validate_config_section(online_egtb_section, "online_moves.online_egtb", online_egtb_sections)

        return OnlineEGTBConfig(
            online_egtb_section["enabled"], online_egtb_section["min_time"], online_egtb_section["timeout"]
        )

    @staticmethod
    def _get_online_moves_config(online_moves_section: dict[str, dict[str, Any]]) -> OnlineMovesConfig:
        online_moves_sections: list[tuple[str, type | UnionType, str]] = [
            (
                "opening_explorer",
                dict,
                ('"opening_explorer" must be a dictionary with indented keys followed by colons.'),
            ),
            ("chessdb", dict, '"chessdb" must be a dictionary with indented keys followed by colons.'),
            ("lichess_cloud", dict, '"lichess_cloud" must be a dictionary with indented keys followed by colons.'),
            ("online_egtb", dict, '"online_egtb" must be a dictionary with indented keys followed by colons.'),
        ]

        Config._validate_config_section(online_moves_section, "online_moves", online_moves_sections)

        return OnlineMovesConfig(
            Config._get_opening_explorer_config(online_moves_section["opening_explorer"]),
            Config._get_lichess_cloud_config(online_moves_section["lichess_cloud"]),
            Config._get_chessdb_config(online_moves_section["chessdb"]),
            Config._get_online_egtb_config(online_moves_section["online_egtb"]),
        )

    @staticmethod
    def _get_offer_draw_config(offer_draw_section: dict[str, Any]) -> OfferDrawConfig:
        offer_draw_sections: list[tuple[str, type | UnionType, str]] = [
            ("enabled", bool, '"enabled" must be a bool.'),
            ("score", int, '"score" must be an integer.'),
            ("consecutive_moves", int, '"consecutive_moves" must be an integer.'),
            ("min_game_length", int, '"min_game_length" must be an integer.'),
            ("against_humans", bool, '"against_humans" must be a bool.'),
        ]

        Config._validate_config_section(offer_draw_section, "offer_draw", offer_draw_sections)

        return OfferDrawConfig(
            offer_draw_section["enabled"],
            offer_draw_section["score"],
            offer_draw_section["consecutive_moves"],
            offer_draw_section["min_game_length"],
            offer_draw_section["against_humans"],
            offer_draw_section.get("min_rating"),
        )

    @staticmethod
    def _get_resign_config(resign_section: dict[str, Any]) -> ResignConfig:
        resign_sections: list[tuple[str, type | UnionType, str]] = [
            ("enabled", bool, '"enabled" must be a bool.'),
            ("score", int, '"score" must be an integer.'),
            ("consecutive_moves", int, '"consecutive_moves" must be an integer.'),
            ("against_humans", bool, '"against_humans" must be a bool.'),
        ]

        Config._validate_config_section(resign_section, "resign", resign_sections)

        return ResignConfig(
            resign_section["enabled"],
            resign_section["score"],
            resign_section["consecutive_moves"],
            resign_section["against_humans"],
            resign_section.get("min_rating"),
        )

    @staticmethod
    def _get_challenge_config(challenge_section: dict[str, Any]) -> ChallengeConfig:
        challenge_sections: list[tuple[str, type | UnionType, str]] = [
            ("concurrency", int, '"concurrency" must be an integer.'),
            ("max_takebacks", int, '"max_takebacks" must be an integer.'),
            ("bullet_with_increment_only", bool, '"bullet_with_increment_only" must be a bool.'),
            ("variants", list, '"variants" must be a list of variants.'),
            ("bot_time_controls", list | None, '"bot_time_controls" must be a list of speeds or time controls.'),
            ("human_time_controls", list | None, '"human_time_controls" must be a list of speeds or time controls.'),
            ("bot_modes", list | None, '"bot_modes" must be a list of game modes.'),
            ("human_modes", list | None, '"human_modes" must be a list of game modes.'),
        ]

        Config._validate_config_section(challenge_section, "challenge", challenge_sections)

        return ChallengeConfig(
            challenge_section["concurrency"],
            challenge_section["max_takebacks"],
            challenge_section["bullet_with_increment_only"],
            challenge_section.get("min_increment"),
            challenge_section.get("max_increment"),
            challenge_section.get("min_initial"),
            challenge_section.get("max_initial"),
            challenge_section["variants"],
            challenge_section["bot_time_controls"] or [],
            challenge_section["human_time_controls"] or [],
            challenge_section["bot_modes"] or [],
            challenge_section["human_modes"] or [],
        )

    @staticmethod
    def _get_matchmaking_config(matchmaking_section: dict[str, Any]) -> MatchmakingConfig:
        matchmaking_sections: list[tuple[str, type | UnionType, str]] = [
            ("delay", int, '"delay" must be an integer.'),
            ("timeout", int, '"timeout" must be an integer.'),
            ("selection", str, '"selection" must be one of "weighted_random", "sequential" or "cyclic".'),
            ("types", dict, '"types" must be a dictionary with indented keys followed by colons.'),
        ]

        Config._validate_config_section(matchmaking_section, "matchmaking", matchmaking_sections)

        types: dict[str, MatchmakingTypeConfig] = {}
        for matchmaking_type, matchmaking_options in matchmaking_section["types"].items():
            if not isinstance(matchmaking_options, dict):
                raise TypeError(
                    f'`matchmaking` `types` subsection "{matchmaking_type}" must be a dictionary with '
                    "indented keys followed by colons."
                )

            if "tc" not in matchmaking_options:
                raise RuntimeError(f'Your matchmaking type "{matchmaking_type}" does not have required `tc` field.')

            if not isinstance(matchmaking_options["tc"], str):
                raise TypeError(
                    f"`matchmaking` `types` `{matchmaking_type}` field `tc` must be a string in "
                    "initial_minutes+increment_seconds format."
                )

            types[matchmaking_type] = MatchmakingTypeConfig(
                matchmaking_options["tc"],
                matchmaking_options.get("rated"),
                matchmaking_options.get("variant"),
                matchmaking_options.get("weight"),
                matchmaking_options.get("multiplier"),
                matchmaking_options.get("min_rating_diff"),
                matchmaking_options.get("max_rating_diff"),
            )

        return MatchmakingConfig(
            matchmaking_section["delay"], matchmaking_section["timeout"], matchmaking_section["selection"], types
        )

    @staticmethod
    def _get_messages_config(messages_section: dict[str, str]) -> MessagesConfig:
        messages_sections: list[tuple[str, type | UnionType, str]] = [
            ("greeting", str, '"greeting" must be a string wrapped in quotes.'),
            ("goodbye", str, '"goodbye" must be a string wrapped in quotes.'),
            ("greeting_spectators", str, '"greeting_spectators" must be a string wrapped in quotes.'),
            ("goodbye_spectators", str, '"goodbye_spectators" must be a string wrapped in quotes.'),
        ]

        for subsection in messages_sections:
            if subsection[0] in messages_section:
                if not isinstance(messages_section[subsection[0]], subsection[1]):
                    raise TypeError(f"`messages` subsection {subsection[2]}")

                if messages_section[subsection[0]].strip() == "!printeval":
                    print(f'Ignoring message "{subsection[0]}": "!printeval" is not allowed in messages.')
                    del messages_section[messages_section[subsection[0]]]

        return MessagesConfig(
            messages_section.get("greeting"),
            messages_section.get("goodbye"),
            messages_section.get("greeting_spectators"),
            messages_section.get("goodbye_spectators"),
        )

    @staticmethod
    def _get_version() -> str:
        try:
            output = subprocess.check_output(
                ["git", "show", "-s", "--date=format:%Y%m%d", "--format=%cd", "HEAD"], stderr=subprocess.DEVNULL
            )
            commit_date = output.decode("utf-8").strip()
            output = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
            commit_sha = output.decode("utf-8").strip()[:7]
            return f"{commit_date}-{commit_sha}"
        except (FileNotFoundError, subprocess.CalledProcessError):
            return "nogit"
