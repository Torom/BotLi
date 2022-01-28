## Overview

```
______       _   _     _ 
| ___ \     | | | |   (_)
| |_/ / ___ | |_| |    _ 
| ___ \/ _ \| __| |   | |
| |_/ / (_) | |_| |___| |
\____/ \___/ \__\_____/_|
```

**BotLi** is a bot for Lichess. Strongly inspired by [ShailChoksi/lichess-bot](https://github.com/ShailChoksi/lichess-bot). It extends its features with a matchmaking mode where the bot automatically challenges other bots with similar ratings.

Not every function of the bot is extensively tested, a faulty or incomplete `config.yml` will lead to unexpected behavior. This bot has only been tested on Linux, other chess variants than Standard and Chess960 are untested. At least Python 3.10 is required.

## How to install

- **NOTE: Only Python 3.10 or later is supported!**
- Download the repo into BotLi directory: `git clone https://github.com/Torom/BotLi.git`
- Navigate to the directory in cmd/Terminal: `cd BotLi`
- Copy `config.yml.default` to `config.yml`

Install all requirements:
```bash
python3 -m pip install -r requirements.txt
```

- Customize the `config.yml` according to your needs.

### Lichess OAuth
- Create an account for your bot on [Lichess.org](https://lichess.org/signup).
- **NOTE: If you have previously played games on an existing account, you will not be able to use it as a bot account.**
- Once your account has been created and you are logged in, [create a personal OAuth2 token with the "Play games with the bot API" ('bot:play') scope](https://lichess.org/account/oauth/token/create?scopes[]=bot:play&description=lichess-bot) selected and a description added.
- A `token` (e.g. `xxxxxxxxxxxxxxxx`) will be displayed. Store this in the `config.yml` file as the `token` field.
- **NOTE: You won't see this token again on Lichess, so do save it.**

### Setup Engine
Within the file `config.yml`:
- Enter the directory containing the engine executable in the `engine: dir` field.
- Enter the executable name in the `engine: name` field.
- You need to adjust the settings in `engine: uci_options` depending on your system.

## How to start

```bash
python user_interface.py
```
The bot automatically accepts challenges. Which challenges it accepts is defined in the config in the section `challenge`.

## How to control

Press <kbd>TAB</kbd> <kbd>TAB</kbd> to see all options.

To challenge other players with similar ratings, type
```bash
matchmaking
```

Change the settings in `matchmaking` in the config to change how this bot challenges other players. The bot will not accept challenges in this mode. To exit the matchmaking mode type
```bash
stop
```

To exit the bot completely type
```bash
quit
```

The bot will always wait until the current game is finished.


## Acknowledgements
Thanks to the Lichess team, especially T. Alexander Lystad and Thibault Duplessis for working with the LeelaChessZero team to get this API up. Thanks to the [Niklas Fiekas](https://github.com/niklasf) and his [python-chess](https://github.com/niklasf/python-chess) code which allows engine communication seamlessly. In addition, the idea of this bot is based on [ShailChoksi/lichess-bot](https://github.com/ShailChoksi/lichess-bot). Few lines were copied as is, many were used as patterns.

## License
**BotLi** is licensed under the AGPLv3 (or any later version at your option). Check out the [LICENSE file](/LICENSE) for the full text.