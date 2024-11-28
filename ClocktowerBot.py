from asyncio.windows_events import NULL
import os
import random
import discord
import typing
from enum import Enum
from discord.ext import commands   # Import the discord.py extension "commands"
from discord import Interaction, app_commands
from discord.utils import get
from dotenv import load_dotenv
from interactions import interaction

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
    
class ChannelNames(Enum): #Names for created discord channels and categories
    category = "Blood on the clocktower"
    storytellerText = "Story teller's lounge"
    
    
class GameState: #Class the holds the users set for the game
    def __init__(self):
        self.storyteller = NULL #Meber who is the storyteller
        self.players = [] #List of players in the game
        self.active = False #Whever the game is running or not
        self.channels = GameChannels() #Store game channels here

    def __str__(self) -> str:
        playerNames = []
        for player in self.players:
            playerNames.append(player.name)
        return f"Storyteller: {self.storyteller} \n Players: {playerNames} \n Acive?: {self.active}"

    def setStoryTeller(self,member: discord.Member):
        self.storyteller = member
        
    def addPlayer(self,player: discord.Member):
        if not (player in self.players):
            self.players.append(player)
           
    def removePlayer(self,player: discord.Member):
        if player in self.players:
            self.players.remove(player)
            
    def getPlayers(self):
        return self.players
    
class GameChannels: #Holds the discord channels for use in the game
    def __init__(self):
        self.category = None #Category all the channels are grouped in
        self.storytellerText = NULL #Storyteller text channel
    
    
        
gameState = GameState() # public game state
        
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
    name="set_story_teller",
    description="set which user is the story teller for the next game",
)
@app_commands.describe(member="The member to make the story teller")
async def setStoryTeller(interaction: discord.Interaction, member: discord.Member): # Set who is the storyteller for a unactive game
    if (gameState.active):
        await interaction.response.send_message("You cannot change the storyteller during an active game")
    else:
        print(member)
        try: #Roles might not exist
            storyRole = get(interaction.guild.roles, name=Role.storyTeller.value) #Get storyteller role from server
            if (gameState.storyteller != NULL): #If there was a previous storyteller, remove their role
                await gameState.storyteller.remove_roles(storyRole)
            await member.add_roles(storyRole)
            gameState.setStoryTeller(member)
            await interaction.response.send_message(f"{member} is now the storyteller")
        except Exception as e:
            print("Exception has occured while swappign storyteller:",e)
            await interaction.response.send_message("Something went wrong swapping storytellers")
            
@bot.tree.command(
    name="add_player",
    description="Add a player to the next game",
)
@app_commands.describe(member="The member to add")
async def addPlayer(interaction: discord.Interaction, member: discord.Member): # add one player to an active game
    if (member == gameState.storyteller):
        await interaction.response.send_message("You cannot make the storyteller a player")
    elif (gameState.active):
        await interaction.response.send_message("You cannot add players during an active game")
    else:
        print(member)
        try: #Roles might not exist
            playerRole = get(interaction.guild.roles, name=Role.player.value) #Get player role from server
            if not (playerRole in member.roles):
                await member.add_roles(playerRole) #Give them the player role if they do not have it already
            gameState.addPlayer(member) #Add player to game
            await interaction.response.send_message(f"Added player: {member} to the game")
        except Exception as e:
            print("Exception has occured while assigning players:",e)
            await interaction.response.send_message("Something went wrong assigning players")
            
@bot.tree.command(
    name="remove_player",
    description="Remove a player from the next game",
)
@app_commands.describe(member="The member to remove")
async def removePlayer(interaction: discord.Interaction, member: discord.Member): # remove one player from an active game
    if (gameState.active):
        await interaction.response.send_message("You cannot remove players during an active game")
    else:
        print(member)
        try: #Roles might not exist
            playerRole = get(interaction.guild.roles, name=Role.player.value) #Get player role from server
            if (playerRole in member.roles):
                 await member.remove_roles(playerRole) #Remove the role
            gameState.removePlayer(member) #Remove player to game
            await interaction.response.send_message(f"Removed player: {member}")
        except Exception as e:
            print("Exception has occured while removing players:",e)
            await interaction.response.send_message("Something went wrong removing players")
     
@bot.tree.command(
    name="player_list",
    description="Show the players in a game",
)
async def printGameState(interaction: discord.Interaction): #Print game state for testing TODO make this pretty
    await interaction.response.send_message(f"{gameState}")
    
@bot.tree.command(
    name="sync_roles",
    description="Syncs the bot to the bot-specific roles on the server and removes excess roles",
)
async def syncRoles(interaction: discord.Interaction): #Sync the discord roles to the bots game state, if possible
    global gameState
    if (gameState.active): #Changing the playlist mid-game will break things
        await interaction.response.send_message("You cannot change the game's state while a match is active")
    else:
        try: #Roles might not exist or calling members may fail
            memberList = interaction.guild.fetch_members() #Get all the servers members, might be dangerous but this bot has a limited scope in users
            newGameState = GameState()
            playerRole = get(interaction.guild.roles, name=Role.player.value) #Get player role from server
            storyRole = get(interaction.guild.roles, name=Role.storyTeller.value) #Get storyteller role from server
            async for member in memberList:
                if (storyRole in member.roles) and (playerRole in member.roles): #A user is both storyteller and player
                    await interaction.response.send_message(f"{member} cannot be both a player and a storyteller")
                    return
                if (storyRole in member.roles) and (newGameState.storyteller != NULL): #If a user is set as storyteller while another is a storyteller
                    await interaction.response.send_message(f"{member} and {newGameState.storyteller} cannot be both be storytellers")
                    return
                if playerRole in member.roles:
                    newGameState.addPlayer(member)
                if storyRole in member.roles:
                    newGameState.setStoryTeller(member)
                    
            gameState = newGameState #Update gamestate
            await interaction.response.send_message(f"Synced member roles to the bot successfully")
        except Exception as e:
            print("Exception has occured while syncing player roles:",e)
            await interaction.response.send_message("Something went wrong syncing roles")
            
async def createStoryText(interaction: discord.Interaction): #Create storyteller text channel
    print(f"Category: {gameState.channels.category}")
    storyRole = get(interaction.guild.roles, name=Role.storyTeller.value) #Get storyteller role from server
    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        storyRole: discord.PermissionOverwrite(read_messages=True)
    }
    gameState.channels.storytellerText = await interaction.guild.create_text_channel(name=ChannelNames.storytellerText.value, overwrites=overwrites, category=gameState.channels.category)
    
@bot.tree.command(
    name="setup_channels",
    description="creates the channels needed for the game if they do not exist",
)
async def setupChannels(interaction: discord.Interaction): #Creates the text and voice channels for the bot#
    try:
        if get(interaction.guild.categories,name=ChannelNames.category.value): # If category already exists
            print(f"Category already exists")
            gameState.channels.category = get(interaction.guild.categories,name=ChannelNames.category.value)
        else:
            category = await interaction.guild.create_category(ChannelNames.category.value)
            gameState.channels.category = category
            
        await createStoryText(interaction)
        await interaction.response.send_message("Succesfully created channels")
        
    except Exception as e:
        print("Exception has occured while setting up channels:",e)
        raise e
        await interaction.response.send_message("Something went setting up channels")
        
    
    
            
#Run the bot
bot.run(TOKEN)