import discord
from discord import app_commands, ui
from discord.ext import commands
from datetime import datetime, timezone
from typing import Optional
from loguru import logger

from src.config import get_settings
from src.config.dynamic_config import DynamicConfig
from src.database import ConfigRepository, LogRepository, OrderRepository, OrderStatus


# ══════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════

def is_admin_check():
    async def predicate(interaction: discord.Interaction) -> bool:
        settings = get_settings()
        admin_id = await DynamicConfig.role_admin_id() or settings.role_admin_id
        return any(r.id == admin_id for r in interaction.user.roles)
    return app_commands.check(predicate)


def color_from_hex(hex_str: str) -> int:
    try:
        return int(hex_str.strip().lstrip("#"), 16)
    except Exception:
        return 0x5865F2


async def get_daily_stats(guild) -> dict:
    """Calcula Robux e R$ vendidos hoje."""
    from sqlalchemy import select, func
    from src.database.models import Order
    from src.database.connection import db
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    async with db.get_session() as session:
        result = await session.execute(
            select(
                func.coalesce(func.sum(Order.robux_amount), 0).label("robux"),
                func.coalesce(func.sum(Order.price_brl), 0.0).label("brl"),
            ).where(
                Order.status == OrderStatus.DELIVERED.value,
                Order.delivered_at >= today,
            )
        )
        row = result.first()
        return {"robux": int(row.robux or 0), "brl": float(row.brl or 0.0)}


# ══════════════════════════════════════════════════════════════════
# HELPER: embed do painel principal (para botão voltar)
# ══════════════════════════════════════════════════════════════════

async def build_config_main_embed() -> discord.Embed:
    settings = get_settings()
    mode = await DynamicConfig.operation_mode()
    price = await DynamicConfig.price_per_1000()
    mode_labels = {"auto": "🤖 Automático", "semi_auto": "⚡ Semi-Automático", "manual": "👤 Manual"}
    embed = discord.Embed(
        title="⚙️ Painel de Configuração",
        description="Bem-vindo ao painel central de configurações!\nUse o menu abaixo para navegar entre as seções.\n\n**Configurações atuais:**",
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="🤖 Modo", value=mode_labels.get(mode, mode), inline=True)
    embed.add_field(name="💵 Preço/1k R$", value=f"R$ {price/100:.2f}", inline=True)
    embed.add_field(name="📉 Mínimo", value=f"{await DynamicConfig.min_robux():,} R$", inline=True)
    embed.add_field(name="📈 Máximo", value=f"{await DynamicConfig.max_robux():,} R$", inline=True)
    daily_robux = await DynamicConfig.daily_limit_robux()
    embed.add_field(name="🗓️ Limite Diário", value=f"{daily_robux:,} R$" if daily_robux else "Sem limite", inline=True)
    embed.add_field(name="💎 Estoque Visível", value="✅ Sim" if await DynamicConfig.robux_stock_display() else "❌ Não", inline=True)
    return embed


# ══════════════════════════════════════════════════════════════════
# PAINEL PRINCIPAL
# ══════════════════════════════════════════════════════════════════

class ConfigMainView(ui.View):
    """View principal do painel /config."""

    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=300)
        self.bot = bot

    @ui.select(
        placeholder="📋 Escolha uma seção para configurar...",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(label="🤖 Modo de Operação", value="mode",
                                 description="Automático, Semi-automático ou Manual"),
            discord.SelectOption(label="💳 Pix Manual", value="pix",
                                 description="Chave Pix para pagamento manual"),
            discord.SelectOption(label="💰 Preços & Limites", value="prices",
                                 description="Preço/Robux, mínimo, máximo, limite diário"),
            discord.SelectOption(label="📢 Canais", value="channels",
                                 description="Vendas, Logs, Pedidos, Categoria Tickets"),
            discord.SelectOption(label="👥 Cargos", value="roles",
                                 description="Admin, Cliente, VIP"),
            discord.SelectOption(label="🎨 Embed da Loja", value="shop_embed",
                                 description="Título, descrição, cor, banner, autor, fields"),
            discord.SelectOption(label="🎫 Embed do Ticket", value="ticket_embed",
                                 description="Mensagem de boas-vindas do ticket"),
            discord.SelectOption(label="💎 Estoque de Robux", value="stock",
                                 description="Exibir saldo e configurar aviso de estoque baixo"),
            discord.SelectOption(label="📊 Resumo Geral", value="summary",
                                 description="Ver todas as configurações atuais"),
        ],
        custom_id="config:section_select",
    )
    async def section_select(self, interaction: discord.Interaction, select: ui.Select):
        section = select.values[0]
        if section == "mode":
            await interaction.response.send_message(
                embed=await build_mode_embed(), view=ModeView(self.bot), ephemeral=True
            )
        elif section == "pix":
            await interaction.response.send_message(
                embed=await build_pix_embed(), view=PixView(self.bot), ephemeral=True
            )
        elif section == "prices":
            await interaction.response.send_message(
                embed=await build_prices_embed(), view=PricesView(self.bot), ephemeral=True
            )
        elif section == "channels":
            await interaction.response.send_message(
                embed=await build_channels_embed(interaction.guild),
                view=ChannelsView(self.bot), ephemeral=True
            )
        elif section == "roles":
            await interaction.response.send_message(
                embed=await build_roles_embed(interaction.guild),
                view=RolesView(self.bot), ephemeral=True
            )
        elif section == "shop_embed":
            await interaction.response.send_message(
                embed=await build_shop_embed_config_embed(),
                view=ShopEmbedView(self.bot), ephemeral=True
            )
        elif section == "ticket_embed":
            await interaction.response.send_message(
                embed=await build_ticket_embed_config_embed(),
                view=TicketEmbedView(self.bot), ephemeral=True
            )
        elif section == "stock":
            await interaction.response.send_message(
                embed=await build_stock_embed(self.bot),
                view=StockView(self.bot), ephemeral=True
            )
        elif section == "summary":
            await interaction.response.send_message(
                embed=await build_summary_embed(interaction.guild),
                ephemeral=True
            )


# ══════════════════════════════════════════════════════════════════
# SEÇÃO: MODO DE OPERAÇÃO
# ══════════════════════════════════════════════════════════════════

async def build_mode_embed() -> discord.Embed:
    mode = await DynamicConfig.operation_mode()
    mode_labels = {
        "auto": "🤖 Automático",
        "semi_auto": "⚡ Semi-Automático",
        "manual": "👤 Manual",
    }
    mode_descs = {
        "auto": "Bot gera PIX **e** entrega os Robux automaticamente após pagamento confirmado.",
        "semi_auto": "Bot gera PIX automaticamente. Admin precisa **confirmar** a entrega manualmente.",
        "manual": "Tudo manual. Bot apenas cria o ticket. Admin faz o atendimento completo.",
    }
    embed = discord.Embed(
        title="🤖 Modo de Operação",
        description=(
            f"**Modo atual:** {mode_labels.get(mode, mode)}\n\n"
            f"📝 {mode_descs.get(mode, '')}\n\n"
            "Escolha abaixo o modo desejado:"
        ),
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="🤖 Automático",
        value="PIX gerado + entrega automática.\nZero intervenção humana.",
        inline=True,
    )
    embed.add_field(
        name="⚡ Semi-Automático",
        value="PIX gerado automaticamente.\nAdmin confirma a entrega.",
        inline=True,
    )
    embed.add_field(
        name="👤 Manual",
        value="Tudo feito pelo admin.\nBot só abre o ticket.",
        inline=True,
    )
    return embed


class ModeView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=180)
        self.bot = bot

    @ui.button(label="🤖 Automático", style=discord.ButtonStyle.green, custom_id="cfg:mode_auto", row=0)
    async def mode_auto(self, interaction: discord.Interaction, button: ui.Button):
        await DynamicConfig.set("operation_mode", "auto", updated_by=interaction.user.id)
        await interaction.response.edit_message(embed=await build_mode_embed(), view=self)
        await LogRepository.log("config_changed", interaction.user.id, details={"key": "operation_mode", "value": "auto"})
        await interaction.followup.send("✅ Modo **Automático** ativado!", ephemeral=True)

    @ui.button(label="⚡ Semi-Automático", style=discord.ButtonStyle.blurple, custom_id="cfg:mode_semi", row=0)
    async def mode_semi(self, interaction: discord.Interaction, button: ui.Button):
        await DynamicConfig.set("operation_mode", "semi_auto", updated_by=interaction.user.id)
        await interaction.response.edit_message(embed=await build_mode_embed(), view=self)
        await LogRepository.log("config_changed", interaction.user.id, details={"key": "operation_mode", "value": "semi_auto"})
        await interaction.followup.send("✅ Modo **Semi-Automático** ativado!", ephemeral=True)

    @ui.button(label="👤 Manual", style=discord.ButtonStyle.danger, custom_id="cfg:mode_manual", row=0)
    async def mode_manual(self, interaction: discord.Interaction, button: ui.Button):
        await DynamicConfig.set("operation_mode", "manual", updated_by=interaction.user.id)
        await interaction.response.edit_message(embed=await build_mode_embed(), view=self)
        await LogRepository.log("config_changed", interaction.user.id, details={"key": "operation_mode", "value": "manual"})
        await interaction.followup.send("✅ Modo **Manual** ativado!", ephemeral=True)

    @ui.button(label="⬅️ Voltar", style=discord.ButtonStyle.secondary, custom_id="cfg:mode_back", row=1)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(embed=await build_config_main_embed(), view=ConfigMainView(self.bot))


# ══════════════════════════════════════════════════════════════════
# SEÇÃO: PREÇOS & LIMITES
# ══════════════════════════════════════════════════════════════════

async def build_prices_embed() -> discord.Embed:
    price = await DynamicConfig.price_per_1000()
    min_r = await DynamicConfig.min_robux()
    max_r = await DynamicConfig.max_robux()
    daily_robux = await DynamicConfig.daily_limit_robux()
    daily_brl = await DynamicConfig.daily_limit_brl()

    price_reais = price / 100
    embed = discord.Embed(
        title="💰 Preços & Limites",
        color=discord.Color.gold(),
    )
    embed.add_field(name="💵 Preço por 1.000 Robux", value=f"R$ **{price_reais:.2f}**", inline=True)
    embed.add_field(name="📉 Mínimo por compra", value=f"**{min_r:,}** Robux", inline=True)
    embed.add_field(name="📈 Máximo por compra", value=f"**{max_r:,}** Robux", inline=True)
    embed.add_field(
        name="🗓️ Limite diário (Robux)",
        value=f"**{daily_robux:,}**" if daily_robux else "**Sem limite**",
        inline=True,
    )
    embed.add_field(
        name="🗓️ Limite diário (R$)",
        value=f"R$ **{daily_brl:.2f}**" if daily_brl else "**Sem limite**",
        inline=True,
    )

    # Exemplos de preço
    examples = [100, 500, 1000, 2000, 5000]
    table = ""
    for robux in examples:
        p = robux * (price / 100) / 1000
        table += f"**{robux:,}** R$ → `R$ {p:.2f}`\n"
    embed.add_field(name="📊 Tabela de Preços", value=table, inline=False)
    return embed


class PricesView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=180)
        self.bot = bot

    @ui.button(label="✏️ Editar Preços", style=discord.ButtonStyle.blurple, row=0)
    async def edit_prices(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(PricesModal())

    @ui.button(label="🗓️ Limite Diário", style=discord.ButtonStyle.gray, row=0)
    async def edit_daily(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(DailyLimitModal())

    @ui.button(label="🗑️ Remover Limite Diário", style=discord.ButtonStyle.danger, row=0)
    async def remove_daily(self, interaction: discord.Interaction, button: ui.Button):
        await DynamicConfig.delete("daily_limit_robux")
        await DynamicConfig.delete("daily_limit_brl")
        await interaction.response.edit_message(embed=await build_prices_embed(), view=self)
        await interaction.followup.send("✅ Limite diário removido!", ephemeral=True)

    @ui.button(label="⬅️ Voltar", style=discord.ButtonStyle.secondary, custom_id="cfg:prices_back", row=1)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(embed=await build_config_main_embed(), view=ConfigMainView(self.bot))


class PricesModal(ui.Modal, title="💰 Configurar Preços"):
    preco = ui.TextInput(
        label="Preço por 1.000 Robux (em R$, ex: 15.00)",
        placeholder="15.00",
        required=True,
        max_length=10,
    )
    minimo = ui.TextInput(
        label="Mínimo de Robux por compra",
        placeholder="100",
        required=True,
        max_length=10,
    )
    maximo = ui.TextInput(
        label="Máximo de Robux por compra",
        placeholder="100000",
        required=True,
        max_length=10,
    )

    async def on_submit(self, interaction: discord.Interaction):
        errors = []
        try:
            price_reais = float(self.preco.value.replace(",", "."))
            price_cents = int(price_reais * 100)
            if price_cents <= 0:
                raise ValueError
        except Exception:
            errors.append("❌ Preço inválido. Use formato como `15.00`")

        try:
            min_r = int(self.minimo.value.replace(".", "").replace(",", ""))
            if min_r < 1:
                raise ValueError
        except Exception:
            errors.append("❌ Mínimo inválido.")

        try:
            max_r = int(self.maximo.value.replace(".", "").replace(",", ""))
            if max_r < 1:
                raise ValueError
        except Exception:
            errors.append("❌ Máximo inválido.")

        if errors:
            await interaction.response.send_message("\n".join(errors), ephemeral=True)
            return

        await DynamicConfig.set("price_per_1000_robux", price_cents, updated_by=interaction.user.id)
        await DynamicConfig.set("min_robux_amount", min_r, updated_by=interaction.user.id)
        await DynamicConfig.set("max_robux_amount", max_r, updated_by=interaction.user.id)

        await LogRepository.log("config_changed", interaction.user.id, details={
            "price_per_1000_robux": price_cents, "min": min_r, "max": max_r
        })
        await interaction.response.send_message(
            f"✅ Preços atualizados!\n"
            f"• R$ {price_reais:.2f} / 1.000 R$\n"
            f"• Mínimo: {min_r:,} | Máximo: {max_r:,}",
            ephemeral=True,
        )


class DailyLimitModal(ui.Modal, title="🗓️ Limite Diário de Vendas"):
    limit_robux = ui.TextInput(
        label="Limite de Robux por dia (0 = sem limite)",
        placeholder="50000",
        required=True,
        max_length=10,
    )
    limit_brl = ui.TextInput(
        label="Limite em R$ por dia (0 = sem limite)",
        placeholder="500.00",
        required=True,
        max_length=10,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            lr = int(self.limit_robux.value.replace(".", "").replace(",", ""))
            lb = float(self.limit_brl.value.replace(",", "."))
        except Exception:
            await interaction.response.send_message("❌ Valores inválidos.", ephemeral=True)
            return

        if lr > 0:
            await DynamicConfig.set("daily_limit_robux", lr, updated_by=interaction.user.id)
        else:
            await DynamicConfig.delete("daily_limit_robux")

        if lb > 0:
            await DynamicConfig.set("daily_limit_brl", lb, updated_by=interaction.user.id)
        else:
            await DynamicConfig.delete("daily_limit_brl")

        await LogRepository.log("config_changed", interaction.user.id,
                                details={"daily_limit_robux": lr, "daily_limit_brl": lb})
        msg = "✅ Limite diário atualizado!\n"
        msg += f"• Robux: {lr:,}" if lr > 0 else "• Robux: sem limite"
        msg += f"\n• R$: {lb:.2f}" if lb > 0 else "\n• R$: sem limite"
        await interaction.response.send_message(msg, ephemeral=True)


# ══════════════════════════════════════════════════════════════════
# SEÇÃO: CANAIS
# ══════════════════════════════════════════════════════════════════

async def build_channels_embed(guild: discord.Guild) -> discord.Embed:
    settings = get_settings()
    vendas_id = await DynamicConfig.channel_vendas_id() or settings.channel_vendas_id
    logs_id = await DynamicConfig.channel_logs_id() or settings.channel_logs_id
    pedidos_id = await DynamicConfig.channel_pedidos_id() or settings.channel_pedidos_id
    cat_id = await DynamicConfig.category_tickets_id() or settings.category_tickets_id

    def ch_mention(cid):
        if not cid:
            return "❌ Não configurado"
        ch = guild.get_channel(cid) if guild else None
        return ch.mention if ch else f"`{cid}` (não encontrado)"

    embed = discord.Embed(title="📢 Configuração de Canais", color=discord.Color.blue())
    embed.add_field(name="🛒 Canal de Vendas", value=ch_mention(vendas_id), inline=True)
    embed.add_field(name="📋 Canal de Logs", value=ch_mention(logs_id), inline=True)
    embed.add_field(name="📦 Canal de Pedidos", value=ch_mention(pedidos_id), inline=True)
    embed.add_field(name="🗂️ Categoria Tickets", value=ch_mention(cat_id), inline=True)
    embed.set_footer(text="Use os seletores abaixo para alterar cada canal.")
    return embed


class ChannelsView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=180)
        self.bot = bot

    @ui.select(
        cls=ui.ChannelSelect,
        placeholder="🛒 Canal de Vendas",
        channel_types=[discord.ChannelType.text],
        min_values=1, max_values=1,
        custom_id="cfg:ch_vendas",
    )
    async def ch_vendas(self, interaction: discord.Interaction, select: ui.ChannelSelect):
        ch = select.values[0]
        await DynamicConfig.set("channel_vendas_id", ch.id, updated_by=interaction.user.id)
        await interaction.response.edit_message(
            embed=await build_channels_embed(interaction.guild), view=self
        )
        await interaction.followup.send(f"✅ Canal de Vendas → {ch.mention}", ephemeral=True)

    @ui.select(
        cls=ui.ChannelSelect,
        placeholder="📋 Canal de Logs",
        channel_types=[discord.ChannelType.text],
        min_values=1, max_values=1,
        custom_id="cfg:ch_logs",
    )
    async def ch_logs(self, interaction: discord.Interaction, select: ui.ChannelSelect):
        ch = select.values[0]
        await DynamicConfig.set("channel_logs_id", ch.id, updated_by=interaction.user.id)
        await interaction.response.edit_message(
            embed=await build_channels_embed(interaction.guild), view=self
        )
        await interaction.followup.send(f"✅ Canal de Logs → {ch.mention}", ephemeral=True)

    @ui.select(
        cls=ui.ChannelSelect,
        placeholder="📦 Canal de Pedidos",
        channel_types=[discord.ChannelType.text],
        min_values=1, max_values=1,
        custom_id="cfg:ch_pedidos",
    )
    async def ch_pedidos(self, interaction: discord.Interaction, select: ui.ChannelSelect):
        ch = select.values[0]
        await DynamicConfig.set("channel_pedidos_id", ch.id, updated_by=interaction.user.id)
        await interaction.response.edit_message(
            embed=await build_channels_embed(interaction.guild), view=self
        )
        await interaction.followup.send(f"✅ Canal de Pedidos → {ch.mention}", ephemeral=True)

    @ui.select(
        cls=ui.ChannelSelect,
        placeholder="🗂️ Categoria de Tickets",
        channel_types=[discord.ChannelType.category],
        min_values=1, max_values=1,
        custom_id="cfg:ch_category",
    )
    async def ch_category(self, interaction: discord.Interaction, select: ui.ChannelSelect):
        ch = select.values[0]
        await DynamicConfig.set("category_tickets_id", ch.id, updated_by=interaction.user.id)
        await interaction.response.edit_message(
            embed=await build_channels_embed(interaction.guild), view=self
        )
        await interaction.followup.send(f"✅ Categoria de Tickets → **{ch.name}**", ephemeral=True)

    @ui.button(label="⬅️ Voltar", style=discord.ButtonStyle.secondary, custom_id="cfg:ch_back", row=1)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(embed=await build_config_main_embed(), view=ConfigMainView(self.bot))


# ══════════════════════════════════════════════════════════════════
# SEÇÃO: CARGOS
# ══════════════════════════════════════════════════════════════════

async def build_roles_embed(guild: discord.Guild) -> discord.Embed:
    settings = get_settings()
    admin_id = await DynamicConfig.role_admin_id() or settings.role_admin_id
    cliente_id = await DynamicConfig.role_cliente_id() or settings.role_cliente_id
    vip_id = await DynamicConfig.role_vip_id() or settings.role_vip_id

    def role_mention(rid):
        if not rid:
            return "❌ Não configurado"
        r = guild.get_role(rid) if guild else None
        return r.mention if r else f"`{rid}` (não encontrado)"

    embed = discord.Embed(title="👥 Configuração de Cargos", color=discord.Color.purple())
    embed.add_field(name="🔑 Cargo Admin", value=role_mention(admin_id), inline=True)
    embed.add_field(name="👤 Cargo Cliente", value=role_mention(cliente_id), inline=True)
    embed.add_field(name="⭐ Cargo VIP", value=role_mention(vip_id), inline=True)
    embed.set_footer(text="Use os seletores abaixo para alterar cada cargo.")
    return embed


class RolesView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=180)
        self.bot = bot

    @ui.select(
        cls=ui.RoleSelect,
        placeholder="🔑 Cargo Admin",
        min_values=1, max_values=1,
        custom_id="cfg:role_admin",
    )
    async def role_admin(self, interaction: discord.Interaction, select: ui.RoleSelect):
        role = select.values[0]
        await DynamicConfig.set("role_admin_id", role.id, updated_by=interaction.user.id)
        await interaction.response.edit_message(
            embed=await build_roles_embed(interaction.guild), view=self
        )
        await interaction.followup.send(f"✅ Cargo Admin → {role.mention}", ephemeral=True)

    @ui.select(
        cls=ui.RoleSelect,
        placeholder="👤 Cargo Cliente",
        min_values=1, max_values=1,
        custom_id="cfg:role_cliente",
    )
    async def role_cliente(self, interaction: discord.Interaction, select: ui.RoleSelect):
        role = select.values[0]
        await DynamicConfig.set("role_cliente_id", role.id, updated_by=interaction.user.id)
        await interaction.response.edit_message(
            embed=await build_roles_embed(interaction.guild), view=self
        )
        await interaction.followup.send(f"✅ Cargo Cliente → {role.mention}", ephemeral=True)

    @ui.select(
        cls=ui.RoleSelect,
        placeholder="⭐ Cargo VIP",
        min_values=1, max_values=1,
        custom_id="cfg:role_vip",
    )
    async def role_vip(self, interaction: discord.Interaction, select: ui.RoleSelect):
        role = select.values[0]
        await DynamicConfig.set("role_vip_id", role.id, updated_by=interaction.user.id)
        await interaction.response.edit_message(
            embed=await build_roles_embed(interaction.guild), view=self
        )
        await interaction.followup.send(f"✅ Cargo VIP → {role.mention}", ephemeral=True)

    @ui.button(label="⬅️ Voltar", style=discord.ButtonStyle.secondary, custom_id="cfg:roles_back", row=1)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(embed=await build_config_main_embed(), view=ConfigMainView(self.bot))


# ══════════════════════════════════════════════════════════════════
# SEÇÃO: EMBED DA LOJA
# ══════════════════════════════════════════════════════════════════

async def build_shop_embed_config_embed() -> discord.Embed:
    cfg = await DynamicConfig.shop_embed()
    color = cfg.get("color", 0x00D166)
    fields = cfg.get("fields", [])
    embed = discord.Embed(
        title="🎨 Embed da Loja — Configurações",
        color=color,
    )
    embed.add_field(name="📌 Título", value=cfg.get("title", "*(padrão)*")[:60], inline=True)
    embed.add_field(name="🎨 Cor", value=f"`#{color:06X}`", inline=True)
    embed.add_field(name="📝 Descrição", value=(cfg.get("description", "*(padrão)*")[:80] + "...") if len(cfg.get("description",""))>80 else cfg.get("description","*(padrão)*"), inline=False)
    embed.add_field(name="👤 Autor", value=cfg.get("author_name", "*(não definido)*") or "*(não definido)*", inline=True)
    embed.add_field(name="🖼️ Banner", value="✅ Definido" if cfg.get("banner_url") else "❌ Não definido", inline=True)
    embed.add_field(name="🖼️ Thumbnail", value="✅ Definida" if cfg.get("thumbnail_url") else "❌ Não definida", inline=True)
    embed.add_field(name="📋 Fields", value=f"{len(fields)} field(s) configurado(s)", inline=True)
    embed.add_field(name="📎 Rodapé", value=cfg.get("footer", "*(não definido)*")[:60] or "*(não definido)*", inline=True)
    embed.set_footer(text="Use os botões abaixo para editar cada parte. '⬅️ Voltar' volta ao menu.")
    return embed


class ShopEmbedView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=180)
        self.bot = bot

    @ui.button(label="✏️ Texto & Rodapé", style=discord.ButtonStyle.blurple, row=0)
    async def edit_text(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ShopEmbedTextModal())

    @ui.button(label="🎨 Cor & Imagens", style=discord.ButtonStyle.gray, row=0)
    async def edit_style(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ShopEmbedStyleModal())

    @ui.button(label="👤 Autor & URL", style=discord.ButtonStyle.gray, row=0)
    async def edit_author(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ShopEmbedAuthorModal())

    @ui.button(label="📋 Fields", style=discord.ButtonStyle.gray, row=0)
    async def edit_fields(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ShopEmbedFieldsModal())

    @ui.button(label="👁️ Pré-visualizar", style=discord.ButtonStyle.green, row=1)
    async def preview(self, interaction: discord.Interaction, button: ui.Button):
        cfg = await DynamicConfig.shop_embed()
        color = cfg.get("color", 0x00D166)
        price = await DynamicConfig.price_per_1000()
        price_reais = price / 100
        preview_embed = discord.Embed(
            title=cfg.get("title", "🏪 Loja de Robux"),
            description=cfg.get("description", ""),
            color=color,
        )
        if cfg.get("author_name"):
            preview_embed.set_author(
                name=cfg["author_name"],
                icon_url=cfg.get("author_icon_url") or discord.Embed.Empty,
                url=cfg.get("author_url") or discord.Embed.Empty,
            )
        if cfg.get("title_url"):
            preview_embed.url = cfg["title_url"]
        preview_embed.add_field(name="💰 Preço", value=f"R$ {price_reais:.2f} / 1.000 R$", inline=True)
        preview_embed.add_field(name="⚡ Entrega", value="Instantânea", inline=True)
        preview_embed.add_field(name="💳 Pagamento", value="PIX", inline=True)
        for f in cfg.get("fields", []):
            preview_embed.add_field(name=f.get("name",""), value=f.get("value",""), inline=f.get("inline", True))
        if cfg.get("banner_url"):
            preview_embed.set_image(url=cfg["banner_url"])
        if cfg.get("thumbnail_url"):
            preview_embed.set_thumbnail(url=cfg["thumbnail_url"])
        if cfg.get("footer") or cfg.get("footer_icon_url"):
            preview_embed.set_footer(text=cfg.get("footer",""), icon_url=cfg.get("footer_icon_url") or discord.Embed.Empty)
        await interaction.response.send_message(
            content="**📋 Pré-visualização da embed da loja:**",
            embed=preview_embed, ephemeral=True
        )

    @ui.button(label="🔄 Aplicar ao Painel", style=discord.ButtonStyle.green, row=1)
    async def apply_to_panel(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        from src.cogs.tickets import setup_ticket_panel
        settings = get_settings()
        vendas_id = await DynamicConfig.channel_vendas_id() or settings.channel_vendas_id
        channel = interaction.guild.get_channel(vendas_id)
        if channel:
            async for msg in channel.history(limit=15):
                if msg.author == interaction.client.user and msg.embeds:
                    await msg.delete()
                    break
        await setup_ticket_panel(interaction.client)
        await interaction.followup.send("✅ Painel da loja atualizado!", ephemeral=True)

    @ui.button(label="⬅️ Voltar", style=discord.ButtonStyle.secondary, custom_id="cfg:shop_back", row=2)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(embed=await build_config_main_embed(), view=ConfigMainView(self.bot))


class ShopEmbedTextModal(ui.Modal, title="🎨 Texto & Rodapé da Embed da Loja"):
    titulo = ui.TextInput(label="Título", placeholder="🏪 Loja Oficial de Robux", max_length=256, required=True)
    titulo_url = ui.TextInput(label="URL do Título (clicável, opcional)", placeholder="https://...", max_length=500, required=False)
    descricao = ui.TextInput(label="Descrição", style=discord.TextStyle.paragraph, placeholder="Compre Robux de forma rápida e segura!", max_length=2000, required=True)
    rodape = ui.TextInput(label="Rodapé", placeholder="🕐 Atendimento 24/7 • ⭐ +1000 clientes satisfeitos", max_length=200, required=False)
    rodape_icon = ui.TextInput(label="URL do Ícone do Rodapé (opcional)", placeholder="https://i.imgur.com/...", max_length=500, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = await DynamicConfig.shop_embed()
        cfg["title"] = self.titulo.value
        cfg["title_url"] = self.titulo_url.value or ""
        cfg["description"] = self.descricao.value
        cfg["footer"] = self.rodape.value
        cfg["footer_icon_url"] = self.rodape_icon.value or ""
        await DynamicConfig.set("shop_embed", cfg, updated_by=interaction.user.id)
        await LogRepository.log("config_changed", interaction.user.id, details={"section": "shop_embed_text"})
        await interaction.response.send_message("✅ Texto da embed da loja atualizado! Use **🔄 Aplicar ao Painel** para publicar.", ephemeral=True)


class ShopEmbedStyleModal(ui.Modal, title="🎨 Cor & Imagens da Embed da Loja"):
    cor = ui.TextInput(label="Cor (HEX, ex: #00D166)", placeholder="#00D166", max_length=10, required=False)
    banner = ui.TextInput(label="URL do Banner (imagem grande abaixo)", placeholder="https://i.imgur.com/...", max_length=500, required=False)
    thumbnail = ui.TextInput(label="URL da Thumbnail (ícone pequeno no canto)", placeholder="https://i.imgur.com/...", max_length=500, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = await DynamicConfig.shop_embed()
        if self.cor.value:
            cfg["color"] = color_from_hex(self.cor.value)
        if self.banner.value:
            cfg["banner_url"] = self.banner.value
        if self.thumbnail.value:
            cfg["thumbnail_url"] = self.thumbnail.value
        await DynamicConfig.set("shop_embed", cfg, updated_by=interaction.user.id)
        await LogRepository.log("config_changed", interaction.user.id, details={"section": "shop_embed_style"})
        await interaction.response.send_message("✅ Estilo da embed atualizado! Use **🔄 Aplicar ao Painel** para publicar.", ephemeral=True)


class ShopEmbedAuthorModal(ui.Modal, title="👤 Autor da Embed da Loja"):
    author_name = ui.TextInput(label="Nome do Autor (deixe vazio para remover)", placeholder="Ex: Loja Oficial de Robux", max_length=256, required=False)
    author_icon = ui.TextInput(label="URL do Ícone do Autor (opcional)", placeholder="https://i.imgur.com/...", max_length=500, required=False)
    author_url = ui.TextInput(label="URL do Autor (clicável, opcional)", placeholder="https://...", max_length=500, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = await DynamicConfig.shop_embed()
        cfg["author_name"] = self.author_name.value
        cfg["author_icon_url"] = self.author_icon.value or ""
        cfg["author_url"] = self.author_url.value or ""
        await DynamicConfig.set("shop_embed", cfg, updated_by=interaction.user.id)
        await LogRepository.log("config_changed", interaction.user.id, details={"section": "shop_embed_author"})
        await interaction.response.send_message("✅ Autor da embed atualizado! Use **🔄 Aplicar ao Painel** para publicar.", ephemeral=True)


class ShopEmbedFieldsModal(ui.Modal, title="📋 Fields da Embed da Loja"):
    f1_name = ui.TextInput(label="Field 1 — Nome", placeholder="Ex: 🔒 Segurança", max_length=256, required=False)
    f1_value = ui.TextInput(label="Field 1 — Valor", placeholder="Ex: 100% seguro via Gamepass", max_length=1024, required=False)
    f2_name = ui.TextInput(label="Field 2 — Nome", placeholder="Ex: ⚡ Entrega", max_length=256, required=False)
    f2_value = ui.TextInput(label="Field 2 — Valor", placeholder="Ex: Instantânea após PIX", max_length=1024, required=False)
    f3_name = ui.TextInput(label="Field 3 — Nome (ou 'LIMPAR' para apagar todos)", placeholder="Ex: 💎 Estoque", max_length=256, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = await DynamicConfig.shop_embed()
        if self.f3_name.value.strip().upper() == "LIMPAR":
            cfg["fields"] = []
            await DynamicConfig.set("shop_embed", cfg, updated_by=interaction.user.id)
            await interaction.response.send_message("✅ Todos os fields removidos!", ephemeral=True)
            return
        fields = []
        if self.f1_name.value and self.f1_value.value:
            fields.append({"name": self.f1_name.value, "value": self.f1_value.value, "inline": True})
        if self.f2_name.value and self.f2_value.value:
            fields.append({"name": self.f2_name.value, "value": self.f2_value.value, "inline": True})
        if self.f3_name.value and self.f3_name.value.upper() != "LIMPAR":
            fields.append({"name": self.f3_name.value, "value": "(sem valor)", "inline": True})
        cfg["fields"] = fields
        await DynamicConfig.set("shop_embed", cfg, updated_by=interaction.user.id)
        await LogRepository.log("config_changed", interaction.user.id, details={"section": "shop_embed_fields"})
        await interaction.response.send_message(f"✅ {len(fields)} field(s) configurado(s)! Use **🔄 Aplicar ao Painel** para publicar.", ephemeral=True)


# ══════════════════════════════════════════════════════════════════
# SEÇÃO: EMBED DO TICKET
# ══════════════════════════════════════════════════════════════════

async def build_ticket_embed_config_embed() -> discord.Embed:
    cfg = await DynamicConfig.ticket_embed()
    color = cfg.get("color", 0x5865F2)
    fields = cfg.get("fields", [])
    embed = discord.Embed(title="🎫 Embed do Ticket — Configurações", color=color)
    embed.add_field(name="📌 Título", value=cfg.get("title", "*(padrão)*")[:60], inline=True)
    embed.add_field(name="🎨 Cor", value=f"`#{color:06X}`", inline=True)
    embed.add_field(name="📝 Descrição", value=(cfg.get("description","*(padrão)*")[:80]+"...") if len(cfg.get("description",""))>80 else cfg.get("description","*(padrão)*"), inline=False)
    embed.add_field(name="👤 Autor", value=cfg.get("author_name","*(não definido)*") or "*(não definido)*", inline=True)
    embed.add_field(name="🖼️ Banner", value="✅ Definido" if cfg.get("banner_url") else "❌ Não definido", inline=True)
    embed.add_field(name="📋 Fields", value=f"{len(fields)} field(s)", inline=True)
    embed.add_field(name="💰 Tabela de Preços", value="✅ Ativada" if cfg.get("show_price_table", True) else "❌ Desativada", inline=True)
    embed.add_field(name="📋 Passos de Compra", value="✅ Ativados" if cfg.get("show_steps", True) else "❌ Desativados", inline=True)
    embed.set_footer(text="Use {mention} na descrição para mencionar o usuário.")
    return embed


class TicketEmbedView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=180)
        self.bot = bot

    @ui.button(label="✏️ Texto & Rodapé", style=discord.ButtonStyle.blurple, row=0)
    async def edit_text(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(TicketEmbedTextModal())

    @ui.button(label="🎨 Cor & Imagens", style=discord.ButtonStyle.gray, row=0)
    async def edit_style(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(TicketEmbedStyleModal())

    @ui.button(label="👤 Autor & URL", style=discord.ButtonStyle.gray, row=0)
    async def edit_author(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(TicketEmbedAuthorModal())

    @ui.button(label="📋 Fields", style=discord.ButtonStyle.gray, row=0)
    async def edit_fields(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(TicketEmbedFieldsModal())

    @ui.button(label="🔁 Tabela de Preços", style=discord.ButtonStyle.green, row=1)
    async def toggle_price_table(self, interaction: discord.Interaction, button: ui.Button):
        cfg = await DynamicConfig.ticket_embed()
        cfg["show_price_table"] = not cfg.get("show_price_table", True)
        await DynamicConfig.set("ticket_embed", cfg, updated_by=interaction.user.id)
        await interaction.response.edit_message(embed=await build_ticket_embed_config_embed(), view=self)

    @ui.button(label="🔁 Passos de Compra", style=discord.ButtonStyle.green, row=1)
    async def toggle_steps(self, interaction: discord.Interaction, button: ui.Button):
        cfg = await DynamicConfig.ticket_embed()
        cfg["show_steps"] = not cfg.get("show_steps", True)
        await DynamicConfig.set("ticket_embed", cfg, updated_by=interaction.user.id)
        await interaction.response.edit_message(embed=await build_ticket_embed_config_embed(), view=self)

    @ui.button(label="⬅️ Voltar", style=discord.ButtonStyle.secondary, custom_id="cfg:ticket_embed_back", row=2)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(embed=await build_config_main_embed(), view=ConfigMainView(self.bot))


class TicketEmbedTextModal(ui.Modal, title="🎫 Texto & Rodapé do Ticket"):
    titulo = ui.TextInput(label="Título do Ticket", placeholder="🛒 Bem-vindo à Loja de Robux!", max_length=256, required=True)
    titulo_url = ui.TextInput(label="URL do Título (clicável, opcional)", placeholder="https://...", max_length=500, required=False)
    descricao = ui.TextInput(label="Descrição (use {mention})", style=discord.TextStyle.paragraph, placeholder="Olá {mention}! 👋\n\nBem-vindo à nossa loja!", max_length=2000, required=True)
    rodape = ui.TextInput(label="Rodapé", placeholder="Atendimento 24/7", max_length=200, required=False)
    rodape_icon = ui.TextInput(label="URL do Ícone do Rodapé (opcional)", placeholder="https://i.imgur.com/...", max_length=500, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = await DynamicConfig.ticket_embed()
        cfg["title"] = self.titulo.value
        cfg["title_url"] = self.titulo_url.value or ""
        cfg["description"] = self.descricao.value
        cfg["footer"] = self.rodape.value
        cfg["footer_icon_url"] = self.rodape_icon.value or ""
        await DynamicConfig.set("ticket_embed", cfg, updated_by=interaction.user.id)
        await LogRepository.log("config_changed", interaction.user.id, details={"section": "ticket_embed_text"})
        await interaction.response.send_message("✅ Texto da embed do ticket atualizado!", ephemeral=True)


class TicketEmbedStyleModal(ui.Modal, title="🎨 Cor & Imagens do Ticket"):
    cor = ui.TextInput(label="Cor (HEX, ex: #5865F2)", placeholder="#5865F2", max_length=10, required=False)
    banner = ui.TextInput(label="URL do Banner (imagem grande)", placeholder="https://i.imgur.com/...", max_length=500, required=False)
    thumbnail = ui.TextInput(label="URL da Thumbnail (ícone pequeno)", placeholder="https://i.imgur.com/...", max_length=500, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = await DynamicConfig.ticket_embed()
        if self.cor.value:
            cfg["color"] = color_from_hex(self.cor.value)
        if self.banner.value:
            cfg["banner_url"] = self.banner.value
        if self.thumbnail.value:
            cfg["thumbnail_url"] = self.thumbnail.value
        await DynamicConfig.set("ticket_embed", cfg, updated_by=interaction.user.id)
        await interaction.response.send_message("✅ Estilo do ticket atualizado!", ephemeral=True)


class TicketEmbedAuthorModal(ui.Modal, title="👤 Autor da Embed do Ticket"):
    author_name = ui.TextInput(label="Nome do Autor (deixe vazio para remover)", placeholder="Ex: Suporte da Loja", max_length=256, required=False)
    author_icon = ui.TextInput(label="URL do Ícone do Autor (opcional)", placeholder="https://i.imgur.com/...", max_length=500, required=False)
    author_url = ui.TextInput(label="URL do Autor (clicável, opcional)", placeholder="https://...", max_length=500, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = await DynamicConfig.ticket_embed()
        cfg["author_name"] = self.author_name.value
        cfg["author_icon_url"] = self.author_icon.value or ""
        cfg["author_url"] = self.author_url.value or ""
        await DynamicConfig.set("ticket_embed", cfg, updated_by=interaction.user.id)
        await interaction.response.send_message("✅ Autor da embed do ticket atualizado!", ephemeral=True)


class TicketEmbedFieldsModal(ui.Modal, title="📋 Fields da Embed do Ticket"):
    f1_name = ui.TextInput(label="Field 1 — Nome", placeholder="Ex: 🔒 Segurança", max_length=256, required=False)
    f1_value = ui.TextInput(label="Field 1 — Valor", placeholder="Ex: 100% seguro via Gamepass", max_length=1024, required=False)
    f2_name = ui.TextInput(label="Field 2 — Nome", placeholder="Ex: ⚡ Entrega", max_length=256, required=False)
    f2_value = ui.TextInput(label="Field 2 — Valor", placeholder="Ex: Instantânea após PIX", max_length=1024, required=False)
    f3_name = ui.TextInput(label="Field 3 — Nome (ou 'LIMPAR' para apagar tudo)", placeholder="Ex: 💎 Estoque", max_length=256, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = await DynamicConfig.ticket_embed()
        if self.f3_name.value.strip().upper() == "LIMPAR":
            cfg["fields"] = []
            await DynamicConfig.set("ticket_embed", cfg, updated_by=interaction.user.id)
            await interaction.response.send_message("✅ Todos os fields removidos!", ephemeral=True)
            return
        fields = []
        if self.f1_name.value and self.f1_value.value:
            fields.append({"name": self.f1_name.value, "value": self.f1_value.value, "inline": True})
        if self.f2_name.value and self.f2_value.value:
            fields.append({"name": self.f2_name.value, "value": self.f2_value.value, "inline": True})
        if self.f3_name.value and self.f3_name.value.upper() != "LIMPAR":
            fields.append({"name": self.f3_name.value, "value": "(sem valor)", "inline": True})
        cfg["fields"] = fields
        await DynamicConfig.set("ticket_embed", cfg, updated_by=interaction.user.id)
        await interaction.response.send_message(f"✅ {len(fields)} field(s) configurado(s)!", ephemeral=True)


# ══════════════════════════════════════════════════════════════════
# SEÇÃO: ESTOQUE DE ROBUX
# ══════════════════════════════════════════════════════════════════

async def build_stock_embed(bot: commands.Bot) -> discord.Embed:
    display = await DynamicConfig.robux_stock_display()
    low_alert = await DynamicConfig.get("stock_low_alert") or 1000

    embed = discord.Embed(title="💎 Estoque de Robux", color=discord.Color.green())
    embed.add_field(
        name="👁️ Exibir no Painel",
        value="✅ Ativado" if display else "❌ Desativado",
        inline=True,
    )
    embed.add_field(
        name="⚠️ Alerta de Estoque Baixo",
        value=f"< **{int(low_alert):,}** Robux",
        inline=True,
    )

    # Tenta buscar saldo atual
    try:
        from src.services import roblox_api
        balance = await roblox_api.get_my_robux_balance()
        user_info = await roblox_api.get_authenticated_user()
        if balance is not None:
            status = "🟢 OK" if balance >= int(low_alert) else "🔴 BAIXO"
            embed.add_field(
                name="💰 Saldo Atual",
                value=f"**{balance:,} R$** {status}",
                inline=False,
            )
            if user_info:
                embed.add_field(name="👤 Conta Roblox", value=f"`{user_info.get('name')}`", inline=True)
        else:
            embed.add_field(name="💰 Saldo Atual", value="❌ Erro ao buscar (cookie inválido?)", inline=False)
    except Exception as e:
        embed.add_field(name="💰 Saldo Atual", value=f"❌ Não disponível: {e}", inline=False)

    return embed


class StockView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=180)
        self.bot = bot

    @ui.button(label="🔁 Exibir no Painel", style=discord.ButtonStyle.blurple, row=0)
    async def toggle_display(self, interaction: discord.Interaction, button: ui.Button):
        current = await DynamicConfig.robux_stock_display()
        await DynamicConfig.set("robux_stock_display", not current, updated_by=interaction.user.id)
        await interaction.response.edit_message(
            embed=await build_stock_embed(self.bot), view=self
        )

    @ui.button(label="⚠️ Definir Alerta", style=discord.ButtonStyle.gray, row=0)
    async def set_alert(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(StockAlertModal())

    @ui.button(label="🔄 Atualizar Saldo", style=discord.ButtonStyle.green, row=0)
    async def refresh(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(
            embed=await build_stock_embed(self.bot), view=self
        )

    @ui.button(label="⬅️ Voltar", style=discord.ButtonStyle.secondary, custom_id="cfg:stock_back", row=1)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(embed=await build_config_main_embed(), view=ConfigMainView(self.bot))


class StockAlertModal(ui.Modal, title="⚠️ Alerta de Estoque Baixo"):
    limite = ui.TextInput(
        label="Alertar quando saldo < X Robux",
        placeholder="1000",
        max_length=10,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.limite.value.replace(".", "").replace(",", ""))
            if val < 0:
                raise ValueError
        except Exception:
            await interaction.response.send_message("❌ Valor inválido.", ephemeral=True)
            return
        await DynamicConfig.set("stock_low_alert", val, updated_by=interaction.user.id)
        await interaction.response.send_message(
            f"✅ Alerta definido: notificar quando < **{val:,}** Robux", ephemeral=True
        )


# ══════════════════════════════════════════════════════════════════
# SEÇÃO: PIX MANUAL
# ══════════════════════════════════════════════════════════════════

async def build_pix_embed() -> discord.Embed:
    pix_key = await DynamicConfig.get("manual_pix_key")
    pix_key_type = await DynamicConfig.get("manual_pix_key_type")
    mode = await DynamicConfig.operation_mode()
    embed = discord.Embed(
        title="💳 Configuração de Pix Manual",
        color=0x00D166,
    )
    embed.add_field(
        name="🤖 Modo de Operação Atual",
        value=(
            "✅ **Manual** — a chave Pix abaixo será exibida para o cliente"
            if mode == "manual" else
            f"⚠️ Modo atual: **{mode}** — Pix manual só é usado no modo **Manual**"
        ),
        inline=False,
    )
    embed.add_field(
        name="🔑 Tipo da Chave",
        value=f"`{pix_key_type}`" if pix_key_type else "❌ Não configurado",
        inline=True,
    )
    embed.add_field(
        name="💳 Chave Pix",
        value=f"`{pix_key}`" if pix_key else "❌ Não configurada",
        inline=True,
    )
    embed.set_footer(text="Configure a chave Pix abaixo e mude o modo para Manual em 🤖 Modo de Operação.")
    return embed


class PixView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=180)
        self.bot = bot

    @ui.button(label="✏️ Configurar Chave Pix", style=discord.ButtonStyle.green, row=0)
    async def edit_pix(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(PixModal())

    @ui.button(label="🗑️ Remover Chave", style=discord.ButtonStyle.danger, row=0)
    async def remove_pix(self, interaction: discord.Interaction, button: ui.Button):
        await DynamicConfig.delete("manual_pix_key")
        await DynamicConfig.delete("manual_pix_key_type")
        await interaction.response.edit_message(embed=await build_pix_embed(), view=self)
        await interaction.followup.send("✅ Chave Pix removida!", ephemeral=True)

    @ui.button(label="⬅️ Voltar", style=discord.ButtonStyle.secondary, custom_id="cfg:pix_back", row=1)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(embed=await build_config_main_embed(), view=ConfigMainView(self.bot))


class PixModal(ui.Modal, title="💳 Configurar Chave Pix Manual"):
    key_type = ui.TextInput(
        label="Tipo da Chave",
        placeholder="CPF / CNPJ / Email / Telefone / Aleatória",
        max_length=20,
        required=True,
    )
    key_value = ui.TextInput(
        label="Chave Pix",
        placeholder="Ex: 123.456.789-00 ou email@email.com",
        max_length=150,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await DynamicConfig.set("manual_pix_key_type", self.key_type.value.strip(), updated_by=interaction.user.id)
        await DynamicConfig.set("manual_pix_key", self.key_value.value.strip(), updated_by=interaction.user.id)
        await LogRepository.log("config_changed", interaction.user.id,
                                details={"key": "manual_pix_key", "type": self.key_type.value})
        await interaction.response.send_message(
            f"✅ Chave Pix configurada!\n"
            f"**Tipo:** `{self.key_type.value}`\n"
            f"**Chave:** `{self.key_value.value}`\n\n"
            "Certifique-se de que o modo está como **Manual** em 🤖 Modo de Operação.",
            ephemeral=True,
        )


# ══════════════════════════════════════════════════════════════════
# RESUMO GERAL
# ══════════════════════════════════════════════════════════════════

async def build_summary_embed(guild: discord.Guild) -> discord.Embed:
    settings = get_settings()
    mode = await DynamicConfig.operation_mode()
    price = await DynamicConfig.price_per_1000()
    min_r = await DynamicConfig.min_robux()
    max_r = await DynamicConfig.max_robux()
    daily_robux = await DynamicConfig.daily_limit_robux()
    daily_brl = await DynamicConfig.daily_limit_brl()
    display_stock = await DynamicConfig.robux_stock_display()

    vendas_id = await DynamicConfig.channel_vendas_id() or settings.channel_vendas_id
    logs_id = await DynamicConfig.channel_logs_id() or settings.channel_logs_id
    cat_id = await DynamicConfig.category_tickets_id() or settings.category_tickets_id
    admin_id = await DynamicConfig.role_admin_id() or settings.role_admin_id

    mode_labels = {"auto": "🤖 Automático", "semi_auto": "⚡ Semi-Automático", "manual": "👤 Manual"}

    def ch_str(cid):
        if not cid or not guild:
            return "❌"
        ch = guild.get_channel(cid)
        return ch.mention if ch else f"`{cid}`"

    def role_str(rid):
        if not rid or not guild:
            return "❌"
        r = guild.get_role(rid)
        return r.mention if r else f"`{rid}`"

    embed = discord.Embed(
        title="📊 Resumo das Configurações",
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(name="🤖 Modo", value=mode_labels.get(mode, mode), inline=True)
    embed.add_field(name="💵 Preço/1k", value=f"R$ {price/100:.2f}", inline=True)
    embed.add_field(name="📉 Mínimo", value=f"{min_r:,} R$", inline=True)
    embed.add_field(name="📈 Máximo", value=f"{max_r:,} R$", inline=True)
    embed.add_field(
        name="🗓️ Limite Diário",
        value=(f"{daily_robux:,} R$" if daily_robux else "—") + " / " + (f"R${daily_brl:.0f}" if daily_brl else "—"),
        inline=True,
    )
    embed.add_field(name="💎 Estoque no Painel", value="✅" if display_stock else "❌", inline=True)
    embed.add_field(name="🛒 Canal Vendas", value=ch_str(vendas_id), inline=True)
    embed.add_field(name="📋 Canal Logs", value=ch_str(logs_id), inline=True)
    embed.add_field(name="🗂️ Categoria Tickets", value=ch_str(cat_id), inline=True)
    embed.add_field(name="🔑 Cargo Admin", value=role_str(admin_id), inline=True)

    # Vendas de hoje
    try:
        daily = await get_daily_stats(guild)
        embed.add_field(
            name="📈 Vendas Hoje",
            value=f"{daily['robux']:,} R$ / R$ {daily['brl']:.2f}",
            inline=False,
        )
    except Exception:
        pass

    embed.set_footer(text="Use /config para editar qualquer seção.")
    return embed


# ══════════════════════════════════════════════════════════════════
# COG PRINCIPAL
# ══════════════════════════════════════════════════════════════════

class ConfigCog(commands.Cog):
    """Cog do painel de configuração do bot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="config", description="⚙️ Painel de configuração do bot")
    @is_admin_check()
    async def config_panel(self, interaction: discord.Interaction):
        """Abre o painel de configuração completo."""
        settings = get_settings()
        mode = await DynamicConfig.operation_mode()
        price = await DynamicConfig.price_per_1000()
        mode_labels = {
            "auto": "🤖 Automático",
            "semi_auto": "⚡ Semi-Automático",
            "manual": "👤 Manual",
        }

        embed = discord.Embed(
            title="⚙️ Painel de Configuração",
            description=(
                "Bem-vindo ao painel central de configurações!\n"
                "Use o menu abaixo para navegar entre as seções.\n\n"
                "**Configurações atuais:**"
            ),
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="🤖 Modo", value=mode_labels.get(mode, mode), inline=True)
        embed.add_field(name="💵 Preço/1k R$", value=f"R$ {price/100:.2f}", inline=True)
        embed.add_field(name="📉 Mínimo", value=f"{await DynamicConfig.min_robux():,} R$", inline=True)
        embed.add_field(name="📈 Máximo", value=f"{await DynamicConfig.max_robux():,} R$", inline=True)

        daily_robux = await DynamicConfig.daily_limit_robux()
        embed.add_field(
            name="🗓️ Limite Diário",
            value=f"{daily_robux:,} R$" if daily_robux else "Sem limite",
            inline=True,
        )
        embed.add_field(
            name="💎 Estoque Visível",
            value="✅ Sim" if await DynamicConfig.robux_stock_display() else "❌ Não",
            inline=True,
        )

        embed.set_footer(
            text=f"Configurado por {interaction.user} • As alterações são salvas automaticamente",
            icon_url=interaction.user.display_avatar.url,
        )

        view = ConfigMainView(self.bot)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @config_panel.error
    async def config_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(
                "❌ Apenas administradores podem usar este comando.", ephemeral=True
            )
        else:
            logger.error(f"Erro no /config: {error}")
            await interaction.response.send_message(
                "❌ Ocorreu um erro ao abrir o painel.", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(ConfigCog(bot))
