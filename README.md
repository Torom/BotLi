# Overview

**BotLi** is a bot for Lichess. Strongly inspired by [ShailChoksi/lichess-bot](https://github.com/ShailChoksi/lichess-bot). It extends its features with a matchmaking mode where the bot automatically challenges other bots with similar ratings.

Not every function of the bot is extensively tested, a faulty or incomplete `config.yml` will lead to unexpected behavior. Other chess variants than Standard and Chess960 are untested. At least Python 3.10 is required.

# How to install

- **NOTE: Only Python 3.10 or later is supported!**
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
- Once your account has been created and you are logged in, [create a personal OAuth2 token with the "Play games with the bot API" ('bot:play') scope](https://lichess.org/account/oauth/token/create?scopes[]=bot:play&description=lichess-bot) selected and a description added.
- A `token` (e.g. `xxxxxxxxxxxxxxxx`) will be displayed. Store this in the `config.yml` file as the `token` field.
- **NOTE: You won't see this token again on Lichess, so do save it.**

## Setup Engine
Within the file `config.yml`:
- Enter the directory containing the engine executable in the `engine: dir` field.
- Enter the executable name in the `engine: name` field.
- You need to adjust the settings in `engine: uci_options` depending on your system.

## Setup polyglot opening book
To use a polyglot opening book the name of the book and the path to the book must be entered at the end of the config in the section `books`.

Several books can be entered here. In the upper area `eninge: polyglot: books` only the name of the book must be entered. In addition, different books can be used for white, black and chess960. If no specific book is defined, the `standard` book is used.

# How to control

To start the bot, type

```bash
python user_interface.py
```
The bot automatically accepts challenges. Which challenges are accepted is defined in the config in the section `challenge`.

To see all commands, type
```
help
```

## Matchmaking mode

To challenge other players with similar ratings, type
```
matchmaking
```

Change the settings in `matchmaking` in the config to change how this bot challenges other players. The bot will not accept challenges in this mode. To exit the matchmaking mode type
```
stop
```

To exit the bot completely, type
```
quit
```

The bot will always wait until the current game is finished.

## Upgrade to Bot account
Upgrade a lichess player account into a Bot account. Only Bot accounts are allowed to use an engine.

The account **cannot have played any game** before becoming a Bot account. The upgrade is **irreversible**. The account will only be able to play as a Bot.

To upgrade your account type
```
upgrade
```

## Acknowledgements
Thanks to the Lichess team, especially T. Alexander Lystad and Thibault Duplessis for working with the LeelaChessZero team to get this API up. Thanks to the [Niklas Fiekas](https://github.com/niklasf) and his [python-chess](https://github.com/niklasf/python-chess) code which allows engine communication seamlessly. In addition, the idea of this bot is based on [ShailChoksi/lichess-bot](https://github.com/ShailChoksi/lichess-bot).

## License
**BotLi** is licensed under the AGPLv3 (or any later version at your option). Check out the [LICENSE file](/LICENSE) for the full text.