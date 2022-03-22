# Overview

**BotLi** is a bot for Lichess. Strongly inspired by [ShailChoksi/lichess-bot](https://github.com/ShailChoksi/lichess-bot). It extends its features with a matchmaking mode where the bot automatically challenges other bots with similar ratings.

Not every function of the bot is extensively tested, a faulty or incomplete `config.yml` will lead to unexpected behavior. Other chess variants than Standard and Chess960 are untested. At least Python 3.10 is required.

# Heroku

### Chess Engines

- [Stockfish](https://github.com/official-stockfish/Stockfish)
- [Stockfish Multi Variant (dev)](https://github.com/ddugovic/Stockfish)

### Heroku Buildpack

- [`heroku/python`](https://elements.heroku.com/buildpacks/heroku/heroku-buildpack-python)

### Heroku Stack

- [`heroku-20`](https://devcenter.heroku.com/articles/heroku-20-stack)

## How to install

- [Fork](https://github.com/Torom/BotLi/fork) this repository.
- Copy `config.yml.default` to `config.yml` __DON'T INSERT YOUR TOKEN__
- Create a [new heroku app](https://dashboard.heroku.com/new-app).
- Go to the `Deploy` tab and click `Connect to GitHub`.
- Click on `search` and then select your fork of this repository.
- Then `Enable Automatic Deploys` and then select the `heroku` branch and Click `Deploy`.
- Once it has been deployed, go to `Settings` tab on heroku and create a variable, set `LICHESS_BOT_TOKEN` as key and your token as value.
- Go to `Resources` tab on heroku and enable `worker (bash startbot.sh)` dynos. (Do note that if you don't see any dynos in the `Resources` tab, then you must wait for about 5 minutes and then refresh your heroku page.)

You're now connected to lichess and awaiting challenges! Your bot is up and ready! You can activate the matchmaking mode in your `startbot.sh` file.

__CAUTION:__ Be careful with matchmaking mode, lichess will rate limit you if you let it run for too long!

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

## Matchmaking mode

You can activate the matchmaking mode in your `startbot.sh` file.

__CAUTION:__ Be careful with matchmaking mode, lichess will rate limit you if you let it run for too long!

## Acknowledgements
Thanks to the Lichess team, especially T. Alexander Lystad and Thibault Duplessis for working with the LeelaChessZero team to get this API up. Thanks to the [Niklas Fiekas](https://github.com/niklasf) and his [python-chess](https://github.com/niklasf/python-chess) code which allows engine communication seamlessly. In addition, the idea of this bot is based on [ShailChoksi/lichess-bot](https://github.com/ShailChoksi/lichess-bot).

## License
**BotLi** is licensed under the AGPLv3 (or any later version at your option). Check out the [LICENSE file](/LICENSE) for the full text.