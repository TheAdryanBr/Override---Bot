# cogs/welcome.py
import os
from datetime import datetime, timezone
import discord
from discord.ext import commands

WELCOME_CHANNEL_ID = int(os.environ.get("WELCOME_CHANNEL_ID", 0))
WELCOME_LOG_CHANNEL_ID = int(os.environ.get("WELCOME_LOG_CHANNEL_ID") or 0)
MEMBER_ROLE_ID = int(os.environ.get("MEMBER_ROLE_ID", 0))

_WELCOME_COLOR_RAW = -2342853
_WELCOME_COLOR = _WELCOME_COLOR_RAW & 0xFFFFFF

def _find_welcome_channel(guild: discord.Guild) -> discord.TextChannel:
    if WELCOME_CHANNEL_ID:
        ch = guild.get_channel(WELCOME_CHANNEL_ID)
        if isinstance(ch, discord.TextChannel):
            return ch
    candidates = {"welcome", "welcomes", "boas-vindas", "bem-vindos", "entradas", "entrada", "welcome-channel"}
    for c in guild.text_channels:
        if c.name.lower() in candidates:
            return c
    return None

def _build_welcome_embed(member: discord.Member) -> discord.Embed:
    title = f"``` {member.display_name} | 𝘽𝙚𝙢-𝙫𝙞𝙣𝙙𝙤(𝙖)! ao Spawnpoint```"
    description = f"```Seja bem-vindo(a) {member.display_name}, agradeço a entrada, espero que possa se torar um membro regular do lobby.```"
    embed = discord.Embed(title=title, description=description, color=discord.Color(_WELCOME_COLOR))
    try:
        avatar_url = member.display_avatar.url
        embed.set_thumbnail(url=avatar_url)
    except Exception:
        pass
    embed.add_field(
        name="📢│𝙁𝙞𝙦𝙪𝙚 𝙖𝙩𝙚𝙣𝙩𝙤!",
        value="Leias as <#1213332268618096690>\nDuvidas e sugestões no canal: <#1259311950958170205>\n Sou grato por entrar 😁",
        inline=False
    )
    return embed

class WelcomeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        try:
            if member.bot:
                return
            guild = member.guild
            if not guild:
                return
            channel = _find_welcome_channel(guild)
            if channel is None and WELCOME_CHANNEL_ID:
                try:
                    ch = guild.get_channel(WELCOME_CHANNEL_ID)
                    if isinstance(ch, discord.TextChannel):
                        channel = ch
                except Exception:
                    channel = None
            if channel:
                embed = _build_welcome_embed(member)
                try:
                    await channel.send(content=member.mention, embed=embed, allowed_mentions=discord.AllowedMentions(users=True))
                except Exception:
                    pass
                if WELCOME_LOG_CHANNEL_ID:
                    try:
                        log_ch = guild.get_channel(WELCOME_LOG_CHANNEL_ID)
                        if isinstance(log_ch, discord.TextChannel):
                            await log_ch.send(embed=embed)
                    except Exception:
                        pass

            # auto-role
            role = None
            if MEMBER_ROLE_ID:
                try:
                    role = guild.get_role(MEMBER_ROLE_ID)
                except Exception:
                    role = None
            if role is None:
                candidate_names = {"membro", "member", "user", "usuario", "usuário", "participante"}
                role = next((r for r in guild.roles if r.name.lower() in candidate_names), None)
            if role:
                try:
                    me = guild.me
                    if me is None:
                        return
                    if not guild.me.guild_permissions.manage_roles:
                        return
                    if me.top_role.position <= role.position:
                        return
                    await member.add_roles(role, reason="Auto-role: atribuído ao entrar no servidor")
                except Exception:
                    pass
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        try:
            guild = member.guild
            if not guild:
                return
            channel = _find_welcome_channel(guild)
            content = f"({member.mention} saiu do servidor) Triste, mas vá com Deus meu mano."
            if channel:
                try:
                    await channel.send(content, allowed_mentions=discord.AllowedMentions(users=True))
                except Exception:
                    pass
            if WELCOME_LOG_CHANNEL_ID:
                try:
                    log_ch = guild.get_channel(WELCOME_LOG_CHANNEL_ID)
                    if isinstance(log_ch, discord.TextChannel):
                        await log_ch.send(content, allowed_mentions=discord.AllowedMentions(users=True))
                except Exception:
                    pass
        except Exception:
            pass

async def setup(bot):
    await bot.add_cog(WelcomeCog(bot))
