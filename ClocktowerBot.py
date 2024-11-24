from asyncio.windows_events import NULL
import os
import random
import discord
from enum import Enum
from discord.ext import commands   # Import the discord.py extension "commands"
from discord import Interaction, app_commands
from discord.utils import get
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.all()
bot = commands.Bot(intents=intents,command_prefix="!")

class Role(Enum): # Roles that are used to determine which channels players can use
    __order__ = 'storyTeller player day night roam alive dead'
    storyTeller = "ctb-StoryTeller" #The storyteller has full access to movement, they admin the game and have their own admin channel
    player = "ctb-Player" #Players are restriced to the town, buildings and their own room
    day = "ctb-Day" #Day players cannot be in their own night room
    night = "ctb-Night" #Night players cannot be in the town or buildings
    roam = "ctb-Roam" #Roam players may freely enter buildings
    alive = "ctb-Alive" #Used to highlight players who are alive
    dead = "ctb-Dead" #Used to highlight dead players
    
class GameState: #Class the holds the users set for the game
    def __init__(self):
        self.storyteller = NULL #User who is the storyteller
        self.players = [] #List of players in the game
        self.active = False #Whever the game is running or not

    def __str__(self) -> str:
        return f"Storyteller: {self.storyteller} \n Players: {self.players} \n Acive?: {self.active}"

    def setStoryTeller(user: discord.abc.User):
        self.storyteller = user
        
@bot.event
async def on_ready(): #On bot startup
    print(f"Logged in as {bot.user.name}")
    try:
        synced = await bot.tree.sync() #Sync slash command to the server
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print("Exception has occured while syncing tree:",e)
        
@bot.tree.command(name="hello",) #TODO remove testing command
async def hello(interaction: discord.Interaction):
    await interaction.response.send_message("Hello!")
    

@bot.tree.command( #Used only for testing
    name="sync",
    description="Sync bot commands to server",
)
async def sync(ctx):
    print("sync command")
    if ctx.author.id == 159375107855351808: #My discord id, TODO changed for dev or remove command
        await bot.tree.sync()
        await ctx.send('Command tree synced.')
    else:
        await ctx.send('You must be the owner to use this command!')
    
@bot.tree.command(name="ping")
async def ping(interaction: discord.Interaction): # a slash command will be created with the name "ping"
    await interaction.response.send_message(f"Pong! Latency is {bot.latency}")

@bot.tree.command(
    name="setup_roles",
    description="Inits user roles for the bot",
)
async def setupRoles(interaction: discord.Interaction): # create roles used by the bot if they do not exist
    for role in Role:
        if get(interaction.guild.roles, name=role.value):
            print(f"Role: {role.value} already exists")
        else:
            await interaction.guild.create_role(name=role.value, colour=discord.Colour(0x0062ff))
    await interaction.response.send_message("Initialised roles")

@bot.tree.command(
    name="setup_channels",
    description="inits user channels for the bot",
)
async def setupChannels(interaction: discord.Interaction): # create the voice channels the bot will use
     await interaction.guild.create_voice_channel(name="Town square")
     await interaction.response.send_message("Initialised Channels")

#Run the bot
bot.run(TOKEN)