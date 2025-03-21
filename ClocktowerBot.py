import os
import discord
from enum import Enum
from discord.ext import commands   # Import the discord.py extension "commands"
from discord import Embed, Interaction, app_commands
from discord.utils import get
from dotenv import load_dotenv
from typing import List
from typing import TypedDict
import asyncio
import logging
import xml.etree.ElementTree as ET

#Dictionary types
RoomLock = TypedDict('Roomlock', {'channel': discord.VoiceChannel, 'locked': bool})
RoomMembers = TypedDict('RoomUsers', {'channel': discord.VoiceChannel, 'members': List[discord.Member]})

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

class VotingType(Enum): #Voting styles that may be used when a player nominates another player
    circleTally = 0 #Defualt voting method used in the official rules, player votes counted clockwise from nominee
    countdownTally = 1 #Players vote while being able to see other players, after countdown players votes are tallied,
    #Used in place to circle tally if latency is bad or for specific characters abilities (see Cultleader)
    blindCountdownTally = 2 #Players vote without being able to see other players, after countdown player votes are tallied,
    #Used specifically for the Organ Grinders ability, which prevents players from seeing who votes who
    pointCountdown = 3 #Players vote on a player publicly, after a countdown votes are tallied.
    #Used specifically for the Boomdandies ability, who requires players pick a specific player to kill.

class Player: #Class that holds the data on a player
    def __init__(self,member: discord.member):
        self.member: discord.Member = member
        self.isAlive = True #If the game registers them as alive
        self.hasGhostVote = True #If the game registers the player as having their ghost vote

    def setIsAlive(self,bool):
        self.isAlive = bool

    def setHasGhostVote(self,bool):
        self.hasGhostVote = bool

    def consumeGhostVote(self):
        if not (self.isAlive):
            self.hasGhostVote = False

    def canNominate(self) -> bool:
        return self.isAlive
    
    def canVote(self) -> bool:
        if self.isAlive:
            return True
        elif self.hasGhostVote:
            return True
        else:
            return False


class GameState: #Class the holds the users set for the game
    def __init__(self):
        self.storyteller = None #Meber who is the storyteller
        self.players: List[Player] = [] #List of players in the game
        self.active = False #Whever the game is running or not
        self.channelReady = False #Whever the correct discord channels are in place
        self.channels = GameChannels() #Store game channels here
        self.channelLocks = ChannelLocks() #Stores player rights to talk in public rooms
        self.playerChannelDict = {} #Dictionary to stores which players have which private room
        self.lockCooldown = 8 #How much time (in secs) it takes for a newly joined public room to lock
        self.openCooldown = 12 # How much time (in secs) a public room is open when a user runs the /open_door command
        self.votingCircledownDelay = 3 # How much delay (in secs) the circle vote has between each players vote being counted
        self.votingCountdownDelay = 10 # How much time (in secs) a countdown vote has until it ends
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
        
    def endGame(self):
        self.active = False
        self.channelReady = False
        self.players = []
        self.storyteller = None
        self.playerChannelDict = {}

    def setStoryTeller(self,member: discord.Member):
        self.storyteller = member

    def isMemberPlayer(self,member:discord.Member) -> bool:
        for player in self.players:
            if player.member == member:
                return True
        return False
        
    def addPlayer(self,player: discord.Member):
        if not (player in self.players):
            self.players.append(Player(player))

    def removePlayer(self,player: discord.Member):
        if player in self.players:
            self.players.remove(Player(player))
            
    def getPlayersAsMembers(self,guild: discord.Guild) -> List[discord.Member]: #Gets the most recent instance of the players in the game as a List{dsicord.Member}
        value = []
        playerIds = []
        for player in self.players:
            playerIds.append(player.member.id)
        for member in guild.members:
            if member.id in playerIds:
                value.append(member)
        return value
    
    def getPlayers(self) -> List[Player]:
        return self.players
    
    def addPrivateRoom(self,player: discord.Member,room: discord.channel):
        if self.isMemberPlayer(player):
            self.playerChannelDict[player] = room
            
    def getRoomOfPlayer(self,player:discord.Member) -> discord.VoiceChannel:
        if self.isMemberPlayer(player):
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
        value = self.getPlayersAsMembers(guild)
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
        
    def filterPlayers(self,members: List[discord.Member]) -> List[discord.Member]: #Given a list of members, returns which are players
        data = []
        for member in members:
            if self.isMemberPlayer(member) and (not (member in data)):
                data.append(member)
        return data

        
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

"""
Public rooms in the bot are designed so that once users join a private room, it prevents other users joining later from listening in
This is done so players can have private conservsations aka whisper to eachother, a vital part of the game
The class holds which channels are locked and which users are allowed to speak undeafened in them
"Locking" a room in this context refers to deafening non-whitelisted members
"""
class ChannelLocks: #Holds the data on which discord channels auto deafen users when they join
    def __init__(self, roomLock: RoomLock = dict(), roomMembers: RoomMembers = dict()):
        self.roomLock = roomLock #Dict (channel -> bool) if a channel is in the lcoked state, new users are forced deafened
        self.roomMembers = roomMembers #Dict (channel -> [members]) which users are allowed to speak in the channel
        
    def lockRoom(self,room: discord.VoiceChannel): #Lock a room
        if (room in self.roomLock) and (room in self.roomMembers):
            self.roomLock[room] = True
            
    def unlockRoom(self,room: discord.VoiceChannel): #Unlock a room
        if room in self.roomLock:
            self.roomLock[room] = False
            
    def isRoomLocked(self,room: discord.VoiceChannel) -> bool: #Returns if room is lcoked
        if room in self.roomLock:
            return self.roomLock[room]
        else:
            return False
        
    def addMembersToRoom(self,room: discord.VoiceChannel,members: List[discord.Member]): #Adds members to a room that allows them to speak when it is locked, doesnt lock by itself
        if room in self.roomMembers:
            for member in members:
                if not (member in self.roomMembers[room]):
                    self.roomMembers[room].append(member)
                    
    def removeMembersToRoom(self,room: discord.VoiceChannel,members: List[discord.Member]): #removes members 
        if room in self.roomMembers:
            for member in members:
                if member in self.roomMembers[room]:
                    self.roomMembers[room].remove(member)
                    
    def getWhitelistedMembers(self,room:discord.VoiceChannel) -> List[discord.Member]: #Returns which users are allowed to talk in a room if it is locked
        if room in self.roomMembers:
            return self.roomMembers[room]
        
class CharacterData: #handles the reading of characters.xml and outputs character data
    def __init__(self,path: str):
        #XML parser
        print(os.getcwd())
        self.tree = ET.parse(path) #Holds character lists for all the editions
        self.choices = self.getChoices()
        
    def getChoices(self) -> List[app_commands.Choice]: #Retuns the slash command choices
        root = self.tree.getroot()
        choices = []
        for edition in root.findall('edition'):
            for character in edition.findall('character'):
                choices.append(app_commands.Choice(name=character.attrib['name'],value=character.attrib['name']))
        return choices
    
    def getEmbedOfCharacter(self,characterName: str) -> discord.Embed | None: #Gets a given character's information as a discord embed
        root = self.tree.getroot()
        embed = None
        for edition in root.findall('edition'):
            for character in edition.findall('character'):
                if character.attrib['name'] == characterName: #If this is our character
                    embed = discord.embeds.Embed()
                    embed.colour = discord.Color.brand_red()
                    
                    embed.title = f"Character Summary"
                    embed.add_field(name="Character",value=characterName,inline=False)
                    embed.add_field(name="Ability",value=character.find('summary').text,inline=False)
                    embed.add_field(name="Type",value=character.find('type').text,inline=False)
                    embed.add_field(name="Wiki link",value=f"[Character info]({character.find('wiki').text})")
                    
                    if character.find('image').text != "None":
                        embed.set_thumbnail(url=character.find('image').text)

                    return embed
        return None
   
#logging
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')



#Bot token
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

#Bot
intents = discord.Intents.all()
bot = commands.Bot(intents=intents,command_prefix="!")    

class GameCommands(commands.Cog): #Cog that holds all the bots commands for running a clocktower game    
    #locks
    commandLock = asyncio.Lock() #Asyncio lock that handles discord command execution
    voiceStateLock = asyncio.Lock() #Asyncio lock that handles member join channel events

    gameState = GameState() # public game state
    characterData = CharacterData('characters.xml') #public Handler reading and dsplay of character roles
    
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self): #On bot startup
        print(f"Logged in as {bot.user.name}")
        try:
            synced = await bot.tree.sync() #Sync slash command to the server
            print(f"Synced {len(synced)} commands.")
        except Exception as e:
            print("Exception has occured while syncing tree:",e)

    @app_commands.command(name="ping")
    async def ping(self,interaction: discord.Interaction): # a slash command will be created with the name "ping"
        await interaction.response.send_message(content=f"Pong!",ephemeral=True)
        
    @app_commands.command(
        name="setup_roles",
        description="Inits user roles for the bot",
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.guild_only()
    async def setupRoles(self,interaction: discord.Interaction): # create roles used by the bot if they do not exist
        await interaction.response.defer(thinking=True,ephemeral=True)
        for role in Role:
            if get(interaction.guild.roles, name=role.value):
                print(f"Role: {role.value} already exists")
            else:
                await interaction.guild.create_role(name=role.value, colour=discord.Colour(0x0062ff))
        await interaction.edit_original_response(content="Initialised roles")
     
    @app_commands.command(
        name="set_storyteller",
        description="set which user is the story teller for the next game",
    )
    @app_commands.describe(member="The member to make the story teller")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_roles=True)
    async def setStoryTeller(self,interaction: discord.Interaction, member: discord.Member): # Set who is the storyteller for a unactive game
        await interaction.response.defer(thinking=True)
        await self.commandLock.acquire()
        if (self.gameState.active):
            await interaction.edit_original_response(content="You cannot change the storyteller during an active game")
            self.commandLock.release()
        else:
            print(member)
            try: #Roles might not exist
                storyRole = get(interaction.guild.roles, name=Role.storyTeller.value) #Get storyteller role from server
                if (member in self.gameState.getPlayersAsMembers(interaction.guild)): #If new storyteller is a player
                    playerRole = get(interaction.guild.roles, name=Role.player.value) #Get player role from server
                    if (playerRole in member.roles):
                        await member.remove_roles(playerRole) #Remove the role
                    self.gameState.removePlayer(member) #remove them from player list
                if (self.gameState.storyteller != None): #If there was a previous storyteller, remove their role
                    await self.gameState.storyteller.remove_roles(storyRole)
                await member.add_roles(storyRole)
                self.gameState.setStoryTeller(member)
                await interaction.edit_original_response(content=f"{member} is now the storyteller")
            except Exception as e:
                print("Exception has occured while swappign storyteller:",e)
                await interaction.edit_original_response(content="Something went wrong swapping storytellers")
            finally:
                self.commandLock.release()
            
    @app_commands.command(
        name="add_player",
        description="Add a player to the next game",
    )
    @app_commands.describe(member="The member to add")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_roles=True)
    async def addPlayer(self,interaction: discord.Interaction, member: discord.Member): # add one player to an active game
        await interaction.response.defer(thinking=True)
        await self.commandLock.acquire()
        if (member == self.gameState.storyteller):
            await interaction.edit_original_response(content="You cannot make the storyteller a player")
            self.commandLock.release()
        elif (self.gameState.active):
            await interaction.edit_original_response(content="You cannot add players during an active game")
            self.commandLock.release()
        else:
            print(member)
            try: #Roles might not exist
                playerRole = get(interaction.guild.roles, name=Role.player.value) #Get player role from server
                if not (playerRole in member.roles):
                    await member.add_roles(playerRole) #Give them the player role if they do not have it already
                self.gameState.addPlayer(member) #Add player to game
                self.gameState.channelReady = False #Change of players means a new channel setup must be made
                await interaction.edit_original_response(content=f"Added player: {member} to the game")
            except Exception as e:
                print("Exception has occured while assigning players:",e)
                await interaction.edit_original_response(content="Something went wrong assigning players")
            finally:
                self.commandLock.release()
            
    @app_commands.command(
        name="remove_player",
        description="Remove a player from the next game",
    )
    @app_commands.describe(member="The member to remove")
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.guild_only()
    async def removePlayer(self,interaction: discord.Interaction, member: discord.Member): # remove one player from an active game
        await interaction.response.defer(thinking=True)
        await self.commandLock.acquire()
        if (self.gameState.active):
            await interaction.response.edit_original_response(content="You cannot remove players during an active game")
            self.commandLock.release()
        else:
            print(member)
            try: #Roles might not exist
                playerRole = get(interaction.guild.roles, name=Role.player.value) #Get player role from server
                if (playerRole in member.roles):
                     await member.remove_roles(playerRole) #Remove the role
                self.gameState.removePlayer(member) #Remove player to game
                self.gameState.channelReady = False #Change of players means a new channel setup must be made
                await interaction.response.edit_original_response(content=f"Removed player: {member}")
            except Exception as e:
                print("Exception has occured while removing players:",e)
                await interaction.response.edit_original_response(content="Something went wrong removing players")
            finally:
                self.commandLock.release()
     
    @app_commands.command(
        name="show_game",
        description="Show the current state of the bot",
    )
    @app_commands.guild_only()
    async def printGameState(self,interaction: discord.Interaction): #Print game state for testing
        await interaction.response.defer(thinking=True)
        await self.commandLock.acquire()
        try:
            embed = discord.embeds.Embed()
            embed.colour = discord.Color.brand_red()
        
            #Storyteller field
            if (self.gameState.storyteller != None):
                embed.add_field(name="Storyteller: ",value=f"<@{self.gameState.storyteller.id}>",inline=False)
            else:
                embed.add_field(name="Storyteller: ",value=f"No one is set as storyteller yet",inline=False)

            if (self.gameState.active == False): #If the game is not currently active
                embed.title = f"Current Users for the next game"
            
                #Players field
                embed.add_field(name="**-Players-**",value="",inline=False)       
                if (len(self.gameState.players) > 0): #We have some players set
                    for i in range(0, len(self.gameState.players)):
                        embed.add_field(name=f"Player {i+1}: ",value=f"<@{self.gameState.players[i].member.id}>",inline=False)
                else: #No Players
                    embed.add_field(name="No players have been added",value="",inline=False)
                
                if self.gameState.channelReady:
                    embed.set_footer(text=f"Run /start_game to start the game when ready")
                else:
                    embed.set_footer(text=f"Once all players and storyteller are added, run /setup_channels to prepare the game")
            else: #If the game is active
                embed.title = "Current game"
            
                #Players field
                embed.add_field(name="**Players**",value="",inline=False)
                if (len(self.gameState.players) > 0): #We have some players set
                    for i in range(0, len(self.gameState.players)):
                        if self.gameState.players[i].isAlive:
                            embed.add_field(name=f"Player {i+1}: ",value=f"<@{self.gameState.players[i].member.id}> :bust_in_silhouette:",inline=False)
                        elif self.gameState.players[i].hasGhostVote:
                            embed.add_field(name=f"Player {i+1}: ",value=f"<@{self.gameState.players[i].member.id}> :skull::large_blue_diamond: ",inline=False)
                        else:
                            embed.add_field(name=f"Player {i+1}: ",value=f"<@{self.gameState.players[i].member.id}> :skull:",inline=False)
                        
                else: #No Players
                    embed.add_field(name="No players have been added",value="",inline=False)
                
                embed.set_footer(text=f"Player list is cyclic: Player 1 and Player {len(self.gameState.players) + 1} are neighbours")
            await interaction.edit_original_response(embed=embed)
        except Exception as e:
             print("Exception has occured while printing game state:",e)
             await interaction.edit_original_response(content="Something went wrong")
        finally:
            self.commandLock.release()
    
    @app_commands.command(
        name="sync_roles",
        description="Syncs the bot to the bot-specific roles on the server and removes excess roles",
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.guild_only()
    async def syncRoles(self,interaction: discord.Interaction): #Sync the discord roles to the bots game state, if possible
    
        await interaction.response.defer(thinking=True)
        await self.commandLock.acquire()
        if self.gameState.active: #Changing the playlist mid-game will break things
            await interaction.edit_original_response(content="You cannot change the game's state while a match is active")
            self.commandLock.release()
        else:
            try: #Roles might not exist or calling members may fail
                memberList = interaction.guild.fetch_members() #Get all the servers members, might be dangerous but this bot has a limited scope in users
                newGameState = GameState()
                playerRole = get(interaction.guild.roles, name=Role.player.value) #Get player role from server
                storyRole = get(interaction.guild.roles, name=Role.storyTeller.value) #Get storyteller role from server
                async for member in memberList:
                    if (storyRole in member.roles) and (playerRole in member.roles): #A user is both storyteller and player
                        await interaction.edit_original_response(content=f"{member} cannot be both a player and a storyteller")
                        return
                    if (storyRole in member.roles) and (newGameState.storyteller != None): #If a user is set as storyteller while another is a storyteller
                        await interaction.edit_original_response(content=f"{member} and {newGameState.storyteller} cannot be both be storytellers")
                        return
                    if playerRole in member.roles:
                        newGameState.addPlayer(member)
                    if storyRole in member.roles:
                        newGameState.setStoryTeller(member)
                    
                self.gameState = newGameState #Update gamestate
                self.gameState.channelReady = False #Change of players means a new channel setup must be made
                await interaction.edit_original_response(content=f"Synced member roles to the bot successfully")
            except Exception as e:
                print("Exception has occured while syncing player roles:",e)
                await interaction.edit_original_response(content="Something went wrong syncing roles")
            finally:
                self.commandLock.release()
            
    async def createStoryText(self,interaction: discord.Interaction): #Create storyteller text channel
        storyRole = get(interaction.guild.roles, name=Role.storyTeller.value) #Get storyteller role from server
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            storyRole: discord.PermissionOverwrite(read_messages=True)
        }
        self.gameState.channels.storytellerText = await interaction.guild.create_text_channel(name=ChannelNames.storytellerText.value, overwrites=overwrites, category=self.gameState.channels.category)
    
    async def createStoryVoice(self,interaction: discord.Interaction): #Create storyteller voice channel
        storyRole = get(interaction.guild.roles, name=Role.storyTeller.value) #Get storyteller role from server
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            storyRole: discord.PermissionOverwrite(read_messages=True)
        }
        self.gameState.channels.storytellerVoice = await interaction.guild.create_voice_channel(name=ChannelNames.storytellerVoice.value, overwrites=overwrites, category=self.gameState.channels.category)
    
    async def createTownText(self,interaction: discord.Interaction): #Create hub voice channel
        dayRole = get(interaction.guild.roles, name=Role.day.value) #Get day role from server
        storyRole = get(interaction.guild.roles, name=Role.storyTeller.value)
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=True,send_messages=False),
            dayRole: discord.PermissionOverwrite(send_messages=True),
            storyRole: discord.PermissionOverwrite(send_messages=True)
        }
        self.gameState.channels.townText = await interaction.guild.create_text_channel(name=ChannelNames.townText.value, overwrites=overwrites, category=self.gameState.channels.category)
    
    async def createTownVoice(self,interaction: discord.Interaction): #Create hub text channel
        dayRole = get(interaction.guild.roles, name=Role.day.value) #Get day role from server
        storyRole = get(interaction.guild.roles, name=Role.storyTeller.value)
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            dayRole: discord.PermissionOverwrite(read_messages=True),
            storyRole: discord.PermissionOverwrite(read_messages=True)
        }
        self.gameState.channels.townVoice = await interaction.guild.create_voice_channel(name=ChannelNames.townVoice.value, overwrites=overwrites, category=self.gameState.channels.category)

    def getInitRoomName(self,playerNumber: int): #Returns the name of a private room that should be used to create a players room
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
        #TODO find a cleaner way to needing more room names than expected players
        if playerNumber >= len(privateRoomNames): #If list overflows
            name += " "
            name += str(playerNumber // len(privateRoomNames)) #Append a unique number to it (e.g. Blue Room 2)
        return name
    
    async def createPrivateVoice(self,interaction: discord.Interaction, players: List[discord.Member]): #Create private rooms for each player
        storyRole = get(interaction.guild.roles, name=Role.storyTeller.value)
        for i in range(0,len(players)):
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                players[i]: discord.PermissionOverwrite(read_messages=True),
                storyRole: discord.PermissionOverwrite(read_messages=True)
            }
            room = await interaction.guild.create_voice_channel(name=self.getInitRoomName(i), overwrites=overwrites, category=self.gameState.channels.category)
            self.gameState.channels.addPrivateRoom(room) # Add channel to channels
            self.gameState.addPrivateRoom(players[i],room) # pair player to channel
        
    async def createPublicVoice(self,interaction: discord.Interaction,count=8): #Creates the given amount of public rooms
        storyRole = get(interaction.guild.roles, name=Role.storyTeller.value)
        roamRole = get(interaction.guild.roles, name=Role.roam.value)
        for i in range(0,count):
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False,connect=False),
                roamRole: discord.PermissionOverwrite(read_messages=True,connect=True),
                storyRole: discord.PermissionOverwrite(read_messages=True,connect=True)
            }
            room = await interaction.guild.create_voice_channel(name=ChannelNames.dayRooms.value[i], overwrites=overwrites, category=self.gameState.channels.category)
            self.gameState.channels.addPublicRoom(room)

    def setupChannelLocks(self,channels: List[discord.VoiceChannel]):
        roomLock = {}
        roomMembers = {}
        for channel in channels:
            roomLock[channel] = False
            roomMembers[channel] = []
        self.gameState.channelLocks = ChannelLocks(roomLock,roomMembers)

    @app_commands.command(
        name="setup_channels",
        description="creates the channels needed for the game if they do not exist",
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.guild_only()
    async def setupChannels(self,interaction: discord.Interaction): #Creates the text and voice channels for the bot#
        await interaction.response.defer(thinking=True,ephemeral=True)
        await self.commandLock.acquire()
        if self.gameState.active:
            await interaction.edit_original_response(content=f"Cannot setup channels during an active game")
            self.commandLock.release()
            return
        if self.gameState.getPlayersAsMembers(interaction.guild) == []:
            await interaction.edit_original_response(content=f"Cannot setup channels with no added players")
            self.commandLock.release()
            return
        try:
            category = get(interaction.guild.categories,name=ChannelNames.category.value)
            if category: # If category already exists delete it adn its channels
                print(f"Category already exists, delete all channels inside and it")
                channels = category.channels
                for channel in channels:
                    await channel.delete()
                await category.delete()
            
            #Create category
            self.gameState.channels.category = await interaction.guild.create_category(ChannelNames.category.value)

            #Create the channels needed for the game to run
            await self.createStoryText(interaction)
            await self.createStoryVoice(interaction)
            await self.createTownText(interaction)
            await self.createTownVoice(interaction)
            await self.createPublicVoice(interaction,8)
            await self.createPrivateVoice(interaction,self.gameState.getPlayersAsMembers(interaction.guild))
        
            self.setupChannelLocks(self.gameState.channels.publicRooms)
        
            self.gameState.channelReady = True
            await interaction.edit_original_response(content=f"Succesfully created channels")
        except Exception as e:
            print("Exception has occured while setting up channels:",e)
            self.gameState.channelReady = False
            await interaction.edit_original_response(content=f"Something went setting up channels")
        finally:
            self.commandLock.release()
    
    """
    Sets the roles of a list of users
    guild - guild of the sver
    members - memers to change roles of
    roles - The bot specific roles to set to
    """
    async def setRoles(self,guild:discord.Guild, members: List[discord.Member], roles: List[discord.Member]):
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
    
    async def alivePlayers(self,guild: discord.Guild, members: List[discord.Member]): #give players the alive role, remove dead role if they have it
        try: #Roles might not exist or calling members may fail
            aliveRole = get(guild.roles, name=Role.alive.value)
            deadRole = get(guild.roles, name=Role.dead.value)
            for member in members:
                roles = member.roles
                if deadRole in roles:
                    roles.remove(deadRole)
                if not (aliveRole in member.roles):
                    roles.append(aliveRole)
                await member.edit(roles=roles)
        except Exception as e:
            raise e
    
    async def killPlayers(self,guild: discord.Guild, members: List[discord.Member]): #give players the dead role, remove alive role if they have it
        try: #Roles might not exist or calling members may fail
            aliveRole = get(guild.roles, name=Role.alive.value)
            deadRole = get(guild.roles, name=Role.dead.value)
            for member in members:
                roles = member.roles
                if aliveRole in roles:
                    roles.remove(aliveRole)
                if not (deadRole in member.roles):
                    roles.append(deadRole)
                await member.edit(roles=roles)
        except Exception as e:
            raise e
    
    async def unlockPlayersPrivateRoom(self,guild: discord.Guild ,members: List[discord.Member]): #Give players permission to enter their private room
        try: #Roles might not exist or calling members may fail
            for member in members:
                privateRoom = self.gameState.getRoomOfPlayer(member) #player's private channel
                await privateRoom.set_permissions(member,read_messages=True)
        except Exception as e:
            raise e
    
    async def lockPlayersPrivateRoom(self,guild: discord.Guild,members: List[discord.Member]): #Remove players permission to enter their private room
        try: #Roles might not exist or calling members may fail
            for member in members:
                privateRoom = self.gameState.getRoomOfPlayer(member) #player's private channel
                await privateRoom.set_permissions(member,read_messages=False)
        except Exception as e:
            raise e

    async def sendPlayersToPrivateRoom(self,guild: discord.Guild, members: List[discord.Member]): #give players the Night role, remove day and roam roles and send them to their private room
        try: #Roles might not exist or calling members may fail
            dayRole = get(guild.roles, name=Role.day.value)
            nightRole = get(guild.roles, name=Role.night.value)
            roamRole = get(guild.roles, name=Role.roam.value)

            #Players need to be able to access their room to be sent to it
            await self.unlockPlayersPrivateRoom(guild,members)        
        
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
                privateRoom = self.gameState.getRoomOfPlayer(member) #player's private channel
                await member.move_to(privateRoom) #move them to their channel 
            except Exception as e:
                print(e)
    
    async def movePlayersToPrivateRoom(self,guild: discord.Guild, members: List[discord.Member]): #move players to their private room without changing roles
        #Players need to be able to access their room to be sent to it
        await self.unlockPlayersPrivateRoom(guild,members)    

        for member in members:
            try: #Try to move them from current vc to new vc, fails is user is in no vc
                privateRoom = self.gameState.getRoomOfPlayer(member) #player's private channel
                await member.move_to(privateRoom) #move them to their channel 
            except Exception as e:
                print(e)

    async def sendPlayersToTown(self,guild: discord.Guild, members: List[discord.Member]): #Give players the Day Role, remove night and roam roles and force them into town
        try: #Roles might not exist or calling members may fail
            dayRole = get(guild.roles, name=Role.day.value)
            nightRole = get(guild.roles, name=Role.night.value)
            roamRole = get(guild.roles, name=Role.roam.value)

            #Players should be blocked from their rooms
            await self.lockPlayersPrivateRoom(guild, members)        

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
    
        town = self.gameState.channels.townVoice
        for member in members:
            try: #Try to move them from current vc to new vc, fails is user is in no vc
                await member.move_to(town) #move them to their channel 
            except Exception as e:
                print(e)
            
    async def movePlayersToTown(self,guild: discord.Guild, members: List[discord.Member]): #Moves players to townsquare without chaing their perms
        town = self.gameState.channels.townVoice
        for member in members:
            try: #Try to move them from current vc to new vc, fails is user is in no vc
                await member.move_to(town) #move them to their channel 
            except Exception as e:
                print(e)    
            
    async def movePlayersToStorytellerPrivate(self,guild: discord.Guild, members: List[discord.Member]):#Moves players to storytellers corner
        corner = self.gameState.channels.storytellerVoice
        for member in members:
            try: #Try to move them from current vc to new vc, fails is user is in no vc
                await member.move_to(corner) #move them to their channel 
            except Exception as e:
                print(e)  

    async def allowPlayersRoam(self,guild: discord.Guild, members: List[discord.Member]): #Give players the Roam role, lets them visit public rooms
        try:
            roamRole = get(guild.roles, name=Role.roam.value)
            for member in members:
                print(f"user: {member} roles {member.roles}")
                if not (roamRole in member.roles):
                    await member.add_roles(roamRole)
        except Exception as e:
            raise e
    
    async def denyPlayersRoam(self,guild: discord.Guild, members: List[discord.Member]): #Remove player(s)'s Roam role if they have it, denying them from public rooms
        try:
            roamRole = get(guild.roles, name=Role.roam.value)
            for member in members:
                print(f"user: {member} roles {member.roles}")
                if roamRole in member.roles:
                    await member.remove_roles(roamRole)
        except Exception as e:
            raise e
    
    async def handlePlayerMovement(self,guild: discord.guild): #Handles player movement based on the phase of the game
        if self.gameState.dayPhase == 0: #Night movement, send to private room
            await self.sendPlayersToPrivateRoom(guild,self.gameState.getPlayersAsMembers(guild))
        elif self.gameState.dayPhase == 1: #Dawn movement, bring to town, announce night actions
            await self.sendPlayersToTown(guild,self.gameState.getPlayersAsMembers(guild))
        elif self.gameState.dayPhase == 2: #Midday movement, allow players to privately talk
            await self.movePlayersToTown(guild,self.gameState.getPlayersAsMembers(guild))
            await self.allowPlayersRoam(guild,self.gameState.getPlayersAsMembers(guild))
        elif self.gameState.dayPhase == 3: #Dusk movement, deny players private talk, bring to town for nominations
            await self.movePlayersToTown(guild,self.gameState.getPlayersAsMembers(guild))
            await self.denyPlayersRoam(guild,self.gameState.getPlayersAsMembers(guild))
        else: #Error state, should not be called
            raise Exception(f"dayPhase: {self.gameState.dayPhase} not in range o to 3")
    
    async def declareGamePhase(self): #Bot states the phase of the game into chat
        await self.gameState.channels.getTownText().send(self.gameState.getGameTimeMsg())

    @app_commands.command(
        name="start_game",
        description="Starts a BoTC game: setup players, storyteller and channel first"
    )
    @app_commands.guild_only()
    @app_commands.checks.has_role('ctb-StoryTeller')
    async def startGame(self,interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        await self.commandLock.acquire()
        try:
            if self.gameState.active:
                await interaction.edit_original_response(content=f"A game is already running, end it before starting a new one")
                return
            if not self.gameState.channelReady:
                await interaction.edit_original_response(content=f"Channels have not been setup yet, run /setup_chanels to create and set them to the bot")
                return 

            await self.setRoles(interaction.guild,self.gameState.getPlayersAsMembers(interaction.guild),[get(interaction.guild.roles, name=Role.alive.value),get(interaction.guild.roles, name=Role.player.value),get(interaction.guild.roles, name=Role.night.value)]) #Remove any excess flag roles that users might have for some reason
    
            await self.movePlayersToPrivateRoom(interaction.guild,self.gameState.getPlayersAsMembers(interaction.guild)) #move all players to their private room
            self.gameState.active = True    

            await interaction.edit_original_response(content=f"The game is set, all players have been sent to their rooms for the first night")
    
            await self.declareGamePhase() # Declare the time, the first night
        except Exception as e:
            print(e)
        finally:
            self.commandLock.release()
    
    
    @app_commands.command(
        name="end_game",
        description="Ends the active game, with an optional reason"
    )
    @app_commands.choices(reason=[ 
        app_commands.Choice(name="Good wins", value="The good team wins!"),
        app_commands.Choice(name="Evil wins", value="The evil team wins!"),
        app_commands.Choice(name="Draw", value="The game is over, it is a draw!"),
        app_commands.Choice(name="None", value="The game is over!"),
    ])
    @app_commands.describe(reason="The reason the game is over (optional)")
    @app_commands.guild_only()
    @app_commands.checks.has_role('ctb-StoryTeller')
    async def endGame(self,interaction: discord.Interaction, reason: app_commands.Choice[str] = None): #Ends an active game, with a given reason
        await interaction.response.defer(thinking=True,ephemeral=True)
        await self.commandLock.acquire()
        if not self.gameState.active:
            await interaction.edit_original_response(content=f"There is no active game to end")
            return    

        self.gameState.endGame()

        if reason == None:
            await self.gameState.channels.getTownText().send(f"The game is over!")
        else:
            await self.gameState.channels.getTownText().send(reason.value)

        await interaction.edit_original_response(content=f"The game has been ended!")
        self.commandLock.release()

    @app_commands.command(
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
    @app_commands.describe(day="The day number to skip the game to (optional)")
    @app_commands.guild_only()
    @app_commands.checks.has_role('ctb-StoryTeller')
    async def nextGamePhase(self,interaction: discord.Interaction, time: app_commands.Choice[int] = None, day: int = None):
        await interaction.response.defer(thinking=True,ephemeral=True)
        await self.commandLock.acquire()

        if not self.gameState.active: # Cant advance an inactive game
            await interaction.edit_original_response(content=f"Requires a game to be running")
            return
    
        if (day != None) and (day < 0): # Cant pass negative value
            await interaction.edit_original_response(content=f"Cannot set day number to: {day}")
            return
    
        if time == None: #If no argument passed
            if not (day == None):
                self.gameState.gameDay = day
            self.gameState.incrementDayPhase()
        else:
            if day == None: #if a day was not given
                self.gameState.advanceDayPhase(time.value)
            else:
                self.gameState.setTime(day,time.value)
        
        await self.handlePlayerMovement(interaction.guild)

        await self.declareGamePhase()

        await interaction.edit_original_response(content=f"Advanced to day: {self.gameState.gameDay}, phase: {self.gameState.dayPhase} and attempted to move players to the correct channel")
        self.commandLock.release()    

    @app_commands.command(
        name="retry_player_movement",
        description="Attempts to move all players according to the day phase"
    )
    @app_commands.guild_only()
    @app_commands.checks.has_role('ctb-StoryTeller')
    async def retryPlayerMovement(self,interaction: discord.Interaction):
        await interaction.response.defer(thinking=True,ephemeral=True)
        await self.commandLock.acquire()
        if not self.gameState.active:
            await interaction.edit_original_response(content=f"Requires a game to be running")
            return
    
        await self.handlePlayerMovement(interaction.guild) 

        await interaction.edit_original_response(content=f"Attempted to move players to the appropriate channel")
        self.commandLock.release()
  
    async def killPlayerWithReason(self,interaction: discord.Interaction, member: discord.Member, reason: str = None): #Kill and announce a player is dead with a given reason   
        await self.killPlayers(interaction.guild,[member]) # Mark their roles as dead

        if reason == None:
            await self.gameState.channels.getTownText().send(f"{member} is dead!")
        else:
            await self.gameState.channels.getTownText().send(f"{member} {reason}")
        
    @app_commands.command(
        name="storyteller_private",
        description="Moves a player to the story telllers private voice channel from the current voice channel"
    )
    @app_commands.describe(member="The member to move")
    @app_commands.guild_only()
    @app_commands.checks.has_role('ctb-StoryTeller')
    async def movePlayerToStortellerChannel(self,interaction: discord.Interaction, member: discord.Member): #Moves select player to the storyteller's channel
        await interaction.response.defer(thinking=True,ephemeral=True)
        await self.commandLock.acquire()
        try:
            if not self.gameState.active:
                await interaction.edit_original_response(content=f"Requires a game to be running")
                return
        
            if member.voice != None:
                await self.movePlayersToStorytellerPrivate(interaction.guild,[member])
                await interaction.edit_original_response(content=f"Moved {member.name} to {self.gameState.channels.storytellerVoice.name}")
            else:
                await interaction.edit_original_response(content=f"Can't move {member.name}, they need to be connected to a voice channel first, its a discord limitation") 
        except Exception as e:
            print(e)
        finally:
            self.commandLock.release()    

    @app_commands.command(
        name="kill_player",
        description="Announces and marks that a player is dead, with an optional reason"
    )
    @app_commands.choices(reason=[ 
        app_commands.Choice(name="None", value="is dead!"),
        app_commands.Choice(name="Died last night", value="died last night!"),
        app_commands.Choice(name="Execution", value="was executed!"),
        app_commands.Choice(name="Unknown", value="somehow died for no known reason!"),
    ])
    @app_commands.describe(member="The member to kill")
    @app_commands.describe(reason="The given announced reason (optional)")
    @app_commands.guild_only()
    @app_commands.checks.has_role('ctb-StoryTeller')
    async def killPlayer(self,interaction: discord.Interaction, member: discord.Member, reason: app_commands.Choice[str] = None): #Marks that a player is dead and announces the death to all players
        await interaction.response.defer(thinking=True,ephemeral=True)
        await self.commandLock.acquire()
        #note, in the rules of BonCT, it is possible for an already dead player to be killed again, see: vigormortis role    
    
        if not self.gameState.active:
            await interaction.edit_original_response(content=f"Requires a game to be running")
            return
    
        if not (member in self.gameState.getPlayersAsMembers(interaction.guild)):
            await interaction.edit_original_response(content=f"{member} is not listed as a player")
            return
    
        if reason == None:
            string = None
        else:
            string = reason.value
        await self.killPlayerWithReason(interaction,member,string)
        await interaction.edit_original_response(content=f"Killed player: {member}")
        self.commandLock.release()
    
    @app_commands.command(
        name="ressurect_player",
        description="Announce and marks that a player is alive, used for certain player abilities"
    )
    @app_commands.describe(member="The member to ressurect")
    @app_commands.guild_only()
    @app_commands.checks.has_role('ctb-StoryTeller')
    async def alivePlayer(self,interaction: discord.Interaction,member: discord.Member): #Marks a player as alive and announced it to all players
        await interaction.response.defer(thinking=True,ephemeral=True)
        await self.commandLock.acquire()

        if not self.gameState.active:
            await interaction.edit_original_response(content=f"Requires a game to be running")
            return
    
        if not (member in self.gameState.getPlayersAsMembers(interaction.guild)):
            await interaction.edit_original_response(content=f"{member} is not listed as a player")
            return

        await self.alivePlayers(interaction.guild,[member])

        await self.gameState.channels.getTownText().send(f"{member} is alive!")
        self.commandLock.release()
    
    @app_commands.command(
        name="open_door",
        description="Lets other users join the public room you are in, until it closes automatically again"
    )
    @app_commands.guild_only()
    @app_commands.checks.has_any_role('ctb-Player','ctb-StoryTeller')
    async def openPublicRoomCommand(self,interaction: discord.Interaction): #Allows a member in the game to open a locked public room they are in
        await interaction.response.defer(thinking=True,ephemeral=True)
        await self.commandLock.acquire()
        try:
            if not self.gameState.active:
                await interaction.edit_original_response(content=f"Requires a game to be running")
                return
            if not (interaction.user in self.gameState.getAllUsers(interaction.guild)): #If user is not in the game
                await interaction.edit_original_response(content=f"You are not a member of the currently running game")
                return 
        
            channel = interaction.user.voice.channel        

            if not (channel in self.gameState.channels.publicRooms): #If the channel the user is in is not a public room
                await interaction.edit_original_response(content=f"You must be in a public room voice channel to use this command")
                return 
        
            if not self.gameState.channelLocks.isRoomLocked(channel): #If the public room the user is in is not locked
                await interaction.edit_original_response(content=f"This room is already open")
                return 
        
            #Open room now
            await self.voiceStateLock.acquire()
            self.gameState.channelLocks.unlockRoom(channel)
            roamRole = get(channel.guild.roles, name=Role.roam.value)
            await channel.set_permissions(roamRole,read_messages=True,connect=True)
            self.voiceStateLock.release()
        
            await interaction.edit_original_response(content=f"Opened channel: {channel.name}")
            self.commandLock.release() #Release command lock before waiting on the scheduled task
        
            #Create a task to close it again in the future, lock in openCooldown seconds (Usually longer than the default)
            task = asyncio.create_task(self.lockChannelInSeconds(channel,self.voiceStateLock,self.gameState.openCooldown))
            await self.commandLock.acquire()
        except Exception as e:
            print(e)
        finally:
            self.commandLock.release()
        
    @app_commands.command(
        name="lock_door",
        description="Prevents players from joining the public room you are in"
    )
    @app_commands.guild_only()
    @app_commands.checks.has_any_role('ctb-Player','ctb-StoryTeller')
    async def lockPublicRoomCommand(self,interaction: discord.Interaction): #Allows a member in the game to lock an open public room they are in
        await interaction.response.defer(thinking=True,ephemeral=True)
        await self.commandLock.acquire()
        try:
            if not self.gameState.active:
                await interaction.edit_original_response(content=f"Requires a game to be running")
                return
            if not (interaction.user in self.gameState.getAllUsers(interaction.guild)): #If user is not in the game
                await interaction.edit_original_response(content=f"You are not a member of the currently running game")
                return 
        
            channel = interaction.user.voice.channel        

            if not (channel in self.gameState.channels.publicRooms): #If the channel the user is in is not a public room
                await interaction.edit_original_response(content=f"You must be in a public room voice channel to use this command")
                return 
        
            if self.gameState.channelLocks.isRoomLocked(channel): #If the public room the user is in is locked
                await interaction.edit_original_response(content=f"This room is already locked")
                return 
        
            #lock room now
            await self.voiceStateLock.acquire()
            self.gameState.channelLocks.lockRoom(channel)
            roamRole = get(channel.guild.roles, name=Role.roam.value)
            await channel.set_permissions(roamRole,read_messages=True,connect=False)
            self.voiceStateLock.release()
        
            await interaction.edit_original_response(content=f"Locked channel: {channel.name}")
        except Exception as e:
            print(e)
        finally:
            self.commandLock.release()

    class VoteView(discord.ui.View):
        @discord.ui.button(label="Start Vote", style=discord.ButtonStyle.primary)
        async def button_callback(self, interaction, button):
            await interaction.response.send_message(content="whae",embed=None,view=None)

    @app_commands.command(
        name="run_vote",
        description="Used by the storyteller to have players vote on an outcome, usually for an execution"
    )
    @app_commands.choices(type=[ 
        app_commands.Choice(name=VotingType.circleTally.name, value=VotingType.circleTally.value),
        app_commands.Choice(name=VotingType.countdownTally.name, value=VotingType.countdownTally.value),
        app_commands.Choice(name=VotingType.blindCountdownTally.name, value=VotingType.blindCountdownTally.value),
        app_commands.Choice(name=VotingType.pointCountdown.name, value=VotingType.pointCountdown.value),
    ])
    @app_commands.describe(nominator="The member to who nominated another player")
    @app_commands.describe(nominee="The member who was nominated")
    @app_commands.describe(type="The type of vote to use")
    @app_commands.guild_only()
    @app_commands.checks.has_role('ctb-StoryTeller')
    async def runVote(self,interaction: discord.Interaction, nominator: discord.Member = None, nominee: discord.Member = None, type: int = 0):
        #await interaction.response.defer(thinking=True,ephemeral=False)
        await self.commandLock.acquire()

        try:
            nominatorStr = "Unknown"
            nomineeStr = "Unknown"

            if nominator != None:
                nominatorStr = nominator.name

            if nominee != None:
                nomineeStr = nominee.name

            await interaction.response.send_message(content=f"{nominatorStr} has nominated {nomineeStr}",view=GameCommands.VoteView())
        except Exception as e:
            print(e)
        finally:
            self.commandLock.release()
    
    @app_commands.command(
        name="character",
        description="Prints information and rules on a given character role"
    )
    @app_commands.choices(character=characterData.choices)
    @app_commands.guild_only()
    async def declareCharacter(self,interaction: discord.Interaction, character: app_commands.Choice[str]): #Prints in chat the summary of a character role
        await interaction.response.defer(thinking=True)
        try:
            embed = self.characterData.getEmbedOfCharacter(character.value)
            if embed != None:
                await interaction.edit_original_response(embed=embed)
            else:
                await interaction.edit_original_response(content="Could not find character")
        except Exception as e:
            print(e)
        
    @app_commands.command(
        name="you_are_the",
        description="Used by the storyteller to tell players their character"
    )
    @app_commands.choices(character=characterData.choices)
    @app_commands.guild_only()
    @app_commands.checks.has_role('ctb-StoryTeller')
    async def youAreTheCharacter(self,interaction: discord.Interaction, character: app_commands.Choice[str]): #Just like /character except it declares what character a plaer is
        await interaction.response.defer(thinking=True)
        try:
            embed = self.characterData.getEmbedOfCharacter(character.value)
            if embed != None:
                embed.title = "You are the:"
                await interaction.edit_original_response(embed=embed)
            else:
                await interaction.edit_original_response(content="Could not find character")
        except Exception as e:
            print(e)

    
    async def lockChannelInSeconds(self,channel: discord.VoiceChannel,locker: asyncio.Lock, secs: int = 5, ): #Prevents players from joining a channel in time seconds from now
        print(f"Locking channel: {channel.name} in {secs} seconds")
        await asyncio.sleep(secs) #Wait seconds, this is okay because nothing waits on this task
        #This command doesnt wait the exact amount of seconds, since there may be a delay to accquire rights to change channel permissions
        await locker.acquire()
        try:
            #Channel might have changed in the time we waited, get updated version
            recentChannel = bot.get_channel(channel.id)
            if (len(self.gameState.filterPlayers(recentChannel.members)) != 0): #The room is not empty, lock it
                roamRole = get(recentChannel.guild.roles, name=Role.roam.value)
                await recentChannel.set_permissions(roamRole,read_messages=True,connect=False) #Prevent roaming players from connecting
                self.gameState.channelLocks.lockRoom(recentChannel)
                print(f"Locked channel: {recentChannel.name}")
            else:
                print(f"Cancelled locking of channel: {channel.name}")
        except:
            print(f"locking is being cancelled")
            raise
        finally:
            locker.release()

    async def handleMemberJoinPublic(self,member: discord.Member, channel: discord.VoiceChannel): #Handle member joining a public room
        await self.voiceStateLock.acquire()
        if not self.gameState.channelLocks.isRoomLocked(channel): #if the room is open
            self.gameState.channelLocks.addMembersToRoom(channel,[member])
            if (len(self.gameState.filterPlayers(channel.members)) == 1): #If there is only one member in the chat
                self.voiceStateLock.release()
            
                #Create an asynciio task to lock down this channel in a set amount of time
                task = asyncio.create_task(self.lockChannelInSeconds(channel,self.voiceStateLock,self.gameState.lockCooldown))
                await self.voiceStateLock.acquire()
        self.voiceStateLock.release()
    
    async def handleMemberLeavePublic(self,member: discord.Member, channel: discord.VoiceChannel): # Handle member leaving a public room
        await self.voiceStateLock.acquire()
        if self.gameState.channelLocks.isRoomLocked(channel): # if room is locked
            print(f"{channel.members}")
            if (len(self.gameState.filterPlayers(channel.members)) == 0): #The room is now empty
                self.gameState.channelLocks.unlockRoom(channel)
                roamRole = get(channel.guild.roles, name=Role.roam.value)
                await channel.set_permissions(roamRole,read_messages=True,connect=True)
        self.gameState.channelLocks.removeMembersToRoom(channel,[member])
        self.voiceStateLock.release()

    """
    Called whenver a member changes their voice state:
        - When a member joins a voice channel
        - When a member leaves a voice channel
        - When a member is muted or deafened on their own accord
        - When a member is muted or deafened by an admin (such as this bot)
    """
    @commands.Cog.listener()
    async def on_voice_state_update(self,member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        print(f"Member: {member.name} moved from voicestate {before.channel} to {after.channel}")

        if GameState.isMemberPlayer(member): # Only control players
            if before.channel == after.channel: #If users did not change channels or did not move to/from a channel
                print(f"Player: {member.name} did not move to or from a channel")
                return #We only care about moving to or from channels. not changes inside of channels

            #handle previous channel
            if before.channel in self.gameState.channels.publicRooms: #we only care about controlling public rooms in the bot
                print(f"Player: {member.name} left public room: {before.channel}")
                await self.handleMemberLeavePublic(member,before.channel)
                print("Done before")
    
            #handle new channel
            if after.channel in self.gameState.channels.publicRooms: #we only care about controlling public rooms in the bot
                print(f"Player: {member.name} entered public room: {after.channel}")
                await self.handleMemberJoinPublic(member,after.channel)
                print("Done after")
    
    #Handle MissingPermissions exceptions raise from commands that require a permission/role
    #TODO this just FEELS wrong to write out all the decorators like this. but I cant find a better soloution
    @setupRoles.error
    @setStoryTeller.error
    @addPlayer.error
    @removePlayer.error
    @syncRoles.error
    @setupChannels.error
    @startGame.error
    @endGame.error
    @nextGamePhase.error
    @retryPlayerMovement.error
    @killPlayer.error
    @alivePlayer.error
    @openPublicRoomCommand.error
    @lockPublicRoomCommand.error
    @youAreTheCharacter.error
    @runVote.error
    async def missingPermisionError(self,interaction: discord.Interaction,error: app_commands.AppCommandError):
        if isinstance(error, app_commands.checks.MissingPermissions):
            await interaction.response.send_message(content="You don't have permission to use this command.",ephemeral=True)
        
        elif isinstance(error, app_commands.MissingRole):
            await interaction.response.send_message(content="You don't have permission to use this command.",ephemeral=True)
        
        elif isinstance(error, commands.MissingRole):
            await interaction.response.send_message(content="You don't have permission to use this command.",ephemeral=True)
        
        elif isinstance(error, commands.MissingPermissions):
            await interaction.response.send_message(content="You don't have permission to use this command.",ephemeral=True)
        else:
            raise error

#Give commands to the bot
asyncio.run(bot.add_cog(GameCommands(bot)))
#Run the bot
bot.run(TOKEN,log_handler=handler,log_level=logging.DEBUG)