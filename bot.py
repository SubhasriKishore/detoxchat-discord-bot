import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import json
import logging
import time
import sys
import asyncio
import subprocess
import signal
from gradio_client import Client

def kill_existing_bots():
    """Kill any existing instances of the bot"""
    try:
        # Get the current process ID to avoid killing ourselves
        current_pid = os.getpid()
        
        # Use ps command to find all python processes running bot.py
        ps = subprocess.Popen(['ps', 'aux'], stdout=subprocess.PIPE)
        output = subprocess.check_output(['grep', 'python bot.py'], stdin=ps.stdout)
        ps.wait()
        
        # Parse the output to get PIDs and kill other instances
        for line in output.decode().split('\n'):
            if line.strip():
                try:
                    pid = int(line.split()[1])
                    if pid != current_pid:
                        print(f"Killing existing bot instance with PID: {pid}")
                        os.kill(pid, signal.SIGTERM)
                except (IndexError, ValueError) as e:
                    continue
                except ProcessLookupError:
                    continue
    except subprocess.CalledProcessError:
        print("No existing bot instances found")
    except Exception as e:
        print(f"Error while killing existing bots: {e}")

# Kill existing instances before starting new one
print("\n=== Checking for existing bot instances ===")
kill_existing_bots()
print("=== Starting new bot instance ===\n")

# Set up logging configuration
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Create and configure logger
logger = logging.getLogger('discord_bot')
logger.setLevel(logging.INFO)
logger.propagate = False  # Prevent duplicate logs

# Create a filter to remove Discord heartbeat messages
class HeartbeatFilter(logging.Filter):
    def filter(self, record):
        return 'heartbeat' not in record.msg.lower()

# Clean up existing handlers and set up new ones
for handler in logger.handlers[:]:
    logger.removeHandler(handler)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
console_handler.addFilter(HeartbeatFilter())
logger.addHandler(console_handler)

# Reduce Discord.py's default logging noise
discord_logger = logging.getLogger('discord')
discord_logger.setLevel(logging.WARNING)

# Load environment variables from .env file
load_dotenv()

class ToxicityBot(commands.Bot):
    def __init__(self):
        # Set up bot with message content intent enabled
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True  # Enable guilds intent
        intents.messages = True  # Make sure message intent is enabled
        super().__init__(command_prefix='!', intents=intents, case_insensitive=True)  # Make commands case-insensitive
        
        # Set command attributes
        self.add_commands()
        
        # Initialize rate limiting system
        self.message_cooldown = {}      # Track processed messages
        self.last_message_time = {}     # Track timing of last message per channel
        self.rate_limit_delay = 1.0     # Minimum seconds between messages
        
        # Initialize command processing locks
        self.command_locks = {}         # Prevent duplicate command processing
        
        # Initialize bot state
        self.analyzing_channels = set()  # Set of channels being monitored
        self.client = Client("https://duchaba-friendly-text-moderation.hf.space/")
        
        # Load previously monitored channels from file
        try:
            with open('analyzing_channels.json', 'r') as f:
                channels = json.load(f)
                self.analyzing_channels = set(channels) if channels else set()
                print(f"Loaded {len(self.analyzing_channels)} channels from file")
        except FileNotFoundError:
            print("No analyzing_channels.json file found. Creating new one.")
            with open('analyzing_channels.json', 'w') as f:
                json.dump([], f)
        except Exception as e:
            print(f"Error loading analyzing_channels.json: {e}")
            import traceback
            print(traceback.format_exc())

    def add_commands(self):
        """Add commands to the bot"""
        bot_instance = self  # Store reference to bot instance
        
        @self.command(name='analyze', help='Start toxicity analysis in this channel')
        async def analyze_prefix(ctx):
            """Start toxicity analysis in a channel (prefix command)"""
            print(f"Received command !analyze from {ctx.author} in {ctx.channel}")
            await bot_instance._handle_analyze(ctx.channel.id, ctx.send)

        @self.command(name='stop', help='Stop toxicity analysis in this channel')
        async def stop_prefix(ctx):
            """Stop toxicity analysis in a channel (prefix command)"""
            print(f"Received command !stop from {ctx.author} in {ctx.channel}")
            await bot_instance._handle_stop(ctx.channel.id, ctx.send)

    async def _handle_analyze(self, channel_id, send_message):
        """Handle the analyze command logic"""
        print(f"Handling analyze command for channel {channel_id}")
        # Prevent duplicate processing
        if channel_id in self.command_locks and self.command_locks[channel_id]:
            print(f"Ignoring duplicate analyze command for channel {channel_id}")
            await send_message("⚠️ Command is already being processed!")
            return
            
        try:
            self.command_locks[channel_id] = True
            
            # Check if channel is already being analyzed
            if channel_id in self.analyzing_channels:
                print(f"Channel {channel_id} is already being analyzed")
                await send_message("⚠️ This channel is already being analyzed!")
                return
                
            print(f"Starting analysis for channel {channel_id}")
            self.analyzing_channels.add(channel_id)
            
            # Save to file
            try:
                with open('analyzing_channels.json', 'w') as f:
                    json.dump(list(self.analyzing_channels), f)
                    print(f"Saved {len(self.analyzing_channels)} channels to file")
            except Exception as e:
                print(f"Error saving analyzing_channels.json: {e}")
                import traceback
                print(traceback.format_exc())
            
            # Send confirmation with updated message
            embed = discord.Embed(
                title="🔍 Toxicity Analysis Started",
                description="I will analyze messages in this channel for toxicity and flag toxic messages.\nUse `!stop` to stop analysis.",
                color=discord.Color.green()
            )
            await send_message(embed=embed)
            
        except Exception as e:
            print(f"Error in analyze_channel: {e}")
            import traceback
            print(traceback.format_exc())
            await send_message("❌ An error occurred while starting analysis.")
        finally:
            self.command_locks[channel_id] = False
            print(f"Released lock for channel {channel_id}")

    async def _handle_stop(self, channel_id, send_message):
        """Handle the stop command logic"""
        print(f"Handling stop command for channel {channel_id}")
        if channel_id not in self.analyzing_channels:
            await send_message("⚠️ This channel is not being analyzed!")
            return
            
        try:
            # Clean up channel resources
            await self.cleanup_channel(channel_id)
            
            # Update file
            with open('analyzing_channels.json', 'w') as f:
                json.dump(list(self.analyzing_channels), f)
                print(f"Saved {len(self.analyzing_channels)} channels to file")
            
            embed = discord.Embed(
                title="🛑 Analysis Stopped",
                description="I will no longer analyze messages in this channel.",
                color=discord.Color.red()
            )
            await send_message(embed=embed)
            
        except Exception as e:
            print(f"Error in stop_analysis: {e}")
            import traceback
            print(traceback.format_exc())
            await send_message("❌ An error occurred while stopping analysis.")

    async def cleanup_channel(self, channel_id):
        """Clean up resources for a channel"""
        # Remove from analyzing channels
        self.analyzing_channels.discard(channel_id)
        
        # Clear cooldowns for this channel
        channel_cooldowns = [k for k in self.message_cooldown.keys() if k.startswith(f"{channel_id}:")]
        for key in channel_cooldowns:
            self.message_cooldown.pop(key, None)
        
        # Clear rate limit tracking
        self.last_message_time.pop(channel_id, None)
        
        # Clear command locks
        self.command_locks.pop(channel_id, None)

    async def close(self):
        """Cleanup when bot shuts down"""
        print("\n=== Bot shutting down ===")
        
        # Clean up all channels
        for channel_id in list(self.analyzing_channels):
            await self.cleanup_channel(channel_id)
        
        # Clear all collections
        self.analyzing_channels.clear()
        self.message_cooldown.clear()
        self.last_message_time.clear()
        self.command_locks.clear()
        
        # Save empty state
        try:
            with open('analyzing_channels.json', 'w') as f:
                json.dump([], f)
        except Exception as e:
            print(f"Error saving empty analyzing_channels.json: {e}")
        
        print("=== Cleanup complete ===\n")
        await super().close()

    async def send_with_rate_limit(self, channel, content=None, embed=None):
        """Send a message with Discord rate limit handling"""
        channel_id = channel.id
        current_time = time.time()
        
        # Implement rate limiting
        if channel_id in self.last_message_time:
            time_since_last = current_time - self.last_message_time[channel_id]
            if time_since_last < self.rate_limit_delay:
                await asyncio.sleep(self.rate_limit_delay - time_since_last)
        
        try:
            # Send the message
            if content:
                await channel.send(content)
            elif embed:
                await channel.send(embed=embed)
            self.last_message_time[channel_id] = time.time()
            
        except discord.errors.HTTPException as e:
            if e.status == 429:  # Rate limit error
                # Handle Discord's rate limiting
                retry_after = e.retry_after if hasattr(e, 'retry_after') else 5
                await asyncio.sleep(retry_after)
                # Retry the message once
                if content:
                    await channel.send(content)
                elif embed:
                    await channel.send(embed=embed)
                self.last_message_time[channel_id] = time.time()

    async def setup_hook(self):
        """Initialize bot on startup"""
        print(f"{self.user} has connected to Discord!")
        if not self.analyzing_channels:
            print("No channels are being analyzed yet")
        else:
            print(f"Currently analyzing channels: {self.analyzing_channels}")

    async def on_ready(self):
        """Called when the bot is ready"""
        print(f"Logged in as {self.user}")
        
        # Print registered commands
        print("\nCommands registered:")
        for command in self.commands:
            print(f"- !{command.name}")
        
        # Print bot's permissions
        for guild in self.guilds:
            print(f"\nBot permissions in {guild.name}:")
            print(f"- Send Messages: {guild.me.guild_permissions.send_messages}")
            print(f"- Read Messages: {guild.me.guild_permissions.read_messages}")
            print(f"- View Channels: {guild.me.guild_permissions.view_channel}")
            print(f"- Send Messages in Threads: {guild.me.guild_permissions.send_messages_in_threads}")
            print(f"- Use External Emojis: {guild.me.guild_permissions.use_external_emojis}")
            print(f"- Add Reactions: {guild.me.guild_permissions.add_reactions}")
            print(f"- Embed Links: {guild.me.guild_permissions.embed_links}")
            print(f"- Attach Files: {guild.me.guild_permissions.attach_files}")
            print(f"- Read Message History: {guild.me.guild_permissions.read_message_history}")

    async def analyze_text(self, text):
        """Analyze text using the Gradio API for toxicity detection"""
        print("\n" + "="*50)
        print("TOXICITY ANALYSIS REQUEST")
        print("="*50)
        print(f"Input Text: {text}")
        
        try:
            # Call Gradio API
            result = await asyncio.to_thread(
                self.client.predict,
                text,                    # Message to analyze
                0.5,                     # Toxicity threshold
                "/fetch_toxicity_level", # API endpoint
                api_name="/fetch_toxicity_level"
            )
            
            # Handle tuple response from API
            if isinstance(result, tuple) and len(result) > 1:
                result = result[1]  # Extract JSON response
            
            # Parse string response if needed
            if isinstance(result, str):
                result = json.loads(result)
                
            # Log raw API response
            print("\nAPI Response:")
            print("-" * 30)
            print(json.dumps(result, indent=2))
            
            # Extract category scores
            category_scores = {}
            for key, value in result.items():
                if isinstance(value, (int, float)) and key not in [
                    'safer_value', 'sum_value', 'max_value', 
                    'is_flagged', 'is_safer_flagged'
                ]:
                    category_scores[key] = float(value)
            
            # Process results
            processed_result = {
                'overall_score': float(result.get('sum_value', 0.0)),
                'max_score': float(result.get('max_value', 0.0)),
                'max_category': result.get('max_key', ''),
                'category_scores': category_scores,
                'is_flagged': bool(result.get('is_flagged', False))
            }
            
            # Log processed results
            print("\nProcessed Results:")
            print("-" * 30)
            print(json.dumps(processed_result, indent=2))
            print("="*50)
            
            return processed_result
            
        except Exception as e:
            print(f"Error analyzing text: {str(e)}")
            import traceback
            print(traceback.format_exc())
            # Return safe default on error
            return {
                'overall_score': 0.0,
                'max_score': 0.0,
                'max_category': '',
                'category_scores': {},
                'is_flagged': False
            }

    async def on_message(self, message):
        """Process incoming messages for toxicity"""
        # Ignore our own messages
        if message.author == self.user:
            return
        
        # Process commands first - this is critical
        await self.process_commands(message)
        
        # Rest of message handling (only for monitored channels)
        try:
            # Skip if not in a monitored channel or if it's a command
            if (message.channel.id not in self.analyzing_channels or 
                message.content.startswith(self.command_prefix)):
                return
            
            # Check message age - ignore messages older than 30 seconds
            message_age = (discord.utils.utcnow() - message.created_at).total_seconds()
            if message_age > 30:
                return
            
            # Prevent duplicate processing
            message_key = f"{message.channel.id}:{message.id}"
            if message_key in self.message_cooldown:
                return
            
            self.message_cooldown[message_key] = time.time()
            
            # Process the message for toxicity
            try:
                # Clean up old cooldowns (older than 60 seconds)
                current_time = time.time()
                stale_keys = [
                    k for k, v in self.message_cooldown.items() 
                    if current_time - v > 60
                ]
                for k in stale_keys:
                    self.message_cooldown.pop(k, None)
                
                # Get toxicity analysis
                result = await self.analyze_text(message.content)
                
                # Only respond to toxic messages
                if result['is_flagged']:
                    # Create clickable link to the message
                    message_link = f"https://discord.com/channels/{message.guild.id}/{message.channel.id}/{message.id}"
                    
                    # Format category scores above 20%
                    significant_categories = []
                    for category, score in result['category_scores'].items():
                        if score > 0.2:  # 20% threshold
                            significant_categories.append(f"{category}: {score:.1%}")
                    
                    significant_categories.sort(reverse=True)
                    categories_text = "\n".join(significant_categories[:5])
                    
                    # Create response message
                    response = (
                        f"⚠️ **Toxic Message Detected**\n"
                        f"Overall Score: {result['overall_score']:.2f}\n"
                        f"Highest Category: {result['max_category']} ({result['max_score']:.1%})\n\n"
                        f"**Significant Categories:**\n{categories_text}\n\n"
                        f"[View Message]({message_link})"
                    )
                    
                    # Create and send embed
                    embed = discord.Embed(
                        title="Toxicity Alert",
                        description=response,
                        color=discord.Color.red()
                    )
                    embed.set_footer(text=f"Message from {message.author.name}")
                    
                    await message.channel.send(embed=embed)
            except Exception as e:
                print(f"Error in message handling: {str(e)}")
                import traceback
                print(traceback.format_exc())
        except Exception as e:
            print(f"Error in on_message: {str(e)}")
            import traceback
            print(traceback.format_exc())
        finally:
            # Clean up cooldown entry
            if 'message_key' in locals() and message_key in self.message_cooldown:
                self.message_cooldown.pop(message_key)

    # Add an error handler for command errors
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Handle command errors"""
        if isinstance(error, commands.CommandNotFound):
            print(f"Command not found: {ctx.message.content}")
            return  # Silently ignore command not found errors
        
        print(f"Command error: {error}")
        import traceback
        print(''.join(traceback.format_exception(type(error), error, error.__traceback__)))
        
        # Notify the user of the error
        await ctx.send(f"❌ An error occurred: {str(error)}")

# Create bot instance
bot = ToxicityBot()

if __name__ == "__main__":
    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Set up signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        print("\nShutdown signal received. Cleaning up...")
        # Schedule cleanup in the main event loop
        asyncio.create_task(bot.close())
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Termination request
    
    try:
        # Start the bot
        bot.run(os.getenv('DISCORD_TOKEN'))
    except KeyboardInterrupt:
        print("\nShutdown requested. Cleaning up...")
        # Let the bot handle its own cleanup
        pass
    except Exception as e:
        print(f"Error running bot: {e}")
        import traceback
        print(traceback.format_exc())
        # Let the bot handle its own cleanup
        pass