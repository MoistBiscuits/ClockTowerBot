from asyncio.windows_events import NULL
import os
import random
from tkinter.tix import INTEGER
import discord
import typing
from enum import Enum
from discord.ext import commands   # Import the discord.py extension "commands"
from discord import Interaction, app_commands
from discord.utils import get
from dotenv import load_dotenv
from interactions import interaction
from typing import List

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
    
class ChannelNames(Enum): #Names for set created discord channels and categories
    category = "Blood on the clocktower"
    storytellerText = "Grimore"
    storytellerVoice = "Story teller's lounge"
    townText = "Town Record"
    townVoice = "Town Square"
    dayRooms=[
        "Church",
        "Bar",
        "Courthouse",
        "library",
        "Docks",
        "Market",
        "Graveyard",
        "Park"
    ]

class GameState: #Class the holds the users set for the game
    def __init__(self):
        self.storyteller = None #Meber who is the storyteller
        self.players = [] #List of players in the game
        self.active = False #Whever the game is running or not
        self.channelReady = False #Whever the correct discord channels are in place
        self.channels = GameChannels() #Store game channels here
        self.playerChannelDict = {} #Dictionary to stores which players have which private room
        self.gameDay = 1 #Determines which day the game is set,
        """
        dayphase : Current phase of the day, each "day" begins at night, game sarts at the first night followed by the first day
        0 - Night : Players in private rooms, get visited by the storyteller privately, use night abilities, demon picks who to kill on all nights except the first etc.
        1 - Dawn : Players allowed in town centre, reveal all deaths that occoured during the night
        2 - Day : Players roam, chat and talk to eachother in public rooms for a time set by the storyteller
        3 - Dusk : Players are brought back to the town centre, nominate and vote on who (if anyone) to execute, afterwards day ends and the next night begins
        """
        self.dayPhase = 0
        

    def __str__(self) -> str:
        playerNames = []
        for player in self.players:
            playerNames.append(player.name)
        return f"Storyteller: {self.storyteller} \n Players: {playerNames} \n Acive?: {self.active}"

    def initStartGame(self):
        self.active = True
        self.gameDay = 1
        self.gamePhase = 0

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
    
    def addPrivateRoom(self,player: discord.Member,room: discord.channel):
        if player in self.players:
            self.playerChannelDict[player] = room
            
    def getRoomOfPlayer(self,player:discord.Member) -> discord.VoiceChannel:
        if player in self.players:
            return self.playerChannelDict[player]
        
    def incrementDayPhase(self):
        self.dayPhase = (self.dayPhase + 1) % 4
        
    def incrementDayCount(self):
        self.gameDay += 1
        
    def getAllUsers(self): #Returns all players and the storyteller as a List[discord.Member]
        data = self.players[::]
        data.append(self.storyteller)
        return data
    
    def getGameTimeMsg(self) -> str: #Returns a string that summaries the current day phase
        if self.gamePhase == 0: #night
            if self.gameDay == 1: #First night
                return f"It is Night 1, All players go to your room and wait to learn your role from the storyteller"
            else:
                return f"It is Night {self.gameDay}, all players return to your rooms"
        elif self.gamePhase == 1: #dawn
            return f"It is the dawn of Day {self.gameDay}, all players gather in the town square"
        elif self.gamePhase == 2: #day
            return f"It is the midday of Day {self.gameDay}, all players are free to move about and chat"
        elif self.gamePhase == 3: #dusk
            return f"It is the dusk of Day {self.gameDay}, all players gather in the town square for nominations"
        else: #error state, should never be reached
            raise Exception(f"Expect gamephase to be in range (0,3) got {self.gamePhase}") 
        
    
class GameChannels: #Holds the discord channels for use in the game
    def __init__(self):
        self.category = None #Category all the channels are grouped in
        self.storytellerText = None #Storyteller text channel
        self.storytellerVoice = None #Storyteller voice channel
        self.townText = None #Town square AKA public day room where votes are called
        self.townVoice = None #Town square AKA public day room where votes are called
        self.publicRooms = [] #Public buildings used for daytime discussion, varies on player count/setttings
        self.privateRooms = [] #Personal night rooms for each player, used for night abilities, length is player count
        
    def addPrivateRoom(self,room: discord.VoiceChannel):
        if not (room in self.privateRooms):
            self.privateRooms.append(room)
            
    def addPublicRoom(self,room: discord.VoiceChannel):
        if not (room in self.publicRooms):
            self.publicRooms.append(room)
            
    def getTownText(self) -> discord.TextChannel:
        return self.townText
            
    
    
        
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
            if (member in gameState.players): #If new storyteller is a player
                playerRole = get(interaction.guild.roles, name=Role.player.value) #Get player role from server
                if (playerRole in member.roles):
                    await member.remove_roles(playerRole) #Remove the role
                gameState.removePlayer(member) #remove them from player list
            if (gameState.storyteller != None): #If there was a previous storyteller, remove their role
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
            gameState.channelReady = False #Change of players means a new channel setup must be made
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
            gameState.channelReady = False #Change of players means a new channel setup must be made
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
                if (storyRole in member.roles) and (newGameState.storyteller != None): #If a user is set as storyteller while another is a storyteller
                    await interaction.response.send_message(f"{member} and {newGameState.storyteller} cannot be both be storytellers")
                    return
                if playerRole in member.roles:
                    newGameState.addPlayer(member)
                if storyRole in member.roles:
                    newGameState.setStoryTeller(member)
                    
            gameState = newGameState #Update gamestate
            gameState.channelReady = False #Change of players means a new channel setup must be made
            await interaction.response.send_message(f"Synced member roles to the bot successfully")
        except Exception as e:
            print("Exception has occured while syncing player roles:",e)
            await interaction.response.send_message("Something went wrong syncing roles")
            
async def createStoryText(interaction: discord.Interaction): #Create storyteller text channel
    storyRole = get(interaction.guild.roles, name=Role.storyTeller.value) #Get storyteller role from server
    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        storyRole: discord.PermissionOverwrite(read_messages=True)
    }
    gameState.channels.storytellerText = await interaction.guild.create_text_channel(name=ChannelNames.storytellerText.value, overwrites=overwrites, category=gameState.channels.category)
    
async def createStoryVoice(interaction: discord.Interaction): #Create storyteller voice channel
    storyRole = get(interaction.guild.roles, name=Role.storyTeller.value) #Get storyteller role from server
    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        storyRole: discord.PermissionOverwrite(read_messages=True)
    }
    gameState.channels.storytellerVoice = await interaction.guild.create_voice_channel(name=ChannelNames.storytellerVoice.value, overwrites=overwrites, category=gameState.channels.category)
    
async def createTownText(interaction: discord.Interaction): #Create hub voice channel
    dayRole = get(interaction.guild.roles, name=Role.day.value) #Get day role from server
    storyRole = get(interaction.guild.roles, name=Role.storyTeller.value)
    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        dayRole: discord.PermissionOverwrite(read_messages=True),
        storyRole: discord.PermissionOverwrite(read_messages=True)
    }
    gameState.channels.townText = await interaction.guild.create_text_channel(name=ChannelNames.townText.value, overwrites=overwrites, category=gameState.channels.category)
    
async def createTownVoice(interaction: discord.Interaction): #Create hub text channel
    dayRole = get(interaction.guild.roles, name=Role.day.value) #Get day role from server
    storyRole = get(interaction.guild.roles, name=Role.storyTeller.value)
    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        dayRole: discord.PermissionOverwrite(read_messages=True),
        storyRole: discord.PermissionOverwrite(read_messages=True)
    }
    gameState.channels.townVoice = await interaction.guild.create_voice_channel(name=ChannelNames.townVoice.value, overwrites=overwrites, category=gameState.channels.category)

def getInitRoomName(playerNumber: int): #Returns the name of a private room that should be used to create a players room
    #Names used for each players private room
    privateRoomNames=[
        "Red Room",
        "Blue Room",
        "Yellow Room",
        "Purple Room",
        "Orange Room",
        "Green Room",
        "Cyan Room",
        "Brown Room",
        "Black Room",
        "White Room",
    ]
    name = privateRoomNames[playerNumber % len(privateRoomNames)]
    #TODO find a cleaner way to needing more room names that expected players
    if playerNumber >= len(privateRoomNames): #If list overflows
        name += " "
        name += str(playerNumber // len(privateRoomNames)) #Append a unique number to it (e.g. Blue Room 2)
    return name
    
async def createPrivateVoice(interaction: discord.Interaction, players: List[discord.Member]): #Create private rooms for each player
    storyRole = get(interaction.guild.roles, name=Role.storyTeller.value)
    for i in range(0,len(players)):
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            players[i]: discord.PermissionOverwrite(read_messages=True),
            storyRole: discord.PermissionOverwrite(read_messages=True)
        }
        room = await interaction.guild.create_voice_channel(name=getInitRoomName(i), overwrites=overwrites, category=gameState.channels.category)
        gameState.channels.addPrivateRoom(room) # Add channel to channels
        gameState.addPrivateRoom(players[i],room) # pair player to channel
        
async def createPublicVoice(interaction: discord.Interaction,count=8): #Creates the given amount of public rooms
    storyRole = get(interaction.guild.roles, name=Role.storyTeller.value)
    dayRole = get(interaction.guild.roles, name=Role.day.value)
    for i in range(0,count):
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            dayRole: discord.PermissionOverwrite(read_messages=True),
            storyRole: discord.PermissionOverwrite(read_messages=True)
        }
        room = await interaction.guild.create_voice_channel(name=ChannelNames.dayRooms.value[i], overwrites=overwrites, category=gameState.channels.category)
        gameState.channels.addPublicRoom(room)
        
 
@bot.tree.command(
    name="setup_channels",
    description="creates the channels needed for the game if they do not exist",
)
async def setupChannels(interaction: discord.Interaction): #Creates the text and voice channels for the bot#
    if gameState.active:
        await interaction.response.send_message(content=f"Cannot setup channels during an active game")
        return
    if gameState.getPlayers() == []:
        await interaction.response.send_message(content=f"Cannot setup channels with no added players")
        return
    try:
        await interaction.response.defer(thinking=True, ephemeral=True)
        category = get(interaction.guild.categories,name=ChannelNames.category.value)
        if category: # If category already exists delete it
            print(f"Category already exists, delete")
            await category.delete()
        gameState.channels.category = await interaction.guild.create_category(ChannelNames.category.value)

        await createStoryText(interaction)
        await createStoryVoice(interaction)
        await createTownText(interaction)
        await createTownVoice(interaction)
        await createPublicVoice(interaction,8)
        await createPrivateVoice(interaction,gameState.getPlayers())
        gameState.channelReady = True
        await interaction.edit_original_response(content=f"Succesfully created channels")
    except Exception as e:
        print("Exception has occured while setting up channels:",e)
        gameState.channelReady = False
        await interaction.edit_original_response(content=f"Something went setting up channels")
        raise e
    
async def cleanRoles(members: List[discord.Member]): #Clears the excess of roles of the given players, only remaining the player role, or storyteller role
    try: #Roles might not exist or calling members may fail
        excessRoleList = []
        excessRoleList.append(get(interaction.guild.roles, name=Role.alive.value))
        excessRoleList.append(get(interaction.guild.roles, name=Role.day.value))
        excessRoleList.append(get(interaction.guild.roles, name=Role.dead.value))
        excessRoleList.append(get(interaction.guild.roles, name=Role.night.value))
        excessRoleList.append(get(interaction.guild.roles, name=Role.roam.value))
        for member in members:
            for role in excessRoleList:
                if (role in member.roles):
                    await member.remove_roles(role)
    except Exception as e:
        raise e
    
async def alivePlayers(members: List[discord.Member]): #give players the alive role, remove dead role if they have it
    try: #Roles might not exist or calling members may fail
        aliveRole = get(interaction.guild.roles, name=Role.alive.value)
        deadRole = get(interaction.guild.roles, name=Role.dead.value)
        for member in members:
            if deadRole in member.roles:
                await member.remove_roles(deadRole)
            if not (aliveRole in member.roles):
                await member.add_roles(aliveRole)
    except Exception as e:
        raise e
    
async def killPlayers(members: List[discord.Member]): #give players the dead role, remove alive role if they have it
    try: #Roles might not exist or calling members may fail
        aliveRole = get(interaction.guild.roles, name=Role.alive.value)
        deadRole = get(interaction.guild.roles, name=Role.dead.value)
        for member in members:
            if aliveRole in member.roles:
                await member.remove_roles(aliveRole)
            if not (deadRole in member.roles):
                await member.add_roles(deadRole)
    except Exception as e:
        raise e
    
async def unlockPlayersPrivateRoom(interaction: discord.Interaction,members: List[discord.Member]): #Give players permission to enter their private room
    try: #Roles might not exist or calling members may fail
        for member in members:
            privateRoom = gameState.getRoomOfPlayer(member) #player's private channel
            storyRole = get(interaction.guild.roles, name=Role.storyTeller.value)
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                member: discord.PermissionOverwrite(read_messages=True),
                storyRole: discord.PermissionOverwrite(read_messages=True)
            }
            privateRoom.set_permissions(overwrite=overwrites)
    except Exception as e:
        raise e
    
async def lockPlayersPrivateRoom(interaction: discord.Interaction,members: List[discord.Member]): #Remove players permission to enter their private room
    try: #Roles might not exist or calling members may fail
        for member in members:
            privateRoom = gameState.getRoomOfPlayer(member) #player's private channel
            storyRole = get(interaction.guild.roles, name=Role.storyTeller.value)
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                storyRole: discord.PermissionOverwrite(read_messages=True)
            }
            privateRoom.set_permissions(overwrite=overwrites)
    except Exception as e:
        raise e

async def sendPlayersToPrivateRoom(members: List[discord.Member]): #give players the Night role, remove day and roam roles and send them to their private room
    try: #Roles might not exist or calling members may fail
        dayRole = get(interaction.guild.roles, name=Role.day.value)
        roamRole = get(interaction.guild.roles, name=Role.roam.value)
        nightRole = get(interaction.guild.roles, name=Role.night.value)

        #Players need to be able to access their room to be sent to it
        await unlockPlayersPrivateRoom(members)        

        for member in members:
            if not (member in gameState.getPlayers()):
                return #Do nothing to non-players
            if dayRole in member.roles:
                await member.remove_roles(dayRole)
            if roamRole in member.roles:
                await member.remove_roles(roamRole)
            if not (nightRole in member.roles):
                await member.add_roles(nightRole)
            privateRoom = gameState.getRoomOfPlayer(member) #player's private channel
            await member.move_to(privateRoom) #move them to their channel  
    except Exception as e:
        raise e
    
async def sendPlayersToTown(members: List[discord.Member]): #Give players the Day Role, remove night and roam roles and force them into town
    try: #Roles might not exist or calling members may fail
        dayRole = get(interaction.guild.roles, name=Role.day.value)
        roamRole = get(interaction.guild.roles, name=Role.roam.value)
        nightRole = get(interaction.guild.roles, name=Role.night.value)

        #Players should be blocked from their rooms
        await lockPlayersPrivateRoom(members)        

        for member in members:
            if not (member in gameState.getPlayers()):
                return #Do nothing to non-players
            if nightRole in member.roles:
                await member.remove_roles(nightRole)
            if roamRole in member.roles:
                await member.remove_roles(roamRole)
            if not (dayRole in member.roles):
                await member.add_roles(dayRole)
            town = gameState.channels.townVoice
            await member.move_to(town) #move them to their channel  
    except Exception as e:
        raise e
    
async def allowPlayersRoam(members: List[discord.Member]): #Give players the Roam role, lets them visit public rooms
    try:
        roamRole = get(interaction.guild.roles, name=Role.roam.value)
        for member in members:
            if not (roamRole in member.roles):
                await member.add_roles(roamRole)
    except Exception as e:
        raise e
    
async def denyPlayersRoam(members: List[discord.Member]): #Remove player(s)'s Roam role if they have it, denying them from public rooms
    try:
        roamRole = get(interaction.guild.roles, name=Role.roam.value)
        for member in members:
            if (roamRole in member.roles):
                await member.remove_roles(roamRole)
    except Exception as e:
        raise e
    
async def declareGamePhase(): #Bot states the phase of the game into chat
    await gameState.channels.getTownText().send(gameState.getGameTimeMsg())

@bot.tree.command(
    name="start_game",
    description="Starts a BotCT game, make sure to add the players, storyteller and setup the new set of channels first!"
)
async def startGame(interaction: discord.Interaction):
    if gameState.active:
        await interaction.response.send_message(content=f"A game is already running, end it before starting a new one")
        return
    if not gameState.channelReady:
        await interaction.response.send_message(content=f"Channels have not been setup yet, run /setup_chanels to create and set them to the bot")
        return
    await interaction.response.defer(thinking=True)    

    await cleanRoles(gameState.getAllUsers()) #Remove any excess flag roles that users might have for some reason
    await alivePlayers(gameState.getPlayers()) #Give all players the alive role
    await sendPlayersToPrivateRoom(gameState.getPlayers()) #Send all players to their private room
    
    await interaction.edit_original_response(content=f"The game is set, all players have been sent to their rooms for the first night")
    
    declareGamePhase() # Declare the time, the first night
    
            
#Run the bot
bot.run(TOKEN)