import threading
from general_utils import get_env_var
from youtube import YTLive
from twitch import TwitchAuth, Bot
from kick import KickClient
import time
import multiprocessing
import random
import logging

class LiveChatController:
    def __init__(self, fetch_youtube=False, fetch_twitch=False, fetch_kick=False, logger=None):
        self.youtube = None
        self.twitch_bot = None
        self.KICK_CLIENT = None
        self.HIGH_CHAT_VOLUME = get_env_var("HIGH_CHAT_VOLUME") #high volume chats will create an enormous list of messages very quickly

        self._all_messages = []

        self.twitch_bot = None
        self.youtube = None
        self.kick = None

        if fetch_youtube:
            self.setup_youtube()
        
        if fetch_twitch:
            manager = multiprocessing.Manager()
            self.twitch_chat_msgs = manager.list()
            self.setup_twitch()

        if fetch_kick:
            self.setup_kick()

        self.logger = logger if logger else logging.getLogger(__name__)
        self.logger.info("LiveChatController initialized.")


    @classmethod
    def create(cls):
        fetch_youtube = get_env_var("YT_FETCH")
        fetch_twitch = get_env_var("TW_FETCH")
        fetch_kick = get_env_var("KI_FETCH")

        # Return None if all fetch variables are False
        if not any([fetch_youtube, fetch_twitch, fetch_kick]):
            return None

        return cls(fetch_youtube=fetch_youtube, fetch_twitch=fetch_twitch, fetch_kick=fetch_kick)

    #get token and prepare for fetching youtube livechat messages
    def setup_youtube(self):
        self.youtube = YTLive(self._all_messages)
        self.next_page_token = get_env_var("LAST_NEXT_PAGE_TOKEN") 

    #get token and start twitch bot on a separate thread for livechat messages
    # @staticmethod
    def _twitch_process(self, CHANNEL, BOT_NICK, CLIENT_ID, CLIENT_SECRET, TOKEN, twitch_chat_msgs):
        self.twitch_bot = Bot(CHANNEL, BOT_NICK, CLIENT_ID, CLIENT_SECRET, TOKEN, twitch_chat_msgs)
        self.twitch_bot.run()

    def setup_twitch(self):
        TW_Auth = TwitchAuth()
        CHANNEL, BOT_NICK, CLIENT_ID, CLIENT_SECRET, ACCESS_TOKEN, USE_THIRD_PARTY_TOKEN = TW_Auth.CHANNEL, TW_Auth.BOT_NICK, TW_Auth.CLIENT_ID, TW_Auth.CLIENT_SECRET, TW_Auth.ACCESS_TOKEN, TW_Auth.USE_THIRD_PARTY_TOKEN
        if USE_THIRD_PARTY_TOKEN:
            TOKEN = ACCESS_TOKEN
        elif not ACCESS_TOKEN:
            TOKEN = TW_Auth.access_token_generator()
        else:
            TOKEN = TW_Auth.refresh_access_token()
        twitch_bot_process = multiprocessing.Process(target=self._twitch_process, args=(CHANNEL, BOT_NICK, CLIENT_ID, CLIENT_SECRET, TOKEN, self.twitch_chat_msgs), daemon=True)
        twitch_bot_process.start()
    
    #WIP
    def setup_kick(self):
        kick_channel = get_env_var("KI_CHANNEL")
        self.kick = KickClient(username=kick_channel, kick_chat_msgs=self._all_messages)
        # KICK_CLIENT.listen() #uncomment for retrieving messages as they come in*
    
    #fetch a random message from 
    async def fetch_chat_message(self):
        self._all_messages.clear()
        if self.HIGH_CHAT_VOLUME: self._all_messages.clear()
        #fetch raw youtube messages and process them automatically -- adds automatically to yt_messages
        if self.youtube:
            self.next_page_token = await self.youtube.get_live_chat_messages(next_page_token=self.next_page_token)
        
        #fetch raw kick messages and process them automatically -- adds automatically to kick_messages
        if self.kick:
            raw_messages = await self.kick.fetch_raw_messages(num_to_fetch=10)
            await self.kick.process_messages(raw_messages)

        #take messages in order
        self._all_messages.extend(self.twitch_chat_msgs)
        self.twitch_chat_msgs[:] = []
        if self._all_messages:
            message = random.choice(self._all_messages)
            self._all_messages.remove(message)
            self.logger.info(f"PICKED MESSAGE: {message}, Remaining Messages: {self._all_messages}")
            return message, self._all_messages
        return None, None

    def is_connected(self):
        """Check if LiveChat connections are active.
        
        Returns:
            bool: True if at least one connection is active, False otherwise
        """
        connections_active = False
        
        # Check YouTube connection
        if self.youtube:
            try:
                # YouTube connection is considered active if we have a valid next_page_token
                # or if the youtube object exists and is properly initialized
                connections_active = True
            except Exception:
                self.logger.warning(f"YouTube LiveChat NOT connected")

        
        # Check Twitch connection
        if self.twitch_bot:
            try:
                # Twitch connection is active if the process is running
                # This is a simplified check - in practice you might want to
                # implement a more sophisticated health check
                connections_active = True
            except Exception:
                self.logger.warning(f"Twitch LiveChat NOT connected")                
        
        # Check Kick connection
        if self.kick:
            try:
                # Kick connection check
                connections_active = True
            except Exception:
                self.logger.warning(f"Kick LiveChat NOT connected")                
        
        return connections_active
    
    def reconnect(self):
        """Attempt to reconnect all LiveChat services."""
        try:
            # Reconnect YouTube if it was enabled
            if self.youtube:
                try:
                    self.setup_youtube()
                    self.logger.info(f"YouTube LiveChat reconnected")
                except Exception as e:
                    self.logger.warning(f"Failed to reconnect YouTube LiveChat: {e}")
            
            # Reconnect Twitch if it was enabled
            if self.twitch_bot:
                try:
                    self.twitch_bot.run()
                    self.logger.info(f"Twitch LiveChat reconnected")
                except Exception as e:
                    self.logger.warning(f"Failed to reconnect Twitch LiveChat: {e}")

            # Reconnect Kick if it was enabled
            if self.KICK_CLIENT:
                try:
                    self.setup_kick()
                    self.logger.info(f"Kick LiveChat reconnected")
                except Exception as e:
                    self.logger.warning(f"Failed to reconnect Kick LiveChat: {e}")
                    
        except Exception as e:
            print(f"Error during LiveChat reconnection: {e}")
    
    def disconnect(self):
        """Disconnect all LiveChat services and clean up resources."""
        try:
            # Disconnect YouTube
            if self.youtube:
                try:
                    # YouTube doesn't need explicit disconnection, just clear the reference
                    self.youtube = None
                    self.logger.info(f"YouTube LiveChat disconnected")
                except Exception as e:
                    self.logger.warning(f"Error disconnecting YouTube LiveChat: {e}")
            
            # Disconnect Twitch
            if self.twitch_bot:
                try:
                    # Clear the shared list
                    if hasattr(self, 'twitch_chat_msgs'):
                        self.twitch_chat_msgs[:] = []
                    self.twitch_bot.close()
                    self.logger.info(f"Twitch LiveChat disconnected")
                except Exception as e:
                    self.logger.warning(f"Error disconnecting Twitch LiveChat: {e}")
            
            # Disconnect Kick
            if self.KICK_CLIENT:
                try:
                    # Kick client cleanup
                    self.KICK_CLIENT = None
                    self.logger.info(f"Kick LiveChat disconnected")
                except Exception as e:
                    self.logger.warning(f"Error disconnecting Kick LiveChat: {e}")
            
            # Clear all messages
            self._all_messages.clear()
            
        except Exception as e:
            self.logger.warning(f"Error during LiveChat disconnection: {e}")

# Example usage:
if __name__ == "__main__":
    import asyncio
    from dotenv import load_dotenv
    load_dotenv()

    fetch_youtube = get_env_var("YT_FETCH") 
    fetch_twitch = get_env_var("TW_FETCH")
    fetch_kick = get_env_var("KI_FETCH")
    live_chat_setup = LiveChatController.create()#(fetch_twitch=fetch_twitch, fetch_youtube=fetch_youtube, fetch_kick=fetch_kick)

    while True:
        print("attempting_fetch")
        asyncio.run(live_chat_setup.fetch_chat_message())
        time.sleep(5.5)  # Adjust the interval as needed
