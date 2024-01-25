# ChatBridge

This is a fork from [TIS ChatBridge](https://github.com/TISUnion/ChatBridge), so for a generic use guide, refer to the original repository.

## Changes implemented
Makes messages sent from a Minecraft server appear as if they were sent by the Minecraft player inside the discord chatbridge channel:

![chatbridge example](https://cdn.discordapp.com/attachments/1199645472655151174/1200001234527068251/image.png?ex=65c4973d&is=65b2223d&hm=6b8694734856e616f5d9d0796b40f1747aaef328ebf5c29e94c5f6d11d6bdffc&)

The bot uses webhooks to appear as imaginary characters created automatically from a Minecraft IGN.

Next to the MC name, the ChatBridge client where the message was sent from appears between `[]`.

## How to set up
This ChatBridge modification only needs to be executed as the `discord_bot` instance.
### Additional python libraries
This implementation needs 2 extra python libraries to be installed, which are:
* **[pillow](https://pypi.org/project/pillow/):** to modify a Minecraft skin image and convert it to a square profile picture with borders
* **[imgbbpy](https://pypi.org/project/imgbbpy/):** to make API calls to [imgbb](https://imgbb.com/) and upload the custom profile pictures

### Extra config variables
The config file (`ChatBridge_discord.json`) needs some extra values, which are:
* **webhook_url:** Obtained in discord server settings -> Integrations -> Webhooks
* **imgbb_key:** Obtained in [imgbb API](https://api.imgbb.com/) (needs an account, completely free without need of credit card). This is where the custom profile pictures get saved.
* **send_join_as_player:** Boolean to choose if join/leave messages are sent by the bot itself (like in the image above) or by the player, which looks like this:

![send join as player](https://cdn.discordapp.com/attachments/1199645472655151174/1200003359013355531/join_as_player_example.png?ex=65c49937&is=65b22437&hm=efe846df547ee5f105a6643698cffb587a45eb7c01254f7bd930b9f713752630&)

### JSON Example
The first time the program is used with the command:
```
python ChatBridge.pyz discord_bot
```
will generate a `ChatBridge_discord.json` if it doesn't find it.

Example of a complete `ChatBridge_discord.json` configuration:
```json5
{
    "aes_key": "ThisIstheSecret",  // the common encrypt key
    "name": "MyClientName",  // the name of the client
    "password": "MyClientPassword",  // the password of the client
    "server_hostname": "127.0.0.1",  // the hostname of the server
    "server_port": 30001,  // the port of the server
    "bot_token": "your.bot.token.here",  // the token of your discord bot
    "webhook_url": "your.discord.server.webhook.url.here",  // the URL of your discord server's webhook
    "imgbb_key": "your.imgbb.api.key.here",  // the API key of your imgbb API v1
    "send_join_as_player": true,  // true if sent by the MC avatar, false if sent by the bot
    "channels_for_command": [  // a list of channels, public commands can be used here
        123400000000000000,
        123450000000000000
    ],
    "channel_for_chat": 123400000000000000,  // the channel for chatting and private commands
    "command_prefix": "!!",
    "client_to_query_stats": "MyClient1",  // it should be a client as an MCDR plugin, with stats_helper plugin installed in the MCDR
    "client_to_query_online": "MyClient2",  // a client described in the following section "Client to respond online command"
    "embed_icon_url": "https://cdn.discordapp.com/emojis/566212479487836160.png",  // icon that will appear on embed messages (like !!online)
    "server_display_name": "TIS"  // name that will appear on embed messages (like !!online)
}
```
