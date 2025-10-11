[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/Torom/BotLi)
[![](https://dcbadge.limes.pink/api/server/https://discord.gg/6aS945KMFD?style=flat)](https://discord.gg/6aS945KMFD)

# Overview

**BotLi** is a bot for Lichess. It connects any [UCI](https://backscattering.de/chess/uci/) engine with the [Lichess Bot API](https://lichess.org/api#tag/Bot).

It has a customizable support of Polyglot opening books, a variety of supported online opening books and an online endgame tablebase. It can query local Syzygy and Gaviota endgame tablebases.

In addition, BotLi can autonomously challenge other bots in any variant. It supports custom opening books and engines depending on color, time control and Lichess chess variant.

If you have found a bug, please [create an issue](https://github.com/Torom/BotLi/issues/new?labels=bug&template=bug_report.md). For discussion, feature requests and help join the [BotLi Discord server](https://discord.gg/6aS945KMFD).

# How to install

First, ask yourself if there is a good reason to create another bot. If you are developing your **own engine** or have a cool idea that makes it interesting **for humans** to play against your bot, then BotLi is for you.

Please refrain from creating another Stockfish bot. There are already enough of them, and that is **not** what the Lichess bot API is intended for.

- Download the repo into BotLi directory: `git clone https://github.com/Torom/BotLi.git`
- Navigate to the directory in cmd/Terminal: `cd BotLi`
- Copy `config.yml.default` to `config.yml`
- Customize the `config.yml` according to your needs.

## Recommended: uv
[uv](https://github.com/astral-sh/uv) is a modern Python project manager that handles dependencies and can also install Python itself. The readme assumes that uv is used.

 - [Install uv](https://github.com/astral-sh/uv?tab=readme-ov-file#installation)
 - Install requirements: `uv sync`

## pip
**NOTE: Only Python 3.11 or later is supported!**

Install requirements:
```bash
python3 -m pip install .
```

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
uv run user_interface.py
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

Change the settings in `matchmaking` in the config to change how this bot challenges other players. The bot will pause matchmaking for incoming challenges.

**Note**: Lichess has a strict limit for bot vs. bot games. It is **strongly** recommended to adjust the `matchmaking` `delay` according to the time control. The recommended formula is as follows, all values in seconds:
```python
delay = 864 - 1.34 * initial_time - 91.76 * increment
```

To exit the matchmaking mode type:
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

This mode is used automatically when BotLi is used without an interactive terminal, for example as a service. In this case, the bot is controlled by passing any command at start time.

Note that commands consisting of several words are delimited by `"`. Any number of commands can be passed this way:
```bash
uv run user_interface.py matchmaking "tournament TOURNAMENT_ID" "create COUNT USERNAME"
```

### Matchmaking

To let the bot challenge other bots in non interactive mode, start it like this:

```bash
uv run user_interface.py matchmaking
```

**CAUTION**: Lichess will rate limit you if you let matchmaking run too long without adjusting the delay accordingly.

### Tournament

To join a tournament in non interactive mode, start it like this:
```bash
uv run user_interface.py "tournament TOURNAMENT_ID TEAM_ID PASSWORD"
```

You can also join multiple tournaments this way:
```bash
uv run user_interface.py "tournament TOURNAMENT_ID TEAM_ID PASSWORD" "tournament TOURNAMENT2_ID TEAM2_ID PASSWORD2"
```

## Upgrade to Bot account

When the bot is running in interactive mode it will ask for an account upgrade if necessary.

In non interactive mode the `--upgrade` flag must be set at start.


```bash
uv run user_interface.py --upgrade
```

The account **cannot have played any game** before becoming a Bot account. The upgrade is **irreversible**. The account will only be able to play as a Bot.

## Running as a service

This is an example systemd service definition:

```ini
[Unit]
Description=BotLi
After=network-online.target
Wants=network-online.target

[Service]
Environment="PYTHONUNBUFFERED=1"
ExecStart=/home/ubuntu/.local/bin/uv run user_interface.py
WorkingDirectory=/home/ubuntu/BotLi
User=ubuntu
Group=ubuntu
Restart=on-failure
TimeoutStopSec=infinity
KillMode=mixed

[Install]
WantedBy=multi-user.target
```

If the service should run with matchmaking the `matchmaking` command must be appended at the end of the `ExecStart` line.

## Acknowledgements
Thanks to the Lichess team, especially T. Alexander Lystad and Thibault Duplessis for working with the LeelaChessZero team to get this API up. Thanks to the [Niklas Fiekas](https://github.com/niklasf) and his [python-chess](https://github.com/niklasf/python-chess) code which allows engine communication seamlessly. In addition, the idea of this bot is based on [lichess-bot-devs/lichess-bot](https://github.com/lichess-bot-devs/lichess-bot).

## License
**BotLi** is licensed under the AGPLv3 (or any later version at your option). Check out the [LICENSE file](/LICENSE) for the full text.
