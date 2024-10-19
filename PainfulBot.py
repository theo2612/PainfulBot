import os                                   # Import the 'OS' module to interact with the operating system, 
                                            # specifically for environment variables
import random                               # Import the 'random' module to generate random numbers
import json                                 # Import 'json' module to work with json data, for storing player data
from twitchio.ext import commands           # Import the commands module from TwitchIO to help create a TwitchBot
from dotenv import load_dotenv              # Import the function to load environment variables from a .env file
from playerdata import *                    # Import all the classes and functions defined in playerdata.py

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
        # Checks if a player has enough points to level up.
        # Parameters: - username (str): The player's username.
        # Returns: - bool: True if the player levels up, False otherwise.
        player = self.player_data[username]         # Retrieve the player's data
        points = player.points                      # Get the player's current points
        level = player.level                        # Get the player's current level
        # Simple leveling: 100 points per level
        if points >= level * 100:
            player.level += 1                       # Increment the player level
            self.save_player_data()                 # Save the updated player data
            return True
        return False

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
        # Simulates rolling a 20-sided die when a user types '!d20' in chat.
        # Parameters: - ctx (Context): The context in which the command was invoked.
    
        # Sends a message in chat with the result of a d20 die
        num = random.randint(1,20)  #Generate a random integer between 1 and 20 inclusive
        await ctx.send(f'@{ctx.author.name} you rolled a {num}')    # Sends message to chat with result

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
        # Registers a new player or informs them if they are already registered.
        # Parameters: - ctx (Context): The context in which the command was invoked.
        
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
            # Add the new player to the player data dictionary
            self.player_data[username] = new_player
            self.save_player_data()  # Save the updated player data to the JSON file
            await ctx.send(f'@{ctx.author.name}, you have been registered!')

    @commands.command(name='help')
    async def help(self, ctx):
        # Displays TwitcHack's commands
        # Parameters: - ctx (Context): The context in which the command was invoked.
        
        # Send a list of available commands to the user
        await ctx.send(f'@{ctx.author.name}, Commands for TwitcHack are !start, !hack, !hack <location>, !phish, !points, !leaderboard.')
   

    @commands.command(name='hack')
    async def hack(self, ctx, *, location: str = None):
        # Allows a player to move to a new hacking location.
        # Parameters:   - ctx (Context): The context in which the command was invoked.
        #               - location (str): The location to move to.
        
        username = ctx.author.name.lower()              # Convert the username to lowercase for consistency
        
        # Check if the user is registered
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using ~start before playing.')
            return

        player = self.player_data[username]             # Retrieve player data

        # If no location is provided, display the current location
        if not location:
            await ctx.send(f'@{ctx.author.name}, you are currently at {player.location}.')
            return

        # List of valid locations
        valid_locations = ['email', '/etc/shadow', 'website', 'database', 'server', 'network', 'evilcorp']

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
            await ctx.send(f'@{ctx.author.name}, please register using ~start before playing.')
            return

        # Retrieve the Player object
        player = self.player_data[username]
        # Send the player's current points to the chat
        await ctx.send(f'@{ctx.author.name}, you have {player.points} points.')

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

    @commands.command(name='phish')
    async def phish(self, ctx):
        # Performs a phishing attack if the player is at the 'email' location.
        # Parameters: - ctx (Context): The context in which the command was invoked.
        
        username = ctx.author.name.lower()      # Convert the username to lowercase for consistency

        # Check if the user is registered
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]     # Retrieve the player's data

        # Check if the player is at the 'email' location
        if player.location != 'email':
            await ctx.send(f'@{ctx.author.name}, you need to be at the email location to perform phishing.')
            return

        # Simulate phishing success or failure
        success = random.choice([True, False])
        if success:
            points_earned = random.randint(20, 60)      # Random points earned for successful phishing
            player.points += points_earned              # Add the points to the player's to
            self.save_player_data()                     # Save the updated player data to the JSON file
            await ctx.send(f'@{ctx.author.name}, phishing successful! You earned {points_earned} points.')
        else:
            points_lost = random.randint(10, 30)        # Random points lost for failed phishing
            player.points -= points_lost                # Subtract the points from the player's total
            player.points -= points_lost  
            if player.points < 0:
                player.points = 0                       # Ensure points do not go below zero
            self.save_player_data()                     # Save the updated player data to the JSON file
            await ctx.send(f'@{ctx.author.name}, phishing failed! You lost {points_lost} points.')



# Entry point of the script
if __name__ == '__main__':
    # Create an instance of your bot
    bot = Bot()
    # Run the bot, which connects it to Twitch
    bot.run()

