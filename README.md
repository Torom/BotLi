[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/Torom/BotLi)

# Overview

**BotLi** is a bot for Lichess. It connects any [UCI](https://backscattering.de/chess/uci/) engine with the [Lichess Bot API](https://lichess.org/api#tag/Bot).

It has a customizable support of Polyglot opening books, a variety of supported online opening books and an online endgame tablebase. It can query local Syzygy and Gaviota endgame tablebases.

In addition, BotLi can autonomously challenge other bots in any variant. It supports custom opening books and engines depending on color, time control and Lichess chess variant.

If you have found a bug, please [create an issue](https://github.com/Torom/BotLi/issues/new?labels=bug&template=bug_report.md). For discussion, feature requests and help join the [BotLi Discord server](https://discord.gg/6aS945KMFD).

# How to install

- **NOTE: Only Python 3.11 or later is supported!**
- Download the repo into BotLi directory: `git clone https://github.com/Torom/BotLi.git`
- Navigate to the directory in cmd/Terminal: `cd BotLi`
- Copy `config.yml.default` to `config.yml`

Install all requirements:
```bash
python -m pip install -r requirements.txt
```

- Customize the `config.yml` according to your needs.

## Lichess OAuth
- Create an account for your bot on [Lichess.org](https://lichess.org/signup).
- **NOTE: If you have previously played games on an existing account, you will not be able to use it as a bot account.**
- Once your account has been created and you are logged in, [create a personal OAuth2 token with the "Play games with the bot API" ('bot:play') scope](https://lichess.org/account/oauth/token/create?scopes[]=bot:play&description=BotLi) selected and a description added.
- A `token` will be displayed. Store this in the `config.yml` file as the `token` field.
- **NOTE: You won't see this token again on Lichess, so do save it.**

## Setup Engine
A separate engine can be configured for each time control and variant. By appending `_white` or `_black` to the time control, variant, `standard` or `variants`, the engine can be configured for that color only.

Within the file `config.yml`:
- Enter the directory containing the engine executable in the `engine: dir` field.
- Enter the executable name in the `engine: name` field.
- You need to adjust the settings in `engine: uci_options` depending on your system.

## Setup opening book
To use an opening book, you have to enter a name of your choice and the path to the book at the end of the config in the `books` section.

In the upper `opening_books: books` section you only have to enter the name you just chose. In addition, different books can be used depending on the time control, white, black and for all variants. If no specific book is defined, the `standard` books are used for standard chess.

For example, the `books` section could look like this:
```yaml
books:
  Goi: "./engines/Goi.bin"
  Perfect: "/home/Books/Perfect2021.bin"
  Cerebellum: "Cerebellum.bin"
```
A corresponding `opening_books` section could look like this:
```yaml
opening_books:
  enabled: true
  priority: 400
  books:
    bullet_white:
      selection: uniform_random
      names:
        - Goi
    bullet_black:
      selection: best_move
      names:
        - Goi
        - Cerebellum
    standard:
      selection: weighted_random
      max_depth: 8
      names:
        - Cerebellum
```

# How to control

## Interactive mode

In this mode the bot is controlled by commands entered into the console.

### Start

To start the bot, type:

```bash
python user_interface.py
```
The bot automatically accepts challenges. Which challenges are accepted is defined in the config in the section `challenge`.

To see all commands, type:
```
help
```

### Matchmaking

To challenge other players with similar ratings, type:
```
matchmaking
```

Change the settings in `matchmaking` in the config to change how this bot challenges other players. The bot will pause matchmaking for incoming challenges. To exit the matchmaking mode type:
```
stop
```

### Tournament

BotLi can participate in tournaments, it joins them automatically after the tournament has begun and leaves them when BotLi is terminated or the tournament is over. During participation in a tournament, one game slot is always reserved for each tournament so that the games can be played without disruption.
To join a tournament, type:
```
tournament TOURNAMENT_ID [TEAM_ID] [PASSWORD]
```

Where TOURNAMENT_ID is replaced by the ID of the tournament, which is easiest to take from the URL of the tournament. TEAM_ID and PASSWORD are optional, the TEAM_ID is taken from the URL of the team page and the PASSWORD is provided by the tournament organizer. To leave a tournament, type:
```
leave TOURNAMENT_ID
```

### Exiting

To exit the bot completely, type:
```
quit
```

The bot will always wait until the current game is finished.

## Non interactive mode

This mode is used automatically when BotLi is used without an interactive terminal, for example as a service. In this case, the bot is controlled by setting flags at start time.

### Matchmaking

To let the bot challenge other bots in non interactive mode, start it like this:

```bash
python user_interface.py --matchmaking
```

**CAUTION**: Lichess will rate limit you if you let matchmaking run too long without adjusting the delay accordingly.

### Tournament

To join a tournament in non interactive mode, start it like this:
```bash
python user_interface.py --tournament TOURNAMENT_ID --team TEAM_ID --password PASSWORD
```

## Upgrade to Bot account

When the bot is running in interactive mode it will ask for an account upgrade if necessary.

In non interactive mode the `--upgrade` flag must be set at start.


```bash
python user_interface.py --upgrade
```

The account **cannot have played any game** before becoming a Bot account. The upgrade is **irreversible**. The account will only be able to play as a Bot.

## Running with Docker

The project comes with a Dockerfile, this uses python:3.13, installs all dependencies, downloads the latest version of Stockfish and starts the bot.

If Docker is used, all configurations must be done in `config.yml.default`. This is automatically renamed to `config.yml` in the build process.

The Dockerfile also contains all commands to download Fairy-Stockfish and all NNUEs needed for the Lichess chess variants. These commands must be uncommented if desired. In addition, the variants engine must be enabled in the `config.yml.default`. To use NNUE for the Lichess chess variants the following UCI option for Fairy-Stockfish must be set in the config: `EvalFile: "3check-cb5f517c228b.nnue:antichess-dd3cbe53cd4e.nnue:atomic-2cf13ff256cc.nnue:crazyhouse-8ebf84784ad2.nnue:horde-28173ddccabe.nnue:kingofthehill-978b86d0e6a4.nnue:racingkings-636b95f085e3.nnue"`

## Running as a service

This is an example systemd service definition:

```ini
[Unit]
Description=BotLi
After=network-online.target
Wants=network-online.target

[Service]
Environment="PYTHONUNBUFFERED=1"
ExecStart=/usr/bin/python3 /home/ubuntu/BotLi/user_interface.py
WorkingDirectory=/home/ubuntu/BotLi
User=ubuntu
Group=ubuntu
Restart=on-failure
TimeoutStopSec=infinity
KillMode=mixed

[Install]
WantedBy=multi-user.target
```

If the service should run with matchmaking the `--matchmaking` flag must be appended at the end of the `ExecStart` line.

**Note**: If you want the bot to run in matchmaking mode for a long time, it is recommended to set the `matchmaking` `delay` higher to avoid problems with the Lichess rate limit. I recommend the following formula: `delay = 430 - 2 * initial_time - 160 * increment`

## Acknowledgements
Thanks to the Lichess team, especially T. Alexander Lystad and Thibault Duplessis for working with the LeelaChessZero team to get this API up. Thanks to the [Niklas Fiekas](https://github.com/niklasf) and his [python-chess](https://github.com/niklasf/python-chess) code which allows engine communication seamlessly. In addition, the idea of this bot is based on [lichess-bot-devs/lichess-bot](https://github.com/lichess-bot-devs/lichess-bot).

## License
**BotLi** is licensed under the AGPLv3 (or any later version at your option). Check out the [LICENSE file](/LICENSE) for the full text.
