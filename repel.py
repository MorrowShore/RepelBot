"""
RepelBot - Discord Moderation Bot
Created by Morrow Shore
https://morrowshore.com
License: AGPLv3
"""

import discord
from discord import app_commands
from discord.ext import commands
import asyncio
from typing import Optional, Dict, List, Tuple
import datetime
import os
from collections import defaultdict, deque
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class RepelBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix='!', intents=intents)
        
        # Efficient message cache using deque for automatic size limiting
        self.message_cache: Dict[int, deque] = {}
        self.max_cache_size = 500
        self.server_id = os.getenv('DISCORD_SERVER_ID')
        
        # Auto-repel tracking: {user_id: {guild_id: [(channel_id, timestamp)]}}
        self.user_activity = defaultdict(lambda: defaultdict(list))
        
        # Log channels: {guild_id: channel_id}
        self.log_channels = {}
        default_log = os.getenv('DEFAULT_LOG_CHANNEL_ID')
        if default_log:
            # Will be properly set in on_ready when we have guild info
            self.default_log_channel_id = int(default_log)
        
    async def setup_hook(self):
        await self.tree.sync()
        
    async def on_ready(self):
        print(f'{self.user} has connected to Discord!')
        
    async def on_message(self, message: discord.Message):
        # Ignore bot messages
        if message.author.bot:
            return
            
        # Cache message efficiently
        if message.channel.id not in self.message_cache:
            self.message_cache[message.channel.id] = deque(maxlen=self.max_cache_size)
            
        self.message_cache[message.channel.id].append({
            'id': message.id,
            'author_id': message.author.id,
            'timestamp': message.created_at
        })
        
        # Auto-repel tracking
        user_id = message.author.id
        guild_id = message.guild.id
        channel_id = message.channel.id
        timestamp = message.created_at
        
        # Track user activity
        self.user_activity[user_id][guild_id].append((channel_id, timestamp))
        
        # Clean old entries (older than 30 seconds)
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=30)
        self.user_activity[user_id][guild_id] = [
            (ch_id, ts) for ch_id, ts in self.user_activity[user_id][guild_id] 
            if ts > cutoff
        ]
        
        # Check for auto-repel condition: messages in >3 channels within 30 seconds
        unique_channels = len(set(ch_id for ch_id, _ in self.user_activity[user_id][guild_id]))
        if unique_channels >= 3:
            # Auto-repel the user (timeout + message deletion)
            try:
                # Timeout the user
                timeout_duration = datetime.timedelta(minutes=120)
                await message.author.timeout(timeout_duration, reason="Auto-repel: spam across multiple channels")
                
                # Delete user's recent messages (same as repel command with 50 messages)
                messages_to_delete = await self.get_user_messages(message.guild, message.author, 50)
                deleted_count = await self.delete_messages_efficiently(messages_to_delete)
                
                # Clear activity to prevent repeated timeouts
                self.user_activity[user_id][guild_id].clear()
                
                # Log the action
                if message.channel:
                    await message.channel.send(
                        f"⏰ Auto-repelled {message.author.mention} for spamming across {unique_channels} channels\n"
                        f"🗑️ Deleted {deleted_count} messages"
                    )
            except discord.Forbidden:
                pass  # Bot doesn't have permission to timeout or delete messages
        
        await self.process_commands(message)

    async def get_user_messages(self, guild: discord.Guild, user: discord.Member, 
                               limit: int) -> List[Tuple[discord.TextChannel, int]]:
        """Efficiently gather user messages from cache first, then API."""
        messages = []
        existing_ids = set()
        
        # First, check cache for recent messages
        for channel_id, cached_msgs in self.message_cache.items():
            channel = guild.get_channel(channel_id)
            if channel and channel.guild.id == guild.id:
                for msg_data in cached_msgs:
                    if msg_data['author_id'] == user.id:
                        messages.append((channel, msg_data['id']))
                        existing_ids.add(msg_data['id'])
                        if len(messages) >= limit:
                            return messages
        
        # If not enough messages in cache, search through channels more thoroughly
        if len(messages) < limit:
            remaining = limit - len(messages)
            
            # Search channels in parallel for faster collection
            async def search_channel(channel: discord.TextChannel):
                if not channel.permissions_for(guild.me).read_message_history:
                    return []
                    
                found = []
                try:
                    # Search enough messages to potentially find the remaining count
                    search_limit = max(remaining * 5, 100)  # Search more aggressively for fewer messages
                    async for message in channel.history(limit=search_limit):
                        if message.author.id == user.id and message.id not in existing_ids:
                            found.append((channel, message.id))
                            existing_ids.add(message.id)
                            if len(found) >= remaining:
                                break
                except discord.Forbidden:
                    pass
                return found
            
            # Process channels with rate limiting - process in batches of 5
            all_channels = list(guild.text_channels)
            for i in range(0, len(all_channels), 5):
                batch = all_channels[i:i+5]
                tasks = [search_channel(channel) for channel in batch]
                results = await asyncio.gather(*tasks)
                
                # Collect results
                for channel_messages in results:
                    messages.extend(channel_messages)
                    if len(messages) >= limit:
                        break
                if len(messages) >= limit:
                    break
                
                # Small delay between batches to avoid rate limits
                if i + 5 < len(all_channels):
                    await asyncio.sleep(0.1)
                    
        return messages[:limit]

    async def delete_channel_messages(self, channel: discord.TextChannel, 
                                     msg_ids: List[int]) -> int:
        """Delete messages from a single channel efficiently."""
        deleted = 0
        
        # Fetch messages in batches to avoid rate limits
        valid_messages = []
        for i in range(0, len(msg_ids), 10):  # Fetch 10 messages at a time
            batch_ids = msg_ids[i:i+10]
            fetch_tasks = [channel.fetch_message(msg_id) for msg_id in batch_ids]
            fetched = await asyncio.gather(*fetch_tasks, return_exceptions=True)
            
            # Filter out exceptions
            valid_messages.extend([msg for msg in fetched if isinstance(msg, discord.Message)])
            
            # Small delay between batches
            if i + 10 < len(msg_ids):
                await asyncio.sleep(0.05)
        
        if not valid_messages:
            return 0
        
        # Separate by age
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=14)
        recent = [msg for msg in valid_messages if msg.created_at > cutoff]
        old = [msg for msg in valid_messages if msg.created_at <= cutoff]
        
        # Bulk delete recent messages in batches
        while len(recent) >= 2:
            batch = recent[:100]
            try:
                await channel.delete_messages(batch)
                deleted += len(batch)
                recent = recent[100:]
            except discord.HTTPException as e:
                if e.status == 429:  # Rate limited
                    await asyncio.sleep(e.retry_after if hasattr(e, 'retry_after') else 1)
                    try:
                        await channel.delete_messages(batch)
                        deleted += len(batch)
                        recent = recent[100:]
                    except:
                        # Fall back to individual deletion
                        old.extend(batch)
                else:
                    # Fall back to individual deletion
                    old.extend(batch)
                    recent = recent[100:]
        
        # Add remaining recent messages to old for individual deletion
        old.extend(recent)
        
        # Delete old/remaining messages individually (with minimal delay)
        if old:
            # Create tasks for individual deletions with controlled concurrency
            async def delete_single(msg):
                try:
                    await msg.delete()
                    return 1
                except:
                    return 0
            
            # Process in small batches to avoid rate limits
            for i in range(0, len(old), 5):
                batch = old[i:i+5]
                results = await asyncio.gather(*[delete_single(msg) for msg in batch])
                deleted += sum(results)
                if i + 5 < len(old):  # Small delay between batches
                    await asyncio.sleep(0.05)
        
        return deleted

    async def delete_messages_efficiently(self, messages: List[Tuple[discord.TextChannel, int]]) -> int:
        """Delete messages with maximum parallelization."""
        # Group by channel
        channel_groups = defaultdict(list)
        for channel, msg_id in messages:
            channel_groups[channel].append(msg_id)
        
        # Process all channels in parallel
        tasks = [
            self.delete_channel_messages(channel, msg_ids)
            for channel, msg_ids in channel_groups.items()
        ]
        
        results = await asyncio.gather(*tasks)
        return sum(results)

bot = RepelBot()

@bot.tree.command(name="repel", description="Timeout a user and remove their recent messages")
@app_commands.describe(
    user="The user to repel",
    messagecount="Number of messages to remove (default: 100)",
    timeoutminutes="Timeout duration in minutes (default: 120)"
)
async def repel(interaction: discord.Interaction, 
               user: discord.Member, 
               messagecount: Optional[int] = 100, 
               timeoutminutes: Optional[int] = 120):
    
    # Server restriction check
    if bot.server_id and bot.server_id != 'YOUR_SERVER_ID_HERE':
        if str(interaction.guild_id) != bot.server_id:
            await interaction.response.send_message(
                "This bot is restricted to a specific server.", 
                ephemeral=True
            )
            return
    
    # Permission checks
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message(
            "You don't have permission to use this command!", 
            ephemeral=True
        )
        return
        
    if not interaction.guild.me.guild_permissions.manage_messages:
        await interaction.response.send_message(
            "I need 'Manage Messages' permission!", 
            ephemeral=True
        )
        return
        
    if not interaction.guild.me.guild_permissions.moderate_members:
        await interaction.response.send_message(
            "I need 'Moderate Members' permission!", 
            ephemeral=True
        )
        return
    
    # Defer response for processing
    await interaction.response.defer(thinking=True)
    
    # Execute timeout and message deletion in parallel
    async def timeout_user():
        try:
            timeout_duration = datetime.timedelta(minutes=timeoutminutes)
            await user.timeout(timeout_duration, reason=f"Repelled by {interaction.user}")
            return True
        except (discord.Forbidden, discord.HTTPException):
            return False
    
    async def delete_user_messages():
        messages_to_delete = await bot.get_user_messages(interaction.guild, user, messagecount)
        return await bot.delete_messages_efficiently(messages_to_delete)
    
    # Run both operations in parallel
    timeout_task = asyncio.create_task(timeout_user())
    delete_task = asyncio.create_task(delete_user_messages())
    
    timeout_success, deleted_count = await asyncio.gather(timeout_task, delete_task)
    
    # Build response
    response = []
    if timeout_success:
        response.append(f"⏰ Timed out {user.mention} for {timeoutminutes} minutes")
    else:
        response.append(f"⚠️ Could not timeout {user.mention} (insufficient permissions)")
    
    response.append(f"🗑️ Deleted {deleted_count} messages")
    
    # Send response
    try:
        await interaction.followup.send("\n".join(response))
    except discord.NotFound:
        # Fallback if interaction expired
        if interaction.channel:
            await interaction.channel.send("\n".join(response))

# Run bot
if __name__ == "__main__":
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        print("Error: DISCORD_BOT_TOKEN not found in environment variables")
    else:
        bot.run(token)