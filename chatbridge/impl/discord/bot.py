import asyncio
from enum import auto, Enum
from queue import Queue, Empty
from typing import NamedTuple, Any, List

import discord
from discord import Message, Webhook
from discord.ext import commands
from discord.ext.commands import Context
import aiohttp

from chatbridge.common import logger
from chatbridge.core.network.protocol import ChatPayload
from chatbridge.impl.discord import stored
from chatbridge.impl.discord.config import DiscordConfig
from chatbridge.impl.discord.createDiscordAvatar import get_avatar_url
from chatbridge.impl.discord.helps import CommandHelpMessageAll, CommandHelpMessage, StatsCommandHelpMessage
from chatbridge.impl.tis import bot_util


# --- Emote bridge ---
# Translates Discord custom emotes <-> Minecraft glyphs both ways, so a
# :name: typed in Minecraft shows up as the real emote in Discord and a
# <:name:id> from Discord shows up as the matching PUA glyph in Minecraft
# (rendered by a server resource pack). The emote table is loaded at startup
# from emote_map.json in the working directory; if it's missing the bridge is
# a no-op. Format: { "name": {"id": "123", "char": "", "animated": false} }
import re as _re_emote, json as _json_emote, os as _os_emote
_emote_by_id = {}
_emote_by_name = {}
_emote_by_char = {}
try:
	_emote_path = _os_emote.path.join(_os_emote.getcwd(), 'emote_map.json')
	_emote_raw = _json_emote.load(open(_emote_path, encoding='utf-8'))
	for _en, _ev in _emote_raw.items():
		_mention = '<{}:{}:{}>'.format('a' if _ev.get('animated') else '', _en, _ev['id'])
		_emote_by_id[str(_ev['id'])] = _ev['char']
		_emote_by_name[_en.lower()] = _mention
		_emote_by_char[_ev['char']] = _mention
except Exception:
	pass
_DISCORD_EMOTE_RE = _re_emote.compile(r'<a?:(\w+):(\d+)>')
_SHORTCODE_RE = _re_emote.compile(r':([A-Za-z0-9_]+):')
def _discord_emotes_to_mc(text):
	try:
		return _DISCORD_EMOTE_RE.sub(lambda m: _emote_by_id.get(m.group(2), m.group(0)), text)
	except Exception:
		return text
def _mc_emotes_to_discord(text):
	try:
		text = _SHORTCODE_RE.sub(lambda m: _emote_by_name.get(m.group(1).lower(), m.group(0)), text)
		if _emote_by_char:
			text = ''.join(_emote_by_char.get(c, c) for c in text)
		return text
	except Exception:
		return text
# --- end emote bridge ---


class MessageDataType(Enum):
	CHAT = auto()
	EMBED = auto()
	TEXT = auto()


class MessageData(NamedTuple):
	channel: int
	data: Any
	type: MessageDataType


class DiscordBot(commands.Bot):
	def __init__(self, command_prefix, **options):
		options['help_command'] = None
		super().__init__(command_prefix, **options)
		self.messages = Queue()
		self.logger = logger.ChatBridgeLogger('Bot', file_handler=stored.client.logger.file_handler)
		try:
			from google_trans_new import google_translator
			self.translator = google_translator()
		except Exception as e:
			self.logger.error('Failed to import google translator: {} {}'.format(type(e), e))
			self.translator = None

	@property
	def config(self) -> DiscordConfig:
		return stored.config

	def start_running(self):
		self.logger.info('Starting the bot')
		self.run(self.config.bot_token)

	async def listeningMessage(self):
		self.logger.info('Message listening looping...')
		try:
			channel_chat = self.get_channel(self.config.channel_for_chat)
			while True:
				try:
					message_data = self.messages.get(block=False)  # type: MessageData
				except Empty:
					await asyncio.sleep(0.05)
					continue
				data = message_data.data
				if message_data.type == MessageDataType.CHAT:  # chat message
					assert isinstance(data, tuple)
					sender: str = data[0]
					payload: ChatPayload = data[1]
					# if self.translator is not None:
					# 	try:
					# 		translation = self.translator.translate(data.message, lang_tgt='en')
					# 		dest = 'en'
					# 		if translation.src != dest:
					# 			message += '   | [{} -> {}] {}'.format(translation.src, dest, translation.text)
					# 	except:
					# 		self.logger.error('Translate fail')
					mcName = payload.author

					if mcName == "":
						message_words = payload.message.split()
						# if it's a join/leave message, have the option to send is as the bot itself or as the player
						if stored.config.send_join_as_player and message_words[1] in ["joined", "left"]:
							mcName = message_words[0]
							payload.message = "*(" + message_words[1] + " " + sender + ")*"

						else:
							# server messages, send normally
							await channel_chat.send(payload.formatted_str())
							continue

					if not mcName in stored.avatar_cache:
						print('MC name "' + mcName + '" not saved, uploading new image')
						stored.avatar_cache[mcName] = get_avatar_url(mcName, stored.config.imgbb_key)

					customUsername = mcName + " [" + sender + "]"

					async with aiohttp.ClientSession() as session:
							webhook = Webhook.from_url(stored.config.webhook_url, session=session)
							await webhook.send(
								content=_mc_emotes_to_discord(payload.message),
								username=customUsername,
								avatar_url=stored.avatar_cache[mcName]
							)

					#await channel_chat.send(self.format_message_text('[{}] {}'.format(sender, payload.formatted_str())))
				elif message_data.type == MessageDataType.EMBED:  # embed
					assert isinstance(data, discord.Embed)
					self.logger.debug('Sending embed')
					await self.get_channel(message_data.channel).send(embed=data)
				elif message_data.type == MessageDataType.TEXT:
					await self.get_channel(message_data.channel).send(self.format_message_text(str(data)))
				else:
					self.logger.debug('Unknown messageData type {}'.format(message_data.data))
		except:
			self.logger.exception('Error looping discord bot')
			await self.close()

	async def on_ready(self):
		self.logger.info(f'Logged in as {self.user}')
		await self.listeningMessage()

	async def _reply_context(self, message: Message) -> str:
		# If this Discord message is a reply, build a short prefix so MC players
		# can see who/what is being replied to: '↪ Author: «snippet…» '
		ref = getattr(message, 'reference', None)
		if ref is None:
			return ''
		orig = ref.resolved
		if orig is None and getattr(ref, 'message_id', None) is not None:
			try:
				orig = await message.channel.fetch_message(ref.message_id)
			except Exception:
				return ''
		if orig is None or isinstance(orig, discord.DeletedReferencedMessage):
			return ''
		try:
			ref_author = orig.author.display_name
		except Exception:
			ref_author = getattr(getattr(orig, 'author', None), 'name', '?')
		snippet = ' '.join(_discord_emotes_to_mc(orig.content or '').split())
		if not snippet:
			if getattr(orig, 'attachments', None):
				snippet = '[file]'
			elif getattr(orig, 'embeds', None):
				snippet = '[embed]'
			else:
				snippet = '...'
		if len(snippet) > 30:
			snippet = snippet[:30].rstrip() + '…'
		return '↪ {}: «{}» '.format(ref_author, snippet)

	async def on_message(self, message: Message):
		#ignores all bot messages
		if message.author.bot:
			return
		if message.channel.id in self.config.channels_for_command or message.channel.id == self.config.channel_for_chat:
			msg_debug = f'{message.channel}: {message.author}: {message.author.name}: {message.content}'
			args = message.content.split(' ')
			# Command
			if args[0].startswith(self.config.command_prefix) and message.channel.id in self.config.channels_for_command:
				self.logger.info('Command: {}'.format(msg_debug))
				await super().on_message(message)
				if args[0] != '!!qq':
					return
			# Chat
			if message.channel.id == self.config.channel_for_chat:
				self.logger.info('Chat: {}'.format(msg_debug))
				reply_prefix = await self._reply_context(message)
				stored.client.broadcast_chat(reply_prefix + _discord_emotes_to_mc(message.content), author=message.author.name)

	def add_message(self, data, channel_id, t):
		self.messages.put(MessageData(data=data, channel=channel_id, type=t))

	def add_embed(self, title: str, message_title: str, message: str, channel_id: int):
		embed = discord.Embed(color=discord.Colour.blue())
		embed.set_author(name=title, icon_url=self.config.embed_icon_url)
		embed.add_field(name=message_title, value=message)
		self.add_message(embed, channel_id, MessageDataType.EMBED)

	def add_stats_result(self, stats_name: str, rank_lines: List[str], total: int, channel_id: int):
		msg = ''
		length = 0
		for i, line in enumerate(rank_lines):
			msg += line
			length += len(line)
			if i == len(rank_lines) - 1 or length + len(rank_lines[i + 1]) > 1024:
				embed = discord.Embed(color=discord.Colour.blue())
				embed.set_author(name='Statistic Rank', icon_url=self.config.embed_icon_url)
				rank = [line.split(' ')[0] for line in msg.splitlines()]
				player = [self.format_message_text(line.split(' ')[1]) for line in msg.splitlines()]
				value = [bot_util.process_number(line.split(' ')[2]) for line in msg.splitlines()]
				embed.add_field(name='Stats name', value=stats_name, inline=False)
				embed.add_field(name='Rank', value='\n'.join(rank))
				embed.add_field(name='Player', value='\n'.join(player))
				embed.add_field(name='Value', value='\n'.join(value))
				if i == len(rank_lines) - 1:
					embed.set_footer(text='Total: {} | {}'.format(total, bot_util.process_number(total)))
				self.logger.debug('Adding embed with length {} in message list'.format(len(msg)))
				self.add_message(embed, channel_id, MessageDataType.EMBED)
				msg = ''
				length = 0
			else:
				msg += '\n'
				length += 1

	@staticmethod
	def format_message_text(msg):
		ret = msg
		for c in ['\\', '`', '*', '_', '<', '>', '@']:
			ret = ret.replace(c, '\\' + c)
		return ret


def create_bot() -> DiscordBot:
	config = stored.config

	intents = discord.Intents.default()
	intents.message_content = True
	bot = DiscordBot(config.command_prefix, intents=intents)

	# noinspection PyShadowingBuiltins
	@bot.command()
	async def help(ctx):
		if ctx.message.channel.id == bot.config.channel_for_chat:
			text = CommandHelpMessageAll
		else:
			text = CommandHelpMessage
		await ctx.send(text)

	@bot.command()
	async def ping(ctx: Context):
		await ctx.send('pong!!')

	async def send_chatbridge_command(target_client: str, command: str, ctx: Context):
		if stored.client.is_online():
			bot.logger.info('Sending command "{}" to client {}'.format(command, target_client))
			stored.client.send_command(target_client, command, params={'from_channel': ctx.message.channel.id})
		else:
			await ctx.send('ChatBridge client is offline')

	@bot.command()
	async def online(ctx: Context):
		if ctx.message.channel.id == bot.config.channel_for_chat:  # chat channel only
			await send_chatbridge_command(bot.config.client_to_query_online, '!!online', ctx)

	@bot.command()
	async def stats(ctx: Context, *args):
		args = list(args)
		if len(args) >= 1 and args[0] == 'rank':
			args.pop(0)
		command = '!!stats rank ' + ' '.join(args)
		if len(args) == 0 or len(args) - int(command.find('-bot') != -1) - int(command.find('-all') != -1) != 2:
			await ctx.send(StatsCommandHelpMessage)
		else:
			await send_chatbridge_command(bot.config.client_to_query_stats, command, ctx)

	return bot
