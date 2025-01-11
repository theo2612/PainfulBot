import os                                   # Import the 'OS' module to interact with the operating system, 
                                            # specifically for environment variables
import random                               # Import the 'random' module to generate random numbers
import json                                 # Import 'json' module to work with json data, for storing player data
from twitchio.ext import commands           # Import the commands module from TwitchIO to help create a TwitchBot
from dotenv import load_dotenv              # Import the function to load environment variables from a .env file
from playerdata import *                    # Import all the classes and functions defined in playerdata.py
import asyncio
from datetime import datetime, timedelta

# Load environment variables from the .env file into the program's environment
load_dotenv()

# Retrieve credentials and settings from environment variables
BOT_NICK = os.environ['BOT_NICK']           # The bot's Twitch username
CLIENT_ID = os.environ['CLIENT_ID']         # Your Twitch application's Client ID
CLIENT_SECRET = os.environ['CLIENT_SECRET'] # Your Twitch application's Client Secret
TOKEN = os.environ['TOKEN']                 # OAuth token for the bot to authenticate with Twitch
PREFIX = os.environ.get('PREFIX', '!')      # Command prefix (defaults to '!' if not set)
CHANNEL = os.environ['CHANNEL']             # The name of the Twitch channel to join
CHANNEL_OWNER = os.environ['CHANNEL_OWNER'] # The name of the Twitch channel owner

# Define a class for your bot, inheriting from twitchio's commands.Bot
class Bot(commands.Bot):

    def __init__(self):
        # Initialize the bot with required parameters
        super().__init__(
            token=TOKEN,                     # Authentication token for Twitch IRC
            client_id=CLIENT_ID,             # Client ID of your Twitch application
            nick=BOT_NICK,                   # The bot's username on Twitch
            prefix=PREFIX,                   # Command prefix for your bot (e.g., '!' for '!command')
            initial_channels=[CHANNEL]       # The channel(s) the bot should join upon connecting
        )

        # Load player data from JSON file
        self.player_data = {}
        self.load_player_data()
        self.last_battle_time = datetime.min
        self.ongoing_battle = None

    def load_player_data(self):
        # Loads player data from the JSON file into Player objects.        
        try:
            with open('player_data.json', 'r') as f:
                data = json.load(f)         # Load the JSON data from the file
                for username, player_info in data.items():
                    # Convert each player's data from a dictionary to a Player object
                    self.player_data[username] = Player.from_dict(username, player_info)
        except FileNotFoundError:
            # If the file doesn't exist, initialize an empty player directory
            self.player_data = {}

    def save_player_data(self):
        # Saves the player data to a JSON file.
        # Convert each Player object to a dictionary for serialization
        data = {username: player.to_dict() for username, player in self.player_data.items()}
        with open('player_data.json', 'w') as f:
            json.dump(data, f, indent=4)    # Write the JSON data to the file with indentation

    def check_level_up(self, username):
        # Checks and adjusts player level based on their points
        player = self.player_data[username]
        current_level = player.level
        new_level = max(1, player.points // 100)  # Floor division, minimum level 1
        
        if new_level != current_level:
            player.level = new_level
            self.save_player_data()
            return True
        return False

    def is_channel_owner(self, username):
        return username.lower() == CHANNEL_OWNER.lower()

    async def event_ready(self):
        # Called once when the bot successfully connects to Twitch.
        # Useful for initialization tasks and confirming the bot is online.
        print(f'Logged in as | {self.nick}')    # Output the bot's username
        print(f'User id is | {self.user_id}')   # Output the bot's user ID
        # Send a message to the chat indicating that the bot is online
        await self.connected_channels[0].send(f"{self.nick} is now online")

    async def event_message(self, message):
        # Called whenever a message is received in chat.
        # Parameters: - message (Message): The message object containing information about the received message.
        # Ignore messages sent by the bot itself
        if message.echo:
            return

        # Print the content of the message if author exists
        if message.author:
            print(f'{message.author.name}: {message.content}')
        else:
            print(f'Unknown author: {message.content}')

        # Handle basic keyword detection
        if "neovim" in message.content.lower():
            await message.channel.send(f'You are better than that @{message.author.name}!')

        # Process commands if any
        await self.handle_commands(message)


###################################################################
# ChatBot COMMANDS #
###################################################################

    @commands.command(name='hello')
    async def hello(self, ctx):
        # Responds with a greeting when a user types '!hello' in chat.
        # Parameters: - ctx (Context): The context in which the command was invoked, 
        #    containing information about the message and channel.
        
        # Send a greeting message in the chat, mentioning the user who invoked the command
        await ctx.send(f'Hello @{ctx.author.name}!')

    @commands.command(name='d20')
    async def dice(self, ctx):
        # Legacy command kept for backward compatibility
        num = random.randint(1,20)
        await ctx.send(f'@{ctx.author.name} you rolled a {num}')

    @commands.command(name='d4')
    async def d4(self, ctx):
        num = random.randint(1,4)
        await ctx.send(f'@{ctx.author.name} you rolled a {num}')

    @commands.command(name='d6')
    async def d6(self, ctx):
        num = random.randint(1,6)
        await ctx.send(f'@{ctx.author.name} you rolled a {num}')

    @commands.command(name='d8')
    async def d8(self, ctx):
        num = random.randint(1,8)
        await ctx.send(f'@{ctx.author.name} you rolled a {num}')

    @commands.command(name='d10')
    async def d10(self, ctx):
        num = random.randint(1,10)
        await ctx.send(f'@{ctx.author.name} you rolled a {num}')

    @commands.command(name='d12')
    async def d12(self, ctx):
        num = random.randint(1,12)
        await ctx.send(f'@{ctx.author.name} you rolled a {num}') 

    @commands.command(name='coinflip')
    async def coinflip(self, ctx):
        # Simulates flipping a coin when a user types '!coinflip' in chat.
        # Parameters: - ctx (Context): The context in which the command was invoked.
        
        # Randomly choose between 'Heads' and 'Tails'
        result = random.choice(['Heads', 'Tails'])
        # Send the result of the coin flip to chat
        await ctx.send(f'@{ctx.author.name}, the coin landed on {result}!')


    @commands.command(name='secret')
    async def secret(self, ctx):
        # Responds with a chatOS .
        # Parameters: - ctx (Context): The context in which the command was invoked, 
        #    containing information about the message and channel.

        # Send a greeting message in the chat, mentioning the user who invoked the command
        await ctx.send(f'The secret is there is no secret. // Consistency over intensity / Progress over Perfection / Fundamentals over fads // Over and over again')

###################################################################
# TwitcHack COMMANDS #
###################################################################

    @commands.command(name='start')
    async def start(self, ctx):
        username = ctx.author.name.lower()

        if username in self.player_data:
            await ctx.send(f'@{ctx.author.name}, you are already registered! Use !help to see available commands, or !status to check your stats.')
            return

        new_player = Player(
            username=username,  # Username from the chat message
            level=1,            # Default level
            health=10,          # Default health
            items=[],           # Default items
            location="home",    # Default location
            points=0,           # Default points
            started=0           # Default started
        )
        self.player_data[username] = new_player
        self.save_player_data()
        
        welcome_msg = (
            f"Welcome to TwitcHack, @{ctx.author.name}! You're now registered as a level 1 hacker. 🖥️\n"
            f"1. Use !hack <location> to move (email, website, server, etc)\n"
            f"2. Each location has unique attacks you can perform\n"
            f"3. Level up by earning points from successful hacks\n"
            f"4. Join boss battles with !bossbattle when available\n"
            f"Use !help for more commands!"
        )
        await ctx.send(welcome_msg)

    @commands.command(name='help')
    async def help(self, ctx):
        help_msg = (
            f"@{ctx.author.name}, TwitcHack Commands:\n"
            f"🎮 Basic: !start (register), !status (check stats), !points, !leaderboard\n"
            f"🌍 Movement: !hack <location> - Available locations: email, website, /etc/shadow, database, server, network, evilcorp\n"
            f"⚔️ Boss Battles: !bossbattle (start/join a team raid against the boss)\n"
            f"Type !attacks to see available attacks for your current location!"
        )
        await ctx.send(help_msg)

    @commands.command(name='attacks')
    async def attacks(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please use !start to register first!')
            return

        player = self.player_data[username]
        location = player.location
        
        attacks = {
            'email': "📧 Email attacks: !phish (lvl 0), !spoof (lvl 5), !dump (lvl 10)",
            '/etc/shadow': "🔑 Password attacks: !crack (lvl 15), !stealth (lvl 20), !bruteforce (lvl 25)",
            'website': "🌐 Web attacks: !burp (lvl 30), !sqliw (lvl 35), !xss (lvl 40)",
            'database': "💽 DB attacks: !dumpdb (lvl 45), !sqlidb (lvl 50), !admin (lvl 55)",
            'server': "🖥️ Server attacks: !revshell (lvl 60), !root (lvl 65), !ransom (lvl 70)",
            'network': "🌐 Network attacks: !sniff (lvl 75), !mitm (lvl 80), !ddos (lvl 85)",
            'evilcorp': "😈 EvilCorp attacks: !drop (lvl 90), !tailgate (lvl 95), !socialengineer (lvl 100)",
            'home': "🏠 You're at home! Use !hack <location> to move somewhere and start hacking!"
        }
        
        await ctx.send(f"@{ctx.author.name}, {attacks.get(location, 'Invalid location! Use !hack to move.')}")

    @commands.command(name='hack')
    async def hack(self, ctx, *, location: str = None):
        # Allows a player to move to a new hacking location.
        # Parameters:   - ctx (Context): The context in which the command was invoked.
        #               - location (str): The location to move to.
        
        username = ctx.author.name.lower()              # Convert the username to lowercase for consistency
        
        # Check if the user is registered
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]             # Retrieve player data

        # If no location is provided, display the current location
        if not location:
            await ctx.send(f"@{ctx.author.name}, you are currently at {player.location}. Use !hack <location> to move to: {', '.join(valid_locations)}")
            return

        # List of valid locations
        valid_locations = ['email', '/etc/shadow', 'website', 'database', 'server', 'network', 'evilcorp']
        # valid_locations = ['email', '/etc/shadow', 'website', 'database', 'server', 'network', 'evilcorp']


        # Check if the provided location is valid
        if location.lower() in valid_locations:
            # Update the player's location
            player.location = location.lower()
            self.save_player_data()  # Save the updated player data to the JSON file
            await ctx.send(f'@{ctx.author.name}, you have moved to {location}!')
        else:
            # Inform the user of invalid location and list valid options
            await ctx.send(f'@{ctx.author.name}, invalid location. Valid locations are: {", ".join(valid_locations)}.')

    @commands.command(name='points')
    async def points(self, ctx):
        # Displays the player's current points.
        # Parameters: - ctx (Context): The context in which the command was invoked.
        
        username = ctx.author.name.lower()      # Convert the username to lowercase for consistency

        # Check if the user is registered
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        # Retrieve the Player object
        player = self.player_data[username]
        # Send the player's current points to the chat
        await ctx.send(f'@{ctx.author.name}, you have {player.points} points.')

    @commands.command(name='ownerpoints')
    async def ownerpoints(self, ctx, amount: int):
        username = ctx.author.name.lower()
        if not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, this command is only for the channel owner.')
            return
        
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start first.')
            return

        player = self.player_data[username]
        player.points += amount
        self.check_level_up(username)
        self.save_player_data()
        await ctx.send(f'@{ctx.author.name}, added {amount} points. Your new total is {player.points} points.')

    @commands.command(name='leaderboard')
    async def leaderboard(self, ctx):
        # Displays the top players based on points. 
        # Parameters: - ctx (Context): The context in which the command was invoked.
        
        # Sort players by points in descending order
        sorted_players = sorted(
            self.player_data.items(),
            key=lambda item: item[1].points,   # Sort by the points attribute of each Player object 
            reverse=True
        )
        top_players = sorted_players[:5]  # Get top 5 players

        # Construct the leaderboard message
        leaderboard_message = 'Leaderboard:\n'
        for idx, (username, player) in enumerate(top_players, start=1):
            leaderboard_message += f'{idx}. {username} - {player.points} points. // '

        # Send the leaderboard message to chat
        await ctx.send(leaderboard_message)


    @commands.command(name='status')
    async def status(self, ctx):
        # Displays the player's current status including level, health, points, and location.
        # Parameters: - ctx (Context): The context in which the command was invoked.
    
        username = ctx.author.name.lower()  # Convert the username to lowercase for consistency

        # Check if the user is registered
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]  # Retrieve the player's data

        # Construct the player's status message
        status_message = (
            f"-@{ctx.author.name}, here is your current status: \n"
            f"-Level: {player.level} \n"
            f"-Health: {player.health} \n"
            f"-Points: {player.points} \n"
            f"-Location: {player.location} \n"
            f"-Items: {', '.join(player.items) if player.items else 'None'}"
        )

        # Send the player's status to the chat
        await ctx.send(status_message)

    @commands.command(name='virus')
    async def virus(self, ctx, target: str = None):
        # Allows the channel owner to spread a virus and penalize players' points.
        # Parameters: - ctx (Context): The context in which the command was invoked.
        #             - target (str, optional): The username of the player to penalize. If not provided, 25% of players will be affected.

        username = ctx.author.name.lower()  # Convert the username to lowercase for consistency

        # Check if the command user is the channel owner
        if username != CHANNEL_OWNER:
            # Penalty for unauthorized use
            if username in self.player_data:
                player = self.player_data[username]  # Retrieve the player's data
                if not hasattr(player, 'virus_attempts'):
                    player.virus_attempts = 0
                player.virus_attempts += 1
                points_lost = 50 * player.virus_attempts  # Penalty increases with each attempt
                player.points -= points_lost
                if player.points < 0:
                    player.points = 0  # Ensure points do not go below zero
                self.save_player_data()  # Save the updated player data to the JSON file
                await ctx.send(f'@{ctx.author.name}, unauthorized use of !virus! You have been penalized {points_lost} points.')
            else:
                await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        if target:
            target = target.lower()  # Convert the target username to lowercase for consistency

            # Check if the target player is registered
            if target not in self.player_data:
                await ctx.send(f'@{ctx.author.name}, the target player {target} is not registered.')
                return

            player = self.player_data[target]  # Retrieve the target player's data

            # Simulate the effect of the virus by penalizing points
            points_lost = random.randint(50, 100)  # Random points lost due to virus
            player.points -= points_lost  # Subtract the points from the player's total
            if player.points < 0:
                player.points = 0  # Ensure points do not go below zero
            self.save_player_data()  # Save the updated player data to the JSON file
            await ctx.send(f'@{ctx.author.name} has spread a virus to @{target}! They lost {points_lost} points.')
        else:
            # Spread the virus to 25% of registered players, excluding the channel owner
            all_players = [p for p in self.player_data.keys() if p != CHANNEL_OWNER]
            affected_players = random.sample(all_players, max(1, len(all_players) // 4))

            for affected in affected_players:
                player = self.player_data[affected]  # Retrieve the affected player's data
                points_lost = random.randint(50, 100)  # Random points lost due to virus
                player.points -= points_lost  # Subtract the points from the player's total
                if player.points < 0:
                    player.points = 0  # Ensure points do not go below zero

            self.save_player_data()  # Save the updated player data to the JSON file
            affected_list = ', '.join(affected_players)
            await ctx.send(f'@{ctx.author.name} has spread a virus affecting 25% of players: {affected_list}. Points have been deducted.')




    ###################################################################
    # EMAIL ATTACKS #
    ###################################################################

    @commands.command(name='phish')
    async def phish(self, ctx):
        # Performs a phishing attack if the player is at the 'email' location.
        # Parameters: - ctx (Context): The context in which the command was invoked.
        username = ctx.author.name.lower()  # Convert the username to lowercase for consistency

        # Check if the user is registered
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]  # Retrieve the player's data

        # Check if the player is at the 'email' location
        if player.location != 'email' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the email location to perform phishing.')
            return

        # Check if the player meets the required level
        if player.level < 0 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 0 to perform phishing.')
            return

        # Simulate phishing success or failure
        success = random.choice([True, False])
        if success:
            points_earned = random.randint(20, 60)  # Random points earned for successful phishing
            player.points += points_earned  # Add the points to the player's total
            self.check_level_up(username)   # Check if the player's level should be adjusted
            self.save_player_data()  # Save the updated player data to the JSON file
            await ctx.send(f'@{ctx.author.name}, phishing successful! You earned {points_earned} points.')
        else:
            points_lost = random.randint(10, 30)  # Random points lost for failed phishing
            player.points -= points_lost  # Subtract the points from the player's total
            if player.points < 0:
                player.points = 0  # Ensure points do not go below zero
            self.check_level_up(username)   # Check if the player's level should be adjusted
            self.save_player_data()  # Save the updated player data to the JSON file
            await ctx.send(f'@{ctx.author.name}, phishing failed! You lost {points_lost} points.')

    @commands.command(name='spoof')
    async def spoof(self, ctx):
        # Simulates sending an email from a spoofed address if the player is at the 'email' location.
        # Parameters: - ctx (Context): The context in which the command was invoked.
        username = ctx.author.name.lower()  # Convert the username to lowercase for consistency

        # Check if the user is registered
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]  # Retrieve the player's data

        # Check if the player is at the 'email' location
        if player.location != 'email' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the email location to send a spoofed email.')
            return

        # Check if the player meets the required level
        if player.level < 5 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 5 to send a spoofed email.')
            return

        # Simulate spoofing success or failure
        success = random.choice([True, False])
        if success:
            points_earned = random.randint(30, 70)  # Random points earned for successful spoofing
            player.points += points_earned  # Add the points to the player's total
            self.check_level_up(username)   # Check if the player's level should be adjusted
            self.save_player_data()  # Save the updated player data to the JSON file
            await ctx.send(f'@{ctx.author.name}, spoofing successful! You earned {points_earned} points.')
        else:
            points_lost = random.randint(15, 35)  # Random points lost for failed spoofing
            player.points -= points_lost  # Subtract the points from the player's total
            if player.points < 0:
                player.points = 0  # Ensure points do not go below zero
            self.check_level_up(username)   # Check if the player's level should be adjusted
            self.save_player_data()  # Save the updated player data to the JSON file
            await ctx.send(f'@{ctx.author.name}, spoofing failed! You lost {points_lost} points.')

    @commands.command(name='dump')
    async def dump(self, ctx):
        # Simulates dumping all emails from a compromised account if the player is at the 'email' location.
        # Parameters: - ctx (Context): The context in which the command was invoked.
    
        username = ctx.author.name.lower()  # Convert the username to lowercase for consistency

        # Check if the user is registered
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]  # Retrieve the player's data

        # Check if the player is at the 'email' location
        if player.location != 'email' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the email location to dump emails.')
            return

        # Check if the player meets the required level
        if player.level < 10 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 10 to dump emails.')
            return

        # Simulate dumping success or failure
        success = random.choice([True, False])
        if success:
            points_earned = random.randint(40, 80)  # Random points earned for successful dump
            player.points += points_earned  # Add the points to the player's total
            self.check_level_up(username)   # Check if the player's level should be adjusted
            self.save_player_data()  # Save the updated player data to the JSON file
            await ctx.send(f'@{ctx.author.name}, email dump successful! You earned {points_earned} points.')
        else:
            points_lost = random.randint(20, 40)  # Random points lost for failed dump
            player.points -= points_lost  # Subtract the points from the player's total
            if player.points < 0:
                player.points = 0  # Ensure points do not go below zero
            self.check_level_up(username)   # Check if the player's level should be adjusted
            self.save_player_data()  # Save the updated player data to the JSON file
            await ctx.send(f'@{ctx.author.name}, email dump failed! You lost {points_lost} points.')

    ###################################################################
    # /etc/shadow ATTACKS #
    ###################################################################

    @commands.command(name='crack')
    async def crack(self, ctx):
        # Simulates cracking hashed passwords when at '/etc/shadow' location.
        # Parameters: - ctx (Context): The context in which the command was invoked.

        username = ctx.author.name.lower()      # Convert the username to lowercase for consistency

        # Check if the user is registered
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]     # Retrieve the player's data

        # Check if the player is at the '/etc/shadow' location
        if player.location != '/etc/shadow' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the /etc/shadow location to crack hashes.')
            return

        # Check if the player meets the required level
        if player.level < 15 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 15 to crack hashes.')
            return

        # Simulate cracking success or failure
        success = random.choice([True, False])
        if success:
            points_earned = random.randint(50, 90)  # Random points earned for successful cracking
            player.points += points_earned  # Add the points to the player's total
            self.check_level_up(username)   # Check if the player's level should be adjusted
            self.save_player_data()  # Save the updated player data to the JSON file
            await ctx.send(f'@{ctx.author.name}, cracking successful! You earned {points_earned} points.')
        else:
            points_lost = random.randint(10, 30)  # Random points lost for failed cracking
            player.points -= points_lost  # Subtract the points from the player's total
            if player.points < 0:
                player.points = 0  # Ensure points do not go below zero
            self.check_level_up(username)   # Check if the player's level should be adjusted
            self.save_player_data()  # Save the updated player data to the JSON file
            await ctx.send(f'@{ctx.author.name}, cracking failed! You lost {points_lost} points.')

    @commands.command(name='stealth')
    async def stealth(self, ctx):
        # Simulates hiding tracks by modifying log files when at '/etc/shadow' location.
        # Parameters: - ctx (Context): The context in which the command was invoked.

        username = ctx.author.name.lower()  # Convert the username to lowercase for consistency

        # Check if the user is registered
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]  # Retrieve the player's data

        # Check if the player is at the '/etc/shadow' location
        if player.location != '/etc/shadow' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the /etc/shadow location to hide your tracks.')
            return

        # Check if the player meets the required level
        if player.level < 20 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 20 to hide your tracks.')
            return

        # Simulate success or failure of hiding tracks
        success = random.choice([True, False])
        if success:
            points_earned = random.randint(60, 100)  # Random points earned for successful stealth
            player.points += points_earned  # Add the points to the player's total
            self.check_level_up(username)   # Check if the player's level should be adjusted
            self.save_player_data()  # Save the updated player data to the JSON file
            await ctx.send(f'@{ctx.author.name}, stealth successful! You earned {points_earned} points.')
        else:
            points_lost = random.randint(5, 20)  # Random points lost for failed stealth
            player.points -= points_lost  # Subtract the points from the player's total
            if player.points < 0:
                player.points = 0  # Ensure points do not go below zero
            self.check_level_up(username)   # Check if the player's level should be adjusted
            self.save_player_data()  # Save the updated player data to the JSON file
            await ctx.send(f'@{ctx.author.name}, stealth failed! You lost {points_lost} points.')

    @commands.command(name='bruteforce')
    async def bruteforce(self, ctx):
        # Simulates performing a brute force attack on password hashes when at '/etc/shadow' location.
        # Parameters: - ctx (Context): The context in which the command was invoked.

        username = ctx.author.name.lower()  # Convert the username to lowercase for consistency

        # Check if the user is registered
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]  # Retrieve the player's data

        # Check if the player is at the '/etc/shadow' location
        if player.location != '/etc/shadow' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the /etc/shadow location to perform a brute force attack.')
            return

        # Check if the player meets the required level
        if player.level < 25 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 25 to perform a brute force attack.')
            return


        # Simulate success or failure of brute force attack
        success = random.choice([True, False])
        if success:
            points_earned = random.randint(70, 110)  # Random points earned for successful brute force
            player.points += points_earned  # Add the points to the player's total
            self.check_level_up(username)   # Check if the player's level should be adjusted
            self.save_player_data()  # Save the updated player data to the JSON file
            await ctx.send(f'@{ctx.author.name}, brute force attack successful! You earned {points_earned} points.')
        else:
            points_lost = random.randint(15, 40)  # Random points lost for failed brute force
            player.points -= points_lost  # Subtract the points from the player's total
            if player.points < 0:
                player.points = 0  # Ensure points do not go below zero
            self.check_level_up(username)   # Check if the player's level should be adjusted
            self.save_player_data()  # Save the updated player data to the JSON file
            await ctx.send(f'@{ctx.author.name}, brute force attack failed! You lost {points_lost} points.')

    ###################################################################
    # WEBSITE ATTACKS #
    ###################################################################

    @commands.command(name='burp')
    async def burp(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'website' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the website location to scan.')
            return

        if player.level < 30 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 30 to use Burp Suite.')
            return

        success = random.choice([True, False])
        if success:
            points_earned = random.randint(80, 120)
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, vulnerability scan successful! You earned {points_earned} points.')
        else:
            points_lost = random.randint(20, 45)
            player.points = max(0, player.points - points_lost)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, scan failed! You lost {points_lost} points.')

    @commands.command(name='sqliw')
    async def sqliw(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'website' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the website location for SQL injection.')
            return

        if player.level < 35 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 35 for SQL injection.')
            return

        success = random.choice([True, False])
        if success:
            points_earned = random.randint(90, 130)
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, SQL injection successful! You earned {points_earned} points.')
        else:
            points_lost = random.randint(25, 50)
            player.points = max(0, player.points - points_lost)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, SQL injection failed! You lost {points_lost} points.')

    @commands.command(name='xss')
    async def xss(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'website' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the website location for XSS attacks.')
            return

        if player.level < 40 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 40 for XSS attacks.')
            return

        success = random.choice([True, False])
        if success:
            points_earned = random.randint(100, 140)
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, XSS attack successful! You earned {points_earned} points.')
        else:
            points_lost = random.randint(30, 55)
            player.points = max(0, player.points - points_lost)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, XSS attack failed! You lost {points_lost} points.')

    ###################################################################
    # DATABASE ATTACKS #
    ###################################################################

    @commands.command(name='dumpdb')
    async def dumpdb(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'database' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the database location to dump data.')
            return

        if player.level < 45 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 45 to dump database.')
            return

        success = random.choice([True, False])
        if success:
            points_earned = random.randint(110, 150)
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, database dump successful! You earned {points_earned} points.')
        else:
            points_lost = random.randint(35, 60)
            player.points = max(0, player.points - points_lost)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, database dump failed! You lost {points_lost} points.')

    @commands.command(name='sqlidb')
    async def sqlidb(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'database' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the database location for SQL injection.')
            return

        if player.level < 50 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 50 to attempt database SQL injection.')
            return

        success = random.choice([True, False])
        if success:
            points_earned = random.randint(120, 160)
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, database SQL injection successful! You gained unauthorized access. You earned {points_earned} points.')
        else:
            points_lost = random.randint(40, 65)
            player.points = max(0, player.points - points_lost)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, database SQL injection failed! Your query was blocked. You lost {points_lost} points.')

    @commands.command(name='admin')
    async def admin(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'database' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the database location for privilege escalation.')
            return

        if player.level < 55 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 55 to attempt privilege escalation.')
            return

        success = random.choice([True, False])
        if success:
            points_earned = random.randint(130, 170)
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, privilege escalation successful! You now have admin access. You earned {points_earned} points.')
        else:
            points_lost = random.randint(45, 70)
            player.points = max(0, player.points - points_lost)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, privilege escalation failed! Your attempt was logged and blocked. You lost {points_lost} points.')

    ###################################################################
    # SERVER ATTACKS #
    ###################################################################

    @commands.command(name='revshell')
    async def revshell(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'server' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the server location to establish a reverse shell.')
            return

        if player.level < 60 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 60 to attempt a reverse shell.')
            return

        success = random.choice([True, False])
        if success:
            points_earned = random.randint(140, 180)
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, reverse shell established! You earned {points_earned} points.')
        else:
            points_lost = random.randint(50, 75)
            player.points = max(0, player.points - points_lost)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, reverse shell attempt failed! You lost {points_lost} points.')

    @commands.command(name='root')
    async def root(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'server' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the server location for privilege escalation.')
            return

        if player.level < 65 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 65 to attempt root escalation.')
            return

        success = random.choice([True, False])
        if success:
            points_earned = random.randint(150, 190)
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, root access achieved! You earned {points_earned} points.')
        else:
            points_lost = random.randint(55, 80)
            player.points = max(0, player.points - points_lost)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, privilege escalation failed! You lost {points_lost} points.')

    @commands.command(name='ransom')
    async def ransom(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'server' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the server location to deploy ransomware.')
            return

        if player.level < 70 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 70 to attempt ransomware deployment.')
            return

        success = random.choice([True, False])
        if success:
            points_earned = random.randint(160, 200)
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, ransomware deployed successfully! You earned {points_earned} points.')
        else:
            points_lost = random.randint(60, 85)
            player.points = max(0, player.points - points_lost)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, ransomware deployment failed! You lost {points_lost} points.')

    ###################################################################
    # NETWORK ATTACKS #
    ###################################################################

    @commands.command(name='sniff')
    async def sniff(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'network' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the network location to sniff traffic.')
            return

        if player.level < 75 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 75 to attempt network sniffing.')
            return

        success = random.choice([True, False])
        if success:
            points_earned = random.randint(170, 210)
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, network sniffing successful! Captured sensitive data! You earned {points_earned} points.')
        else:
            points_lost = random.randint(65, 90)
            player.points = max(0, player.points - points_lost)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, network sniffing failed! You lost {points_lost} points.')

    @commands.command(name='mitm')
    async def mitm(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'network' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the network location for MITM attacks.')
            return

        if player.level < 80 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 80 to attempt MITM attack.')
            return

        success = random.choice([True, False])
        if success:
            points_earned = random.randint(180, 220)
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, MITM attack successful! Intercepted traffic! You earned {points_earned} points.')
        else:
            points_lost = random.randint(70, 95)
            player.points = max(0, player.points - points_lost)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, MITM attack failed! You lost {points_lost} points.')

    @commands.command(name='ddos')
    async def ddos(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'network' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the network location to launch DDoS attacks.')
            return

        if player.level < 85 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 85 to attempt DDoS attack.')
            return

        success = random.choice([True, False])
        if success:
            points_earned = random.randint(190, 230)
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, DDoS attack successful! Services disrupted! You earned {points_earned} points.')
        else:
            points_lost = random.randint(75, 100)
            player.points = max(0, player.points - points_lost)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, DDoS attack failed! You lost {points_lost} points.')

    ###################################################################
    # EVILCORP ATTACKS #
    ###################################################################

    @commands.command(name='drop')
    async def drop(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'evilcorp' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the EvilCorp location for a USB drop attack.')
            return

        if player.level < 90 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 90 to attempt a USB drop attack.')
            return

        success = random.choice([True, False])
        if success:
            points_earned = random.randint(200, 240)
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, USB drop attack successful! Target connected the device! You earned {points_earned} points.')
        else:
            points_lost = random.randint(80, 105)
            player.points = max(0, player.points - points_lost)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, USB drop attack failed! No one took the bait. You lost {points_lost} points.')

    @commands.command(name='tailgate')
    async def tailgate(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'evilcorp' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the EvilCorp location to attempt tailgating.')
            return

        if player.level < 95 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 95 to attempt tailgating.')
            return

        success = random.choice([True, False])
        if success:
            points_earned = random.randint(210, 250)
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, tailgating successful! You slipped in unnoticed. You earned {points_earned} points.')
        else:
            points_lost = random.randint(85, 110)
            player.points = max(0, player.points - points_lost)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, tailgating failed! Security caught you. You lost {points_lost} points.')

    @commands.command(name='socialengineer')
    async def socialengineer(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'evilcorp' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the EvilCorp location for social engineering.')
            return

        if player.level < 100 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 100 to attempt social engineering.')
            return

        success = random.choice([True, False])
        if success:
            points_earned = random.randint(220, 260)
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, social engineering successful! You obtained sensitive information. You earned {points_earned} points.')
        else:
            points_lost = random.randint(90, 115)
            player.points = max(0, player.points - points_lost)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, social engineering failed! Your cover was blown. You lost {points_lost} points.')

    ###################################################################
    # BOSS BATTLE #
    ###################################################################

    @commands.command(name='bossbattle')
    async def bossbattle(self, ctx):
        username = ctx.author.name.lower()
        
        if self.ongoing_battle:
            await ctx.send("A boss battle is already in progress!")
            return

        if datetime.now() - self.last_battle_time < timedelta(hours=1):
            await ctx.send("Please wait 1 hour between boss battles!")
            return

        # Use b7h30's actual stats from player_data
        boss_player = self.player_data.get('b7h30')
        if not boss_player:
            await ctx.send("Error: Boss not registered.")
            return

        self.ongoing_battle = BossBattle(
            boss_name='b7h30',
            boss_health=boss_player.health  # This will use the 1000 HP from player_data.json
        )
        self.last_battle_time = datetime.now()
        
        await ctx.send(
            f"⚔️ BOSS BATTLE INITIATED! ⚔️\n"
            f"💀 Boss: 1337haxxor Theo (HP: {boss_player.health})\n"
            f"👥 Type !joinbattle in the next 30 seconds to join the raid team! (max 5 members)\n"
            f"💪 Smaller teams get bigger rewards if they win!\n"
            f"⚔️ Each survivor gets points and +5 permanent max HP!"
        )
        
        # Start join timer
        await asyncio.sleep(30)
        self.ongoing_battle.join_phase = False
        
        if not self.ongoing_battle.challenger_team:
            await ctx.send("No challengers joined! Battle cancelled.")
            self.ongoing_battle = None
            return

        await ctx.send("Join phase ended! Battle beginning...")
        await self.run_team_battle(ctx)

    @commands.command(name='joinbattle')
    async def joinbattle(self, ctx):
        username = ctx.author.name.lower()
        
        if not self.ongoing_battle or not self.ongoing_battle.join_phase:
            await ctx.send("No battle to join right now!")
            return
            
        if username == CHANNEL_OWNER.lower():
            await ctx.send("The boss cannot join the challenger team!")
            return

        if len(self.ongoing_battle.challenger_team) >= 5:
            await ctx.send("The team is full!")
            return

        if username not in self.player_data:
            await ctx.send(f"@{ctx.author.name}, please register first with !start")
            return

        player = self.player_data[username]
        self.ongoing_battle.challenger_team[username] = player.health
        await ctx.send(f"@{ctx.author.name} has joined the raid! ({len(self.ongoing_battle.challenger_team)}/5 members)")

    async def run_team_battle(self, ctx):
        battle = self.ongoing_battle
        turn = 0
        max_turns = 15  # Extended for team battles

        while battle.boss_health > 0 and battle.challenger_team and turn < max_turns:
            turn += 1
            await ctx.send(f"⚔️ Turn {turn} ⚔️")

            # Boss AOE attack
            damage = random.randint(10, 30)
            dead_players = []
            
            boss_action = random.choice([
                "launches a massive DDoS attack!",
                "deploys ransomware across the network!",
                "executes a supply chain attack!",
                "activates the corporate defenses!",
                "sets rgb keyboard to red!",
                "sends 'AngyTheo' emote!"
            ])
            
            await ctx.send(f"🔥 {battle.boss_name} {boss_action}")
            
            for player_name, health in battle.challenger_team.items():
                new_health = max(0, health - damage)
                battle.challenger_team[player_name] = new_health
                if new_health <= 0:
                    dead_players.append(player_name)
                    await ctx.send(f"☠️ @{player_name} has fallen!")
                else:
                    await ctx.send(f"@{player_name} takes {damage} damage! ({new_health} HP remaining)")

            # Remove defeated players
            for player in dead_players:
                del battle.challenger_team[player]

            if not battle.challenger_team:
                break

            # Team attack phase
            await ctx.send("🗡️ Team attack phase:")
            total_damage = 0
            for player_name in battle.challenger_team:
                player_damage = random.randint(5, 15)
                total_damage += player_damage
                battle.team_damage += player_damage
                
                attack_action = random.choice([
                    "executes a SQL injection",
                    "deploys a zero-day exploit",
                    "launches a social engineering attack",
                    "attempts a buffer overflow",
                    "distracts Theo by disparaging the Cleveland Browns"
                ])
                
                await ctx.send(f"@{player_name} {attack_action} for {player_damage} damage!")

            battle.boss_health = max(0, battle.boss_health - total_damage)
            await ctx.send(f"Boss HP: {battle.boss_health} | Team members remaining: {len(battle.challenger_team)}")
            await asyncio.sleep(2)

        # Battle resolution
        if battle.boss_health <= 0:
            await self.reward_team(ctx)
        else:
            await ctx.send(f"{battle.boss_name} has defeated the challenger team!")
            
        self.ongoing_battle = None
        self.save_player_data()

    async def reward_team(self, ctx):
        battle = self.ongoing_battle
        base_reward = 200
        team_size_bonus = (5 - len(battle.challenger_team)) * 50  # Smaller teams get bigger bonus
        damage_bonus = battle.team_damage // 50

        for username in battle.challenger_team:
            player = self.player_data[username]
            points_earned = base_reward + team_size_bonus + damage_bonus
            player.points += points_earned
            player.health += 5  # Small permanent health boost for surviving
            self.check_level_up(username)
            await ctx.send(f"@{username} earned {points_earned} points and +5 max HP!")

        await ctx.send(f"The team has defeated {battle.boss_name}! Congratulations!")

class BossBattle:
    def __init__(self, boss_name, boss_health):
        self.boss_name = boss_name
        self.boss_health = boss_health
        self.challenger_team = {}  # Dict of {username: health}
        self.join_phase = True
        self.join_timer = 30  # Seconds
        self.team_damage = 0  # Track total team damage for rewards

# Entry point of the script
if __name__ == '__main__':
    # Create an instance of your bot
    bot = Bot()
    # Run the bot, which connects it to Twitch
    bot.run()

