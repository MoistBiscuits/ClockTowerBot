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
- Python version 3.11 or greater
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


