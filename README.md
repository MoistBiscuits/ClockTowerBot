# Clocktowerbot: A discord bot intergration of Blood on the Clocktower
## What is Blood on the Clocktower?

Blood on the clocktower is a popular social deduction game where a group of players must find the murderous demon in their town with the entire game being run by the storyteller.
Good players must sniff out the evil players who conspire against them, piecing together their findings to execute the demon, while the evil team work with the demon to ensure the demise of the town.
This bot (and documentation) assumes you know the basics of the games rules and premise, so its best you learn about them first before diving in.

You can find out more about Blood on the Clocktower on their main site:
https://bloodontheclocktower.com

And use the unofficial wiki for rules clarification and player roles here:
https://wiki.bloodontheclocktower.com/Main_Page

## So what is this discord bot?

This discord bot allows the creation and running of blood on the Clocktower games online through a discord server. The bot emulates a phsyicial game, giving the storyteller the power to visit players in private at night and players get into private convserations during the day to confide and conspire all remotely online. This bot uses discord channels to manage conversation and slash commands to allow the storyteller to control the game and automate the busywork of managing players, allowing you to run games with your friends online.

## How to setup your own instance of the bot

You will need:
- Python version 3.11 or greater (Get it here: https://www.python.org/downloads/)
- Your own Discord bot with it's own token (Find our more here: https://discord.com/developers/docs/intro)

First: clone this repository onto your own machine
`git clone https://github.com/MoistBiscuits/ClockTowerBot.git`

Inside the newly created folder, create a new file named `.env`

Inside `.env` add in the following, replacing `<YOUR TOKEN HERE>` with your own discord bots token

`DISCORD_TOKEN=<YOUR TOKEN HERE>`

Open up the terminal or command prompt in your repoistory and install the required packages

`pip install requirements.txt`

And finally run the bot using python

`py ClocktowerBot.py`

## How to use the bot

Once your python code is running, you will need to invite your discord bot to a server.
I **highly reccommend** creating a new server using an alternative account if you plan on being a player in any games since the bot uses discord permissions to hide player conversations, and owners can always see these channels.

You will need the `manage_roles` permission to setup a game with the bot

To setup a game run `/setup_roles` so the bot can create the roles it uses to run the game
Use `/set_set_storyteller` and `/add_player` to set who will be the storyteller and which members will be players in the game
You can also give members the `ctb-storyteller` and `stb-player` role with `/sync_roles` to register the storyteller and players to the bot

Only one member cna be the storyteller and everyone who plans to play will need to be a player

When every member is registered with the bot, run `/setup_channels` to create the discord channels that players will use.
These channels are where the game takes place, the town hall is where all players will be brought each day and where they will vote and nominate other players
Each player has their own private channel they will be sent to each night where only the storyteller and talk to them
During the day, public channels will be opened and players can get into private conservsations with other players

Run `/start_game` to begin the game, starting at the first night

The rules of this version are nearly the exact same as the physical version, except on a different medium. Instead of using he grimore at night to communcate with players, the storyteller visits the players private channel to talk with the directly. During the day players can use the automatic public channels created by the bot to get into public conversations. The channels automatically close once players join them to prevent other players from snooping in.

The storyteller has fully access to each of the channels, they can use the command `/advance_phase` to porgress the game in its phases, just like the board game

Every day has 4 phases, starting at night which the storyteller can advance the game through:
- At night, players are in a private room, the storyteller can visit them in secret
- At Dawn, all players meet in the town centre and the storyteller can announce any deaths using `/kill_player`
- At Midday, players are free to talk amongst themselves. They can use the public channels to talk in private in small groups. The public channels prevent other players from joining into conversations. `/open_door` and `/lock_door` commands can be used by players to control how private their conversation is.
- At Dusk, the storyteller holds the executions and players vote and nominate on players, just like the physical version

Gameplay continues through each day until either the good team executes the demon or the demon kills enough of the good team, at which `/end_game` can be used and another can be started


