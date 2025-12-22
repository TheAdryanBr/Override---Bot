import discord
from discord.ext import commands

TARGET_CHANNEL_ID = 123456789012345678  # ID DO CANAL ONDE O EMBED VAI

class EmbedConfirmView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=None)
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Apenas quem executou o comando pode usar esses botões.",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(
        label="✅ Confirmar",
        style=discord.ButtonStyle.success,
        custom_id="embed_confirm_btn"
    )
    async def confirm(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.defer(ephemeral=True)

        channel = interaction.client.get_channel(TARGET_CHANNEL_ID)
        if not channel:
            await interaction.followup.send(
                "❌ Canal de destino não encontrado.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📢 Embed enviado com sucesso",
            description="Este embed foi confirmado via botão.",
            color=discord.Color.green()
        )

        await channel.send(embed=embed)

        await interaction.followup.send(
            "✅ Embed enviado com sucesso!",
            ephemeral=True
        )

        self.stop()

    @discord.ui.button(
        label="❌ Cancelar",
        style=discord.ButtonStyle.danger,
        custom_id="embed_cancel_btn"
    )
    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.send_message(
            "❌ Envio cancelado.",
            ephemeral=True
        )
        self.stop()


class EmbedSender(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="embedtest")
    async def embedtest(self, ctx: commands.Context):
        embed = discord.Embed(
            title="⚠️ Confirmação necessária",
            description="Deseja enviar o embed para o canal definido?",
            color=discord.Color.orange()
        )

        view = EmbedConfirmView(author_id=ctx.author.id)
        await ctx.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(EmbedSender(bot))
