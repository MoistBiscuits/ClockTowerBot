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
import asyncio
import logging

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')

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
            
    def getPlayers(self,guild: discord.Guild): #Gets the most recent instance of the players in the game as a List{dsicord.Member}
        value = []
        playerIds = []
        for member in self.players:
            playerIds.append(member.id)
        for member in guild.members:
            if member.id in playerIds:
                value.append(member)
        return value
    
    def addPrivateRoom(self,player: discord.Member,room: discord.channel):
        if player in self.players:
            self.playerChannelDict[player] = room
            
    def getRoomOfPlayer(self,player:discord.Member) -> discord.VoiceChannel:
        if player in self.players:
            return self.playerChannelDict[player]
        
    def incrementDayPhase(self):
        if self.dayPhase == 3: #if dusk
            self.incrementDayCount()
        self.dayPhase = (self.dayPhase + 1) % 4
        
    #Advance current phase to next phase, incrementing day count if needed
    def advanceDayPhase(self,newPhase: int):
        if newPhase <= self.dayPhase: # If less than or equal to, its the next day
            self.incrementDayCount()
        self.dayPhase = newPhase
        
    #Set the current day and phase
    def setTime(self,day:int,phase: int):
        self.dayPhase = phase
        self.gameDay = day
        
    def incrementDayCount(self):
        self.gameDay += 1
        
    def getAllUsers(self,guild: discord.Guild): #Returns all players and the storyteller as a List[discord.Member]
        value = self.getPlayers(guild)
        for member in guild.members:
            if member.id == self.storyteller.id:
                value.append(member)
        return value
    
    def getGameTimeMsg(self) -> str: #Returns a string that summaries the current day phase
        if self.dayPhase == 0: #night
            if self.gameDay == 1: #First night
                return f"It is Night 1, All players go to your room and wait to learn your role from the storyteller"
            else:
                return f"It is Night {self.gameDay}, all players return to your rooms"
        elif self.dayPhase == 1: #dawn
            return f"It is the dawn of Day {self.gameDay}, all players gather in the town square"
        elif self.dayPhase == 2: #day
            return f"It is the midday of Day {self.gameDay}, all players are free to move about and chat"
        elif self.dayPhase == 3: #dusk
            return f"It is the dusk of Day {self.gameDay}, all players gather in the town square for nominations"
        else: #error state, should never be reached
            raise Exception(f"Expect dayPhase to be in range (0,3) got {self.dayPhase}") 
        
    
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
        interaction.guild.default_role: discord.PermissionOverwrite(read_messages=True,send_messages=False),
        dayRole: discord.PermissionOverwrite(send_messages=True),
        storyRole: discord.PermissionOverwrite(send_messages=True)
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
    roamRole = get(interaction.guild.roles, name=Role.roam.value)
    for i in range(0,count):
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            roamRole: discord.PermissionOverwrite(read_messages=True),
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
    if gameState.getPlayers(interaction.guild) == []:
        await interaction.response.send_message(content=f"Cannot setup channels with no added players")
        return
    try:
        await interaction.response.defer(thinking=True, ephemeral=True)
        category = get(interaction.guild.categories,name=ChannelNames.category.value)
        if category: # If category already exists delete it adn its channels
            print(f"Category already exists, delete all channels inside and it")
            channels = category.channels
            for channel in channels:
                await channel.delete()
            await category.delete()
            
        #Create category
        gameState.channels.category = await interaction.guild.create_category(ChannelNames.category.value)

        #Create the channels needed for the game to run
        await createStoryText(interaction)
        await createStoryVoice(interaction)
        await createTownText(interaction)
        await createTownVoice(interaction)
        await createPublicVoice(interaction,8)
        await createPrivateVoice(interaction,gameState.getPlayers(interaction.guild))
        gameState.channelReady = True
        await interaction.edit_original_response(content=f"Succesfully created channels")
    except Exception as e:
        print("Exception has occured while setting up channels:",e)
        gameState.channelReady = False
        await interaction.edit_original_response(content=f"Something went setting up channels")
        raise e
    
"""
Sets the roles of a list of users
guild - guild of the sver
members - memers to change roles of
roles - The bot specific roles to set to
"""
async def setRoles(guild:discord.Guild, members: List[discord.Member], roles: List[discord.Member]):
    try:
        excessRoleList = [
            get(guild.roles, name=Role.alive.value),
            get(guild.roles, name=Role.dead.value),
            get(guild.roles, name=Role.day.value),
            get(guild.roles, name=Role.night.value),
            get(guild.roles, name=Role.roam.value),
        ]
        for member in members:
            newRoles = member.roles
            for role in excessRoleList:
                if (role in newRoles):
                    newRoles.remove(role)
            for role in roles:
                if not (role in newRoles):
                    newRoles.append(role)
            print(f"user: {member} roles {roles}")
            await member.edit(roles=newRoles)
        
    except Exception as e:
        raise e
    
async def alivePlayers(guild: discord.Guild, members: List[discord.Member]): #give players the alive role, remove dead role if they have it
    try: #Roles might not exist or calling members may fail
        aliveRole = get(guild.roles, name=Role.alive.value)
        deadRole = get(guild.roles, name=Role.dead.value)
        for member in members:
            roles = member.roles
            if deadRole in roles:
                roles.remove(deadRole)
            if not (aliveRole in member.roles):
                roles.append(aliveRole)
            member.edit(roles=roles)
    except Exception as e:
        raise e
    
async def killPlayers(guild: discord.Guild, members: List[discord.Member]): #give players the dead role, remove alive role if they have it
    try: #Roles might not exist or calling members may fail
        aliveRole = get(guild.roles, name=Role.alive.value)
        deadRole = get(guild.roles, name=Role.dead.value)
        for member in members:
            roles = member.roles
            if aliveRole in roles:
                roles.remove(aliveRole)
            if not (deadRole in member.roles):
                roles.append(deadRole)
            member.edit(roles=roles)
    except Exception as e:
        raise e
    
async def unlockPlayersPrivateRoom(guild: discord.Guild ,members: List[discord.Member]): #Give players permission to enter their private room
    try: #Roles might not exist or calling members may fail
        for member in members:
            privateRoom = gameState.getRoomOfPlayer(member) #player's private channel
            await privateRoom.set_permissions(member,read_messages=True)
    except Exception as e:
        raise e
    
async def lockPlayersPrivateRoom(guild: discord.Guild,members: List[discord.Member]): #Remove players permission to enter their private room
    try: #Roles might not exist or calling members may fail
        for member in members:
            privateRoom = gameState.getRoomOfPlayer(member) #player's private channel
            await privateRoom.set_permissions(member,read_messages=False)
    except Exception as e:
        raise e

async def sendPlayersToPrivateRoom(guild: discord.Guild, members: List[discord.Member]): #give players the Night role, remove day and roam roles and send them to their private room
    try: #Roles might not exist or calling members may fail
        dayRole = get(guild.roles, name=Role.day.value)
        nightRole = get(guild.roles, name=Role.night.value)
        roamRole = get(guild.roles, name=Role.roam.value)

        #Players need to be able to access their room to be sent to it
        await unlockPlayersPrivateRoom(guild,members)        
        
        for member in members:
            roles = member.roles
            if dayRole in roles:
                roles.remove(dayRole)
            if roamRole in roles:
                roles.remove(roamRole)
            if not (nightRole in roles):
                roles.append(nightRole)
            await member.edit(roles=roles) #You must add roles atmoically or errors occour, it sucks
    except Exception as e:
        raise e
    
    for member in members:
        try: #Try to move them from current vc to new vc, fails is user is in no vc
            privateRoom = gameState.getRoomOfPlayer(member) #player's private channel
            await member.move_to(privateRoom) #move them to their channel 
        except Exception as e:
            print(e)
    
async def movePlayersToPrivateRoom(guild: discord.Guild, members: List[discord.Member]): #move players to their private room without changing roles
    #Players need to be able to access their room to be sent to it
    await unlockPlayersPrivateRoom(guild,members)    

    for member in members:
        try: #Try to move them from current vc to new vc, fails is user is in no vc
            privateRoom = gameState.getRoomOfPlayer(member) #player's private channel
            await member.move_to(privateRoom) #move them to their channel 
        except Exception as e:
            print(e)

async def sendPlayersToTown(guild: discord.Guild, members: List[discord.Member]): #Give players the Day Role, remove night and roam roles and force them into town
    try: #Roles might not exist or calling members may fail
        dayRole = get(guild.roles, name=Role.day.value)
        nightRole = get(guild.roles, name=Role.night.value)
        roamRole = get(guild.roles, name=Role.roam.value)

        #Players should be blocked from their rooms
        await lockPlayersPrivateRoom(guild, members)        

        for member in members:
            roles = member.roles
            if nightRole in roles:
                roles.remove(nightRole)
            if roamRole in roles:
                roles.remove(roamRole)
            if not (dayRole in roles):
                roles.append(dayRole)
            await member.edit(roles=roles) #You must add roles atmoically or eronious errors occour, it sucks I hate asynchronous programming
    except Exception as e:
        raise e
    
    town = gameState.channels.townVoice
    for member in members:
        try: #Try to move them from current vc to new vc, fails is user is in no vc
            await member.move_to(town) #move them to their channel 
        except Exception as e:
            print(e)
            
async def movePlayersToTown(guild: discord.Guild, members: List[discord.Member]): #Moves players to townsquare without chaing their perms
    town = gameState.channels.townVoice
    for member in members:
        try: #Try to move them from current vc to new vc, fails is user is in no vc
            await member.move_to(town) #move them to their channel 
        except Exception as e:
            print(e)    

async def allowPlayersRoam(guild: discord.Guild, members: List[discord.Member]): #Give players the Roam role, lets them visit public rooms
    try:
        roamRole = get(guild.roles, name=Role.roam.value)
        for member in members:
            print(f"user: {member} roles {member.roles}")
            if not (roamRole in member.roles):
                await member.add_roles(roamRole)
    except Exception as e:
        raise e
    
async def denyPlayersRoam(guild: discord.Guild, members: List[discord.Member]): #Remove player(s)'s Roam role if they have it, denying them from public rooms
    try:
        roamRole = get(guild.roles, name=Role.roam.value)
        for member in members:
            print(f"user: {member} roles {member.roles}")
            if roamRole in member.roles:
                await member.remove_roles(roamRole)
    except Exception as e:
        raise e
    
async def handlePlayerMovement(guild: discord.guild): #Handles player movement based on the phase of the game
    if gameState.dayPhase == 0: #Night movement, send to private room
        await sendPlayersToPrivateRoom(guild,gameState.getPlayers(guild))
    elif gameState.dayPhase == 1: #Dawn movement, bring to town, announce night actions
        await sendPlayersToTown(guild,gameState.getPlayers(guild))
    elif gameState.dayPhase == 2: #Midday movement, allow players to privately talk
        await movePlayersToTown(guild,gameState.getPlayers(guild))
        await allowPlayersRoam(guild,gameState.getPlayers(guild))
    elif gameState.dayPhase == 3: #Dusk movement, deny players private talk, bring to town for nominations
        await movePlayersToTown(guild,gameState.getPlayers(guild))
        await denyPlayersRoam(guild,gameState.getPlayers(guild))
    else: #Error state, should not be called
        raise Exception(f"dayPhase: {gameState.dayPhase} not in range o to 3")
    
async def declareGamePhase(): #Bot states the phase of the game into chat
    await gameState.channels.getTownText().send(gameState.getGameTimeMsg())

@bot.tree.command(
    name="start_game",
    description="Starts a BoTC game: setup players, storyteller and channel first"
)
async def startGame(interaction: discord.Interaction):
    if gameState.active:
        await interaction.response.send_message(content=f"A game is already running, end it before starting a new one")
        return
    if not gameState.channelReady:
        await interaction.response.send_message(content=f"Channels have not been setup yet, run /setup_chanels to create and set them to the bot")
        return
    
    await interaction.response.defer(thinking=True) #Let discord know the bot is working through a proccess   

    await setRoles(interaction.guild,gameState.getPlayers(interaction.guild),[get(interaction.guild.roles, name=Role.alive.value),get(interaction.guild.roles, name=Role.player.value),get(interaction.guild.roles, name=Role.night.value)]) #Remove any excess flag roles that users might have for some reason
    
    await movePlayersToPrivateRoom(interaction.guild,gameState.getPlayers(interaction.guild)) #move all players to their private room
    gameState.active = True    

    await interaction.edit_original_response(content=f"The game is set, all players have been sent to their rooms for the first night")
    
    await declareGamePhase() # Declare the time, the first night
    
@bot.tree.command(
    name="advance_phase",
    description="Advances the current game to the next phase or a set time if given"
)
#Which next phase to jump to, advaces the day counter if needed
@app_commands.choices(time=[ 
        app_commands.Choice(name="Night", value=0),
        app_commands.Choice(name="Dawn", value=1),
        app_commands.Choice(name="Midday", value=2),
        app_commands.Choice(name="Dusk", value=3),
])
@app_commands.describe(time="The next phase to skip the game to (optional)")
@app_commands.describe(time="The day number to skip the game to (optional)")
async def nextGamePhase(interaction: discord.Interaction, time: app_commands.Choice[int] = None, day: int = None):
    await interaction.response.defer(thinking=True,ephemeral=True)  

    if not gameState.active: # Cant advance an inactive game
        await interaction.edit_original_response(content=f"Requires a game to be running")
        return
    
    if (day != None) and (day < 0): # Cant pass negative value
        await interaction.edit_original_response(content=f"Cannot set day number to: {day}")
        return
    
    if time == None: #If no argument passed
        if not (day == None):
            gameState.gameDay = day
        gameState.incrementDayPhase()
    else:
        if day == None: #if a day was not given
            gameState.advanceDayPhase(time.value)
        else:
            gameState.setTime(day,time.value)
        
    await handlePlayerMovement(interaction.guild)

    await declareGamePhase()
    
    await interaction.edit_original_response(content=f"Advanced to day: {gameState.gameDay}, phase: {gameState.dayPhase} and attempted to move players to the correct channel")
    
@bot.tree.command(
    name="retry_player_movement",
    description="Attempts to move all players according to the day phase"
)
async def retryPlayerMovement(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True,ephemeral=True)    

    if not gameState.active:
        await interaction.edit_original_response(content=f"Requires a game to be running")
        return
    
    await handlePlayerMovement(interaction.guild)
    
    await interaction.edit_original_response(content=f"Attempted to move players to the appropriate channel")

#Run the bot
bot.run(TOKEN,log_handler=handler,log_level=logging.DEBUG)