import os
import discord.ext.test as dpytest
import discord
import asyncio
from discord.ext import commands
import pytest
import sys 
import pytest_asyncio

sys.path.append('../ClocktowerBot')

from ClocktowerBot import GameCommands

pytest_plugins = ('pytest_asyncio',)

@pytest_asyncio.fixture
async def bot():
    # Setup
    #Bot
    intents = discord.Intents.all()
    bot = commands.Bot(intents=intents,command_prefix="!")

    await bot._async_setup_hook()  # setup the loop
    await bot.add_cog(GameCommands(bot))

    dpytest.configure(bot)

    yield bot

    # Teardown
    await dpytest.empty_queue() # empty the global message queue as test teardown
    
@pytest.mark.asyncio
async def test_ping(bot):
    msg = await dpytest.message("/ping")
    print(msg.content)
    print (dpytest.get_message(True) )
    assert dpytest.verify().message().content("Pong!")