import os
import random                               #Import the 'random' module to generate random numbers
import json
from twitchio.ext import commands
from dotenv import load_dotenv
from playerdata import *

# Load environment variables from the .env file into the program's environment
load_dotenv()

# Retrieve credentials and settings from environment variables
BOT_NICK = os.environ['BOT_NICK']           # The bot's Twitch username
CLIENT_ID = os.environ['CLIENT_ID']         # Your Twitch application's Client ID
CLIENT_SECRET = os.environ['CLIENT_SECRET'] # Your Twitch application's Client Secret
TOKEN = os.environ['TOKEN']                 # OAuth token for the bot to authenticate with Twitch
PREFIX = os.environ.get('PREFIX', '!')      # Command prefix (defaults to '!' if not set)
CHANNEL = os.environ['CHANNEL']             # The name of the Twitch channel to join


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

    def load_player_data(self):
        """Loads player data from the JSON file into Player objects."""
        try:
            with open('player_data.json', 'r') as f:
                data = json.load(f)
                for username, player_info in data.items():
                    self.player_data[username] = Player.from_dict(username, player_info)
        except FileNotFoundError:
            self.player_data = {}

    def save_player_data(self):
        """Saves the player data to a JSON file."""
        data = {username: player.to_dict() for username, player in self.player_data.items()}
        with open('player_data.json', 'w') as f:
            json.dump(data, f, indent=4)

    def check_level_up(self, username):
        """
        Checks if a player has enough points to level up.
        Parameters:
            - username (str): The player's username.
        """
        player = self.player_data[username]
        points = player.points
        level = player.level
        # Simple leveling: 100 points per level
        if points >= level * 100:
            player.level += 1
            self.save_player_data()
            return True
        return False

    async def event_ready(self):
        """
        Called once when the bot successfully connects to Twitch.
        Useful for initialization tasks and confirming the bot is online.
        """
        print(f'Logged in as | {self.nick}')    # Output the bot's username
        print(f'User id is | {self.user_id}')   # Output the bot's user ID

    async def event_message(self, message):
        """
        Called whenever a message is received in chat.
        """
        # Ignore messages sent by the bot itself
        if message.echo:
            return

        # Print the content of the message if author exists
        if message.author:
            print(f'{message.author.name}: {message.content}')
        else:
            print(f'Unknown author: {message.content}')

        # Process commands if any
        await self.handle_commands(message)


###################################################################
# ChatBot COMMANDS #
###################################################################

    @commands.command(name='hello')
    async def hello(self, ctx):
        """
        Responds with a greeting when a user types '~hello' in chat.
        Parameters:
            - ctx (Context): The context in which the command was invoked, 
            containing information about the message and channel.
        """
        # Send a greeting message in the chat, mentioning the user who invoked the command
        await ctx.send(f'Hello @{ctx.author.name}!')

    @commands.command(name='d20')
    async def dice(self, ctx):
        """
        Simulates rolling a 20-sided die when a user types '~d20' in chat.
        Parameters:
            - ctx (Context): The context in which the command was invoked.
        """
        # Sends a message in chat with the result of a d20 die
        num = random.randint(1,20)  #Generate a random integer between 1 and 20 inclusive
        await ctx.send(f'@{ctx.author.name} you rolled a {num}')    # Sends message to chat with result

    @commands.command(name='coinflip')
    async def coinflip(self, ctx):
        """
        Simulates flipping a coin when a user types '~coinflip' in chat.
        Parameters:
            - ctx (Context): The context in which the command was invoked.
        """
        result = random.choice(['Heads', 'Tails'])
        await ctx.send(f'@{ctx.author.name}, the coin landed on {result}!')


    @commands.command(name='secret')
    async def hello(self, ctx):
        """
        Responds with a chatOS .
        Parameters:
            - ctx (Context): The context in which the command was invoked, 
            containing information about the message and channel.
        """
        # Send a greeting message in the chat, mentioning the user who invoked the command
        await ctx.send(f'The secret is there is no secret. // Consistency over intensity / Progress over Perfection / Fundamentals over fads // Over and over again')

###################################################################
# TwitcHack COMMANDS #
###################################################################

    @commands.command(name='start')
    async def start(self, ctx):
        """
        Registers a new player or informs them if they are already registered.
        Parameters:
            - ctx (Context): The context in which the command was invoked.
        """
        username = ctx.author.name.lower()

        # Check if the user is already registered
        if username in self.player_data:
            await ctx.send(f'@{ctx.author.name}, you are already registered!')
        else:
            # Initialize the player's data with default values
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
            self.save_player_data()  # Save the updated player data
            await ctx.send(f'@{ctx.author.name}, you have been registered!')

    @commands.command(name='help')
    async def help(self, ctx):
        """
        Displays TwitcHack's commands
        Parameters:
            - ctx (Context): The context in which the command was invoked.
        """
        await ctx.send(f'@{ctx.author.name}, Commands for TwitcHack are !start, !hack, !hack <location>, !phish, !points, !leaderboard.')
   


    @commands.command(name='hack')
    async def hack(self, ctx, *, location: str = None):
        """
        Allows a player to move to a new hacking location.
        Parameters:
            - ctx (Context): The context in which the command was invoked.
            - location (str): The location to move to.
        """
        username = ctx.author.name.lower()
        
        # Check if the user is registered
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using ~start before playing.')
            return

        player = self.player_data[username]

        # If no location is provided, display the current location
        if not location:
            await ctx.send(f'@{ctx.author.name}, you are currently at {player.location}.')
            return

        # List of valid locations
        valid_locations = ['email', '/etc/shadow', 'website', 'database', 'server', 'network', 'evilcorp']

        if location.lower() in valid_locations:
            # Update the player's location
            player.location = location.lower()
            self.save_player_data()  # Save the updated player data
            await ctx.send(f'@{ctx.author.name}, you have moved to {location}!')
        else:
            await ctx.send(f'@{ctx.author.name}, invalid location. Valid locations are: {", ".join(valid_locations)}.')

    @commands.command(name='points')
    async def points(self, ctx):
        """
        Displays the player's current points.
        Parameters:
            - ctx (Context): The context in which the command was invoked.
        """
        username = ctx.author.name.lower()

        # Check if the user is registered
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using ~start before playing.')
            return

        # Retrieve the Player object
        player = self.player_data[username]
        await ctx.send(f'@{ctx.author.name}, you have {player.points} points.')

    @commands.command(name='leaderboard')
    async def leaderboard(self, ctx):
        """
        Displays the top players based on points. 
        Parameters:
            - ctx (Context): The context in which the command was invoked.
        """
        # Sort players by points in descending order
        sorted_players = sorted(
            self.player_data.items(),
            key=lambda item: item[1].points,
            reverse=True
        )
        top_players = sorted_players[:5]  # Get top 5 players

        leaderboard_message = 'Leaderboard:\n'
        for idx, (username, player) in enumerate(top_players, start=1):
            leaderboard_message += f'{idx}. {username} - {player.points} points. // '

        await ctx.send(leaderboard_message)

    @commands.command(name='phish')
    async def phish(self, ctx):
        """
        Performs a phishing attack if the player is at the 'email' location.
        Parameters:
        - ctx (Context): The context in which the command was invoked.
        """
        username = ctx.author.name.lower()

        # Check if the user is registered
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using ~start before playing.')
            return

        player = self.player_data[username]

        # Check if the player is at the 'email' location
        if player.location != 'email':
            await ctx.send(f'@{ctx.author.name}, you need to be at the email location to perform phishing.')
            return

        # Simulate phishing success or failure
        success = random.choice([True, False])
        if success:
            points_earned = random.randint(20, 60)
            player.points += points_earned
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, phishing successful! You earned {points_earned} points.')
        else:
            points_lost = random.randint(10, 30)
            player.points -= points_lost
            if player.points < 0:
                player.points = 0
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, phishing failed! You lost {points_lost} points.')



# Entry point of the script
if __name__ == '__main__':
    # Create an instance of your bot
    bot = Bot()
    # Run the bot, which connects it to Twitch
    bot.run()

