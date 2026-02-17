import logging
from discord.ext import commands

log = logging.getLogger("cog_loader")

PROTECTED_COGS = {
    "cogs.ai_chat.ai_chat",
}


class AdminReload(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log.info("[ADMIN] Cog AdminReload carregado")

    @commands.command(name="reload")
    @commands.has_permissions(administrator=True)
    async def reload(self, ctx: commands.Context, cog: str):
        ext = f"cogs.{cog}"

        if ext in PROTECTED_COGS:
            log.warning(f"[ADMIN] Tentativa de reload bloqueada: {ext}")
            await ctx.send("Esse cog não pode ser recarregado agora.")
            return

        try:
            log.info(f"[ADMIN] Recarregando cog: {ext}")
            await self.bot.reload_extension(ext)

            log.info(f"[ADMIN] Cog recarregado com sucesso: {ext}")
            await ctx.send(f"`{cog}` recarregado.")

        except Exception as e:
            log.exception(f"[ADMIN] Erro ao recarregar {ext}")
            await ctx.send(f"Falhou ao recarregar `{cog}`.")

    @commands.command(name="load")
    @commands.has_permissions(administrator=True)
    async def load(self, ctx: commands.Context, cog: str):
        ext = f"cogs.{cog}"

        try:
            log.info(f"[ADMIN] Carregando cog: {ext}")
            await self.bot.load_extension(ext)

            log.info(f"[ADMIN] Cog carregado com sucesso: {ext}")
            await ctx.send(f"`{cog}` carregado.")

        except Exception as e:
            log.exception(f"[ADMIN] Erro ao carregar {ext}")
            await ctx.send(f"Falhou ao carregar `{cog}`.")

    @commands.command(name="unload")
    @commands.has_permissions(administrator=True)
    async def unload(self, ctx: commands.Context, cog: str):
        ext = f"cogs.{cog}"

        if ext in PROTECTED_COGS:
            log.warning(f"[ADMIN] Tentativa de unload bloqueada: {ext}")
            await ctx.send("Esse cog não pode ser descarregado.")
            return

        try:
            log.info(f"[ADMIN] Descarregando cog: {ext}")
            await self.bot.unload_extension(ext)

            log.info(f"[ADMIN] Cog descarregado com sucesso: {ext}")
            await ctx.send(f"`{cog}` descarregado.")

        except Exception as e:
            log.exception(f"[ADMIN] Erro ao descarregar {ext}")
            await ctx.send(f"Falhou ao descarregar `{cog}`.")


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminReload(bot))
