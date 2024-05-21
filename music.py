import discord
from discord.ext import commands
import os
import asyncio
#library for discord youtube
import yt_dlp

from dotenv import load_dotenv
import urllib.parse, urllib.request, re
from datetime import timedelta

def run_bot():
    load_dotenv()
    TOKEN = os.getenv('DISCORD_TOKEN')
    intents = discord.Intents.default()
    intents.message_content = True
    client = commands.Bot(command_prefix="v!", intents=intents)

    queues = {}
    voice_clients = {}
    repeat_flags = {}  # To keep track of repeat state for each guild
    yt_dl_options = {"format": "bestaudio/best"}
    ytdl = yt_dlp.YoutubeDL(yt_dl_options)

    ffmpeg_options = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5','options': '-vn -filter:a "volume=0.25"'}

    @client.event
    async def on_ready():
        print(f'{client.user} is now jamming')

    # Function to check if the bot is in a voice channel
    def is_bot_in_voice(ctx):
        return ctx.voice_client is not None

    async def play_next(ctx):
        if ctx.guild.id in repeat_flags and repeat_flags[ctx.guild.id].get('repeat', False):
            # Re-add the current song to the queue
            link = repeat_flags[ctx.guild.id].get('link')
            await play(ctx, link=link, skip=True)
        elif queues.get(ctx.guild.id):
            link, _, _ = queues[ctx.guild.id].pop(0)
            await play(ctx, link=link, skip=True)
        else:
            embed = discord.Embed(description="There are no more tracks", color=discord.Color.red())
            await ctx.send(embed=embed)

    @client.command(name="play", aliases=["p"], help="Play a song or add to queue")
    async def play(ctx, *, link: str = 'None', skip: bool = False):
        if ctx.author.voice is None:
            embed = discord.Embed(description="You must be in a voice channel to use this command.", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        if not is_bot_in_voice(ctx):
            try:
                voice_client = await ctx.author.voice.channel.connect()
                voice_clients[voice_client.guild.id] = voice_client
            except Exception as e:
                print(e)
        
        if not is_bot_in_voice(ctx):
            embed = discord.Embed(description="You are not in a voice channel", color=discord.Color.red())
            await ctx.send(embed=embed)
            return

         # Add to queue if the bot is already playing and not skipping
        if not skip and voice_clients[ctx.guild.id].is_playing():
            if ctx.guild.id not in queues:
                queues[ctx.guild.id] = []
            duration, title = await get_duration_and_title(link)
            queues[ctx.guild.id].append((link, duration, title))
            await send_queue_info(ctx, title, link, duration)
            return

        try:
            # Check if the link is a YouTube video or playlist
            if "www.youtube.com" not in link and "youtu.be" not in link:
                link = f"ytsearch:{link}"
            
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(link, download=False))
            
            if 'entries' in data:  # If the link is a search result or playlist
                data = data['entries'][0]

            link = data['webpage_url']
            titlem = data['title']
            duration = data.get('duration', 0)
            requestm = ctx.author.name

            # Send embedded message with song details
            embed = discord.Embed(
                title=f"🎶 Now Playing 1/{len(queues.get(ctx.guild.id, [])) + 1}",
                description=f"[{titlem}]({link})\nRequested by: **{requestm}**\n\nEnjoy the music!",
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"Duration: {str(timedelta(seconds=duration))}")
            embed.set_thumbnail(url=data['thumbnail'])
            await ctx.send(embed=embed)

            song = data['url']
            player = discord.FFmpegOpusAudio(song, **ffmpeg_options)

            def after_playing(error):
                coro = play_next(ctx)
                future = asyncio.run_coroutine_threadsafe(coro, client.loop)
                try:
                    future.result()
                except Exception as e:
                    print(f'Error in after_playing: {e}')

            voice_clients[ctx.guild.id].play(player, after=after_playing)

            # Save the song link if repeat mode is on
            if ctx.guild.id in repeat_flags and repeat_flags[ctx.guild.id].get('repeat', False):
                repeat_flags[ctx.guild.id]['link'] = link

        except Exception as e:
            print(e)

    async def send_queue_info(ctx, title, link, duration):
        if ctx.guild.id in queues:
            queue_length = len(queues[ctx.guild.id]) + 1
            estimated_time = sum(d for _, d, _ in queues[ctx.guild.id])  # Total duration of queued songs
            requestm = ctx.author.name
            embed = discord.Embed(
                title=f"Added to Queue - {queue_length}",
                description=f"[{title}]({link})",
                color=discord.Color.blue()
            )
            #Footer embed
            embed.set_footer(text=f"Requested by: {requestm}")
            #Field embed
            embed.add_field(name="Estimated time until play", value=f"{str(timedelta(seconds=estimated_time))}", inline=True)
            embed.add_field(name="Song Duration", value=f"{str(timedelta(seconds=duration))}", inline=True)
            await ctx.send(embed=embed)
        else:
            await ctx.send("Queue is empty!")

    async def get_duration_and_title(link):
        if "www.youtube.com" not in link and "youtu.be" not in link:
            link = f"ytsearch:{link}"
        
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(link, download=False))
        
        if 'entries' in data:  # If the link is a search result or playlist
            data = data['entries'][0]

        return data.get('duration', 0), data.get('title', 'Unknown')

    @client.command(name="clear_queue", aliases=["cq"], help="")
    async def clear_queue(ctx):
        if ctx.author.voice is None:
            embed = discord.Embed(description="You must be in a voice channel to use this command.", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        if is_bot_in_voice(ctx):
            if ctx.guild.id in queues:
                queues[ctx.guild.id].clear()
                await ctx.send("Queue cleared!")
            else:
                await ctx.send("There is no queue to clear")
        else:
            embed = discord.Embed(description="You are not in a voice channel",color=discord.Color.brand_red())
            await ctx.send(embed=embed)
            return False

    @client.command(name="skip", aliases=["s"], help="Skip the current song")
    async def skip(ctx):
        if ctx.author.voice is None:
            embed = discord.Embed(description="You must be in a voice channel to use this command.", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        if is_bot_in_voice(ctx):
            try:
                embed = discord.Embed(description="Skipped current track!", color=discord.Color.green())
                await ctx.send(embed=embed)
                voice_clients[ctx.guild.id].stop()
            except Exception as e:
                print(e)
        else:
            embed = discord.Embed(description="You are not in a voice channel", color=discord.Color.brand_red())
            await ctx.send(embed=embed)
            return False

    @client.command(name="pause", aliases=["ps"], help="Pause the current song")
    async def pause(ctx):
        if ctx.author.voice is None:
            embed = discord.Embed(description="You must be in a voice channel to use this command.", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        if is_bot_in_voice(ctx):
            try:
                voice_clients[ctx.guild.id].pause()
                await ctx.send("Paused!")
            except Exception as e:
                print(e)
        else:
            embed = discord.Embed(description="You are not in a voice channel",color=discord.Color.brand_red())
            await ctx.send(embed=embed)
            return False

    @client.command(name="resume", aliases=["r"], help="Pause the current song")
    async def resume(ctx):
        if ctx.author.voice is None:
            embed = discord.Embed(description="You must be in a voice channel to use this command.", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        if is_bot_in_voice(ctx):
            try:
                voice_clients[ctx.guild.id].resume()
            except Exception as e:
                print(e)
        else:
            embed = discord.Embed(description="You are not in a voice channel",color=discord.Color.brand_red())
            await ctx.send(embed=embed)
            return False

    @client.command(name="stop", help="Stop the bot and clear the queue")
    async def stop(ctx):
        if ctx.author.voice is None:
            embed = discord.Embed(description="You must be in a voice channel to use this command.", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        if is_bot_in_voice(ctx):
            try:
                voice_clients[ctx.guild.id].stop()
                await voice_clients[ctx.guild.id].disconnect()
                del voice_clients[ctx.guild.id]
                if ctx.guild.id in queues:
                    del queues[ctx.guild.id]
                if ctx.guild.id in repeat_flags:
                    del repeat_flags[ctx.guild.id]
            except Exception as e:
                print(e)
        else:
            embed = discord.Embed(description="You are not in a voice channel", color=discord.Color.brand_red())
            await ctx.send(embed=embed)
            return False

    @client.command(name="repeat", aliases=["rp"], help="Toggle repeat mode for the current song")
    async def repeat(ctx):
        if ctx.author.voice is None:
            embed = discord.Embed(description="You must be in a voice channel to use this command.", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        if is_bot_in_voice(ctx):
            if ctx.guild.id not in repeat_flags:
                repeat_flags[ctx.guild.id] = {'repeat': False, 'link': None}
            repeat_flags[ctx.guild.id]['repeat'] = not repeat_flags[ctx.guild.id]['repeat']
            status = "enabled" if repeat_flags[ctx.guild.id]['repeat'] else "disabled"
            await ctx.send(f"Repeat mode {status}!")
        else:
            embed = discord.Embed(description="You are not in a voice channel", color=discord.Color.brand_red())
            await ctx.send(embed=embed)
            return False

    client.run(TOKEN)
