from disco.bot.plugin import Plugin
from disco.api.http import APIException

from datetime import datetime
import logging
import random
import time


class VocalCrewsPlugin(Plugin):
    known_guilds = {}
    crew_creators = set()
    invites = {}
    used_names = {}

    def load(self, ctx):
        super(VocalCrewsPlugin, self).load(ctx)
        if self.config['enabled']:
            self.register_listener(self.on_guild_create, 'event', 'GuildCreate')

    @staticmethod
    def allow_api_exception(method, code, *args, **kwargs):
        try:
            method(*args, **kwargs)
        except APIException as e:
            if e.code != code:
                raise e

    def create_crew_channel(self, channel, user):
        self.crew_creators.remove(channel.id)
        category_config = self.config['categories'].get(str(channel.parent.id), {})
        crew_names = category_config.get('crew_names', self.config['crew_names'])
        crew_formatter = category_config.get('crew_formatter', self.config['crew_formatter'])
        if channel.parent.id not in self.used_names:
            self.used_names[channel.parent.id] = set()
        used_names = self.used_names[channel.parent.id]
        available_names = set(crew_names).difference(used_names)
        chosen_name = random.choice(list(available_names))
        used_names.add(chosen_name)
        if len(used_names) == len(crew_names):
            used_names.clear()
        new_channel_name = crew_formatter.format(chosen_name)
        log_msg = 'Creating Crew "{}" (#{}) (requested by {})'.format(
            new_channel_name,
            channel.id,
            str(user)
        )
        logging.info(log_msg)
        self.client.api.channels_modify(channel.id, name=new_channel_name, position=int(time.time()))
        log_channel = category_config.get('log_channel', self.config['log_channel'])
        if log_channel in channel.guild.channels:
            self.client.api.channels_messages_create(
                log_channel, "[{:%X}] {}".format(datetime.now(), log_msg)
            )
        return channel

    def create_creator_channel(self, category):
        category_config = self.config['categories'].get(str(category.id), {})
        channel_name = category_config.get('new_crew_name', self.config['new_crew_name'])
        channel_limit = category_config.get('crew_size', self.config['crew_size'])
        creator = category.create_voice_channel(channel_name, user_limit=channel_limit)
        self.crew_creators.add(creator.id)
        creator.set_position(1)

    def clean_empty_channels(self, guild):
        if guild.id not in self.known_guilds:
            return
        categories = self.known_guilds[guild.id]
        guild_channels = list(guild.channels.values())
        for channel in guild_channels:
            if channel.is_voice is False or channel.id in self.crew_creators:
                continue
            if channel.parent_id and channel.parent_id in categories:
                delete_channel = True
                voice_states = list(channel.guild.voice_states.values())
                for voice_state in voice_states:
                    if voice_state.channel_id == channel.id:
                        delete_channel = False
                        break
                if delete_channel:
                    logging.info(
                        'Deleting empty channel "{}" (#{})'.format(channel.name, channel.id)
                    )
                    self.spawn(self.allow_api_exception, channel.delete, 10003)

    def send_alert(self, alert_channel, voice_channel, user, user_message):
        if voice_channel.id not in voice_channel.guild.channels:
            return
        category_config = self.config['categories'].get(str(voice_channel.parent.id), {})
        alert_invite_max_age = category_config.get('alert_invite_max_age', self.config['alert_invite_max_age'])
        invitation = voice_channel.create_invite(max_age=alert_invite_max_age)
        invitation_link = "https://discord.gg/{}".format(invitation.code)
        if voice_channel.id not in self.invites:
            self.invites[voice_channel.id] = {}
        if alert_channel.id in self.invites[voice_channel.id]:
            message_id = self.invites[voice_channel.id][alert_channel.id]
            try:
                self.client.api.channels_messages_delete(alert_channel.id, message_id)
            except APIException as e:
                if e.code != 10008:
                    raise e
        if user_message is not None:
            alert_message = category_config.get('alert_message_custom', self.config['alert_message_custom'])
            formatted_msg = alert_message.format(creator_tag=user.mention, link=invitation_link, msg=user_message)
            log_msg = "Sending invite {}, requested by {} for channel {} (#{}), with custom message:\n```{}```".format(
                invitation.code, str(user), alert_channel.name, alert_channel.id, user_message
            )
        else:
            alert_message = category_config.get('alert_message_standard', self.config['alert_message_standard'])
            formatted_msg = alert_message.format(creator_tag=user.mention, link=invitation_link)
            log_msg = "Sending invite {}, requested by {} for channel {} (#{}) without custom message".format(
                invitation.code, str(user), alert_channel.name, alert_channel.id
            )
        logging.info(log_msg)
        invite_msg = alert_channel.send_message(formatted_msg)
        self.invites[voice_channel.id][alert_channel.id] = invite_msg.id
        log_channel = category_config.get('log_channel', self.config['log_channel'])
        if log_channel in alert_channel.guild.channels:
            self.client.api.channels_messages_create(
                log_channel, "[{:%X}] {}".format(datetime.now(), log_msg)
            )

    def on_guild_create(self, event):
        guild = event.guild
        if guild.id in self.known_guilds:
            return
        register_listeners = not self.known_guilds
        logging.info('Setuping voice channels for guild "{}" (#{})'.format(guild.name, guild.id))
        config_categories = [int(c) for c in self.config['categories']]
        categories = set(guild.channels).intersection(config_categories)
        self.known_guilds[guild.id] = categories
        for category_id in categories:
            category = guild.channels[category_id]
            logging.info('Setting category "{}" (#{}) as vocal crew category'.format(category.name, category.id))
            guild_channels = list(category.guild.channels.values())
            for channel in guild_channels:
                if channel.is_voice is False:
                    continue
                if channel.parent_id and channel.parent_id == category_id:
                    delete_channel = True
                    voice_states = list(channel.guild.voice_states.values())
                    for voice_state in voice_states:
                        if voice_state.channel_id == channel.id:
                            delete_channel = False
                            break
                    if delete_channel:
                        logging.info('Deleting unknown voice channel "{}" (#{})'.format(channel.name, channel.id))
                        self.spawn(channel.delete)
                    else:
                        logging.warning(
                            'Leaving non-empty unknown voice channel "{}" (#{})'.format(channel.name, channel.id)
                        )
            self.spawn(self.create_creator_channel, category)
        if register_listeners:
            self.register_listener(self.on_voice_state_update, 'event', 'VoiceStateUpdate')
            self.register_listener(self.on_channel_delete, 'event', 'ChannelDelete')

    def on_voice_state_update(self, event):
        if event.state.channel_id in self.crew_creators:
            self.spawn(self.create_crew_channel, event.state.channel, event.state.user)
            self.spawn(self.create_creator_channel, event.state.channel.parent)
        self.spawn(self.clean_empty_channels, event.state.guild)

    def on_channel_delete(self, event):
        deleted_channel_id = event.channel.id
        if deleted_channel_id in self.invites:
            messages_to_delete = self.invites[deleted_channel_id]
            del self.invites[deleted_channel_id]
            for channel_id, message_id in messages_to_delete.items():
                self.spawn(
                    self.allow_api_exception,
                    self.client.api.channels_messages_delete,
                    10008,
                    channel_id,
                    message_id
                )

    @Plugin.command('!i', '[msg:str...]')
    def on_invite_command(self, event, msg=None):
        self.spawn(self.allow_api_exception, event.msg.delete, 10008)
        managed_categories = [int(c) for c in self.config['categories']]
        voice_states = list(event.guild.voice_states.values())
        for voice_state in voice_states:
            if voice_state.user == event.author:
                if voice_state.channel.parent.id not in managed_categories:
                    return
                category_config = self.config['categories'].get(str(voice_state.channel.parent.id), {})
                alert_channels = category_config.get('alert_allowed_channels', self.config['alert_allowed_channels'])
                if event.channel.id in alert_channels:
                    self.spawn(self.send_alert, event.channel, voice_state.channel, event.author, msg)
                break
