import discord
from discord import ui
from discord.ext import commands
from loguru import logger
from src.config import get_settings, DynamicConfig
from src.database import (
    TicketRepository,
    TicketStatus,
    TicketCreate,
    LogRepository,
)


class TicketCreateButton(ui.View):
    """Botão para criar ticket."""

    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="🛒 Comprar Robux",
        style=discord.ButtonStyle.green,
        custom_id="ticket:create",
    )
    async def create_ticket(self, interaction: discord.Interaction, button: ui.Button):
        """Cria um novo ticket/carrinho."""
        try:
            settings = get_settings()
            logger.info(f"🎫 Usuário {interaction.user} tentando criar ticket")

            # Verifica se já tem ticket aberto
            existing = await TicketRepository.get_user_open_ticket(interaction.user.id)
            if existing:
                try:
                    channel = interaction.guild.get_channel(existing["channel_id"])
                    if channel:
                        await interaction.response.send_message(
                            f"❌ Você já tem um ticket aberto: {channel.mention}",
                            ephemeral=True,
                        )
                        logger.info(
                            f"⚠️ Usuário {interaction.user} já tem ticket aberto"
                        )
                        return
                except Exception as e:
                    logger.warning(f"⚠️ Erro ao verificar ticket existente: {e}")

            await interaction.response.defer(ephemeral=True)
            logger.info(f"✅ Criando canal de ticket para {interaction.user}")

            # Cria o canal do ticket
            category = interaction.guild.get_channel(settings.category_tickets_id)
            if not category:
                logger.error(
                    f"❌ Categoria de tickets não encontrada: {settings.category_tickets_id}"
                )
                await interaction.followup.send(
                    "❌ Categoria de tickets não configurada. Contate um administrador.",
                    ephemeral=True,
                )
                return

            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(
                    read_messages=False
                ),
                interaction.user: discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    attach_files=True,
                    embed_links=True,
                ),
                interaction.guild.me: discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    manage_channels=True,
                    manage_messages=True,
                ),
            }

            # Adiciona admins
            admin_role = interaction.guild.get_role(settings.role_admin_id)
            if admin_role:
                overwrites[admin_role] = discord.PermissionOverwrite(
                    read_messages=True, send_messages=True, manage_messages=True
                )

            channel = await interaction.guild.create_text_channel(
                name=f"🛒│{interaction.user.name[:20]}",
                category=category,
                overwrites=overwrites,
                topic=f"Ticket de {interaction.user.name} | ID: {interaction.user.id}",
            )
            logger.success(f"✅ Canal criado: {channel.name} (ID: {channel.id})")

            # Salva no banco
            ticket_data = TicketCreate(
                user_id=interaction.user.id,
                channel_id=channel.id,
                subject="Compra de Robux",
            )
            ticket_id = await TicketRepository.create(ticket_data)
            logger.success(f"✅ Ticket salvo no banco: {ticket_id}")

            # Envia mensagem de boas-vindas (usa config dinâmica)
            settings = get_settings()
            price_cents = await DynamicConfig.price_per_1000()
            price_per_1k = price_cents / 100
            min_r = await DynamicConfig.min_robux()
            max_r = await DynamicConfig.max_robux()
            ticket_cfg = await DynamicConfig.ticket_embed()

            embeds_to_send = []

            # Banner (se configurado)
            banner_url = ticket_cfg.get("banner_url", "")
            if banner_url:
                header_embed = discord.Embed(color=ticket_cfg.get("color", 0x5865F2))
                header_embed.set_image(url=banner_url)
                embeds_to_send.append(header_embed)

            # Embed principal de boas-vindas
            desc = ticket_cfg.get(
                "description",
                "Olá {mention}! 👋\n\nEstamos felizes em te atender! Aqui você pode comprar Robux de forma **rápida**, **segura** e **automática**.",
            ).replace("{mention}", interaction.user.mention)

            welcome_embed = discord.Embed(
                title=ticket_cfg.get("title", "🛒 Bem-vindo à Loja de Robux!"),
                description=desc,
                color=ticket_cfg.get("color", 0x5865F2),
            )
            welcome_embed.set_thumbnail(url=interaction.user.display_avatar.url)
            embeds_to_send.append(welcome_embed)

            # Tabela de preços (configurável)
            if ticket_cfg.get("show_price_table", True):
                price_embed = discord.Embed(title="💰 Tabela de Preços", color=0xFEE75C)
                examples = [100, 500, 1000, 2000, 5000, 10000]
                price_table = ""
                for robux in examples:
                    p = robux * (price_cents / 100) / 1000
                    price_table += f"**{robux:,}** R$ → `R$ {p:.2f}`\n"
                price_embed.add_field(name="📊 Exemplos", value=price_table, inline=True)
                price_embed.add_field(
                    name="ℹ️ Informações",
                    value=(
                        f"💵 **R$ {price_per_1k:.2f}** / 1.000 R$\n"
                        f"📉 Mínimo: **{min_r:,}** R$\n"
                        f"📈 Máximo: **{max_r:,}** R$\n"
                        "⚡ Entrega: **Instantânea**"
                    ),
                    inline=True,
                )
                embeds_to_send.append(price_embed)

            # Passos de compra (configurável)
            if ticket_cfg.get("show_steps", True):
                steps_embed = discord.Embed(
                    title="📋 Como Funciona?",
                    description=(
                        "```\n"
                        "1️⃣ Clique em 'Iniciar Compra'\n"
                        "2️⃣ Informe quantidade e seu usuário Roblox\n"
                        "3️⃣ Pague o PIX gerado\n"
                        "4️⃣ Crie um Gamepass no valor indicado\n"
                        "5️⃣ Envie o link e receba seus Robux!\n"
                        "```"
                    ),
                    color=ticket_cfg.get("color", 0x5865F2),
                )
                steps_embed.add_field(
                    name="🔒 Segurança Garantida",
                    value=(
                        "• Método oficial via Gamepass\n"
                        "• Não pedimos senha ou cookie\n"
                        "• Pagamento seguro via PIX\n"
                        "• Entrega verificada automaticamente"
                    ),
                    inline=False,
                )
                footer_text = ticket_cfg.get("footer", "Atendimento 24/7")
                steps_embed.set_footer(
                    text=f"🎫 Ticket #{ticket_id} • {footer_text}",
                    icon_url=interaction.guild.icon.url if interaction.guild.icon else None,
                )
                embeds_to_send.append(steps_embed)

            view = TicketActionsView()
            await channel.send(embeds=embeds_to_send, view=view)
            logger.success(f"✅ Mensagem inicial enviada no ticket {ticket_id}")

            await interaction.followup.send(
                f"✅ Seu carrinho foi criado: {channel.mention}", ephemeral=True
            )

            # Log
            await LogRepository.log(
                action="ticket_created",
                user_id=interaction.user.id,
                details={"ticket_id": ticket_id, "channel_id": channel.id},
            )

        except Exception as e:
            logger.error(f"❌ ERRO CRÍTICO ao criar ticket: {e}")
            logger.exception(e)  # Mostra traceback completo
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(
                        f"❌ Erro ao criar ticket: {str(e)}\nContate um administrador.",
                        ephemeral=True,
                    )
                else:
                    await interaction.response.send_message(
                        f"❌ Erro ao criar ticket: {str(e)}\nContate um administrador.",
                        ephemeral=True,
                    )
            except Exception:
                logger.error("❌ Não foi possível enviar mensagem de erro ao usuário")


class TicketActionsView(ui.View):
    """Ações do ticket."""

    def __init__(self, ticket_id: str = None):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id

        # Se ticket_id foi fornecido, atualiza os custom_ids
        if ticket_id:
            for item in self.children:
                if isinstance(item, ui.Button):
                    # Mantém o prefixo mas não inclui ticket_id no custom_id
                    # pois o custom_id deve ser fixo para persistência
                    pass

    @ui.button(
        label="💰 Iniciar Compra",
        style=discord.ButtonStyle.green,
        custom_id="ticket:buy",
        row=0,
    )
    async def start_buy(self, interaction: discord.Interaction, button: ui.Button):
        """Abre modal para iniciar compra (Passo 1: quantidade)."""
        ticket = await TicketRepository.get_by_channel(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message(
                "❌ Ticket não encontrado!", ephemeral=True
            )
            return

        modal = AmountModal(ticket["ticket_id"])
        await interaction.response.send_modal(modal)

    @ui.button(
        label="🎟️ Usar Cupom",
        style=discord.ButtonStyle.blurple,
        custom_id="ticket:coupon",
        row=0,
    )
    async def use_coupon(self, interaction: discord.Interaction, button: ui.Button):
        """Abre modal para usar cupom."""
        # Busca ticket pelo canal
        ticket = await TicketRepository.get_by_channel(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message(
                "❌ Ticket não encontrado!", ephemeral=True
            )
            return

        modal = CouponModal(ticket["ticket_id"])
        await interaction.response.send_modal(modal)

    @ui.button(
        label="❓ Ajuda", style=discord.ButtonStyle.gray, custom_id="ticket:help", row=0
    )
    async def show_help(self, interaction: discord.Interaction, button: ui.Button):
        """Mostra ajuda."""
        settings = get_settings()

        price_per_1k = settings.price_per_1000_robux / 100

        embed = discord.Embed(
            title="❓ Central de Ajuda",
            description=(
                "**💰 Preços:**\n"
                f"• 1.000 Robux = R$ {price_per_1k:.2f}\n"
                f"• Mínimo: {settings.min_robux_amount} Robux\n"
                f"• Máximo: {settings.max_robux_amount} Robux\n\n"
                "**📋 Processo de Entrega:**\n"
                "Utilizamos o sistema de **Gamepasses** do Roblox.\n"
                "Após o pagamento, você compra um gamepass especial\n"
                "e recebe os Robux diretamente na sua conta!\n\n"
                "**⏰ Tempo de Entrega:**\n"
                "Após pagamento confirmado: **Instantâneo**\n\n"
                "**🔒 Segurança:**\n"
                "• Método 100% seguro e permitido pelo Roblox\n"
                "• Não pedimos sua senha ou cookie\n"
                "• Pagamento via PIX com confirmação automática"
            ),
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(
        label="🔴 Fechar Ticket",
        style=discord.ButtonStyle.danger,
        custom_id="ticket:close",
        row=1,
    )
    async def close_ticket(self, interaction: discord.Interaction, button: ui.Button):
        """Fecha o ticket."""
        settings = get_settings()

        # Busca ticket pelo canal
        ticket = await TicketRepository.get_by_channel(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message(
                "❌ Ticket não encontrado!", ephemeral=True
            )
            return

        # Verifica permissão
        is_owner = interaction.user.id == ticket["user_id"]
        is_admin = any(r.id == settings.role_admin_id for r in interaction.user.roles)

        if not is_owner and not is_admin:
            await interaction.response.send_message(
                "❌ Apenas o dono do ticket ou admins podem fechar.", ephemeral=True
            )
            return

        # Confirmação
        view = ConfirmCloseView(ticket["ticket_id"], interaction.user.id)
        await interaction.response.send_message(
            "⚠️ Tem certeza que deseja fechar este ticket?", view=view, ephemeral=True
        )


class AmountModal(ui.Modal, title="💰 Quantos Robux?"):
    """Passo 1: pede apenas a quantidade de Robux."""

    robux_amount = ui.TextInput(
        label="Quantidade de Robux",
        placeholder="Ex: 1000",
        min_length=1,
        max_length=10,
        required=True,
    )

    def __init__(self, ticket_id: str):
        super().__init__()
        self.ticket_id = ticket_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.robux_amount.value.replace(".", "").replace(",", ""))
        except ValueError:
            await interaction.response.send_message(
                "❌ Quantidade inválida. Digite apenas números.", ephemeral=True
            )
            return

        await interaction.response.defer()

        min_r = await DynamicConfig.min_robux()
        max_r = await DynamicConfig.max_robux()
        price_cents = await DynamicConfig.price_per_1000()

        if amount < min_r:
            await interaction.followup.send(f"❌ Mínimo de {min_r:,} Robux.", ephemeral=True)
            return
        if amount > max_r:
            await interaction.followup.send(f"❌ Máximo de {max_r:,} Robux.", ephemeral=True)
            return

        base_price = amount * (price_cents / 100) / 1000

        ticket_coupons = getattr(interaction.client, "ticket_coupons", {})
        coupon = ticket_coupons.get(self.ticket_id)
        discount = coupon["discount"] if coupon else 0.0
        final_price = base_price * (1 - discount)

        if not hasattr(interaction.client, "purchase_state"):
            interaction.client.purchase_state = {}
        interaction.client.purchase_state[interaction.channel.id] = {
            "ticket_id": self.ticket_id,
            "robux_amount": amount,
            "base_price": base_price,
            "final_price": final_price,
            "discount": discount,
            "coupon": coupon,
        }

        embed = discord.Embed(
            title="💰 Resumo do Preço",
            description="Confira o valor antes de continuar:",
            color=0x00D166,
        )
        embed.add_field(name="💎 Quantidade", value=f"**{amount:,} Robux**", inline=True)
        if discount > 0:
            embed.add_field(
                name="💵 Valor",
                value=f"~~R$ {base_price:.2f}~~ → **R$ {final_price:.2f}**\n`{coupon['code']}` (-{discount*100:.0f}%)",
                inline=True,
            )
        else:
            embed.add_field(name="💵 Valor", value=f"**R$ {final_price:.2f}**", inline=True)
        embed.set_footer(text="Clique em ✅ Confirmar para informar seu usuário Roblox.")

        await interaction.followup.send(embed=embed, view=PriceConfirmView())


class PriceConfirmView(ui.View):
    """Passo 2: confirma o preço e abre o modal de username."""

    def __init__(self):
        super().__init__(timeout=300)

    @ui.button(label="✅ Confirmar", style=discord.ButtonStyle.green, custom_id="buy:price_confirm")
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        state = getattr(interaction.client, "purchase_state", {}).get(interaction.channel.id)
        if not state:
            await interaction.response.send_message(
                "❌ Sessão expirada. Clique em **💰 Iniciar Compra** novamente.", ephemeral=True
            )
            return
        await interaction.response.send_modal(UsernameModal())

    @ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger, custom_id="buy:price_cancel")
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        ps = getattr(interaction.client, "purchase_state", {})
        ps.pop(interaction.channel.id, None)
        embed = discord.Embed(
            title="❌ Compra Cancelada",
            description="Você pode clicar em **💰 Iniciar Compra** para tentar novamente.",
            color=discord.Color.red(),
        )
        await interaction.response.edit_message(embed=embed, view=None)


class UsernameModal(ui.Modal, title="👤 Usuário do Roblox"):
    """Passo 3: pede o nickname do Roblox."""

    roblox_username = ui.TextInput(
        label="Seu usuário do Roblox",
        placeholder="Ex: PlayerName123",
        min_length=3,
        max_length=50,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        state = getattr(interaction.client, "purchase_state", {}).get(interaction.channel.id)
        if not state:
            await interaction.followup.send(
                "❌ Sessão expirada. Clique em **💰 Iniciar Compra** novamente.", ephemeral=True
            )
            return

        from src.services import roblox_api
        username = self.roblox_username.value.strip()

        valid, roblox_id, message = await roblox_api.validate_username(username)
        if not valid:
            await interaction.followup.send(
                f"❌ Usuário **{username}** não encontrado no Roblox.\n{message}\n\n"
                "Verifique o nome e tente novamente clicando em ✅ Confirmar.",
                ephemeral=True,
            )
            return

        avatar_url = (
            f"https://www.roblox.com/headshot-thumbnail/image"
            f"?userId={roblox_id}&width=150&height=150&format=png"
        )

        state["roblox_username"] = username
        state["roblox_id"] = roblox_id
        state["avatar_url"] = avatar_url

        embed = discord.Embed(
            title="👤 Confirmar Conta Roblox",
            description=(
                f"Verifique se esta é **sua** conta antes de confirmar:\n\n"
                f"**Usuário:** `{username}`\n"
                f"**ID Roblox:** `{roblox_id}`"
            ),
            color=0x5865F2,
        )
        embed.set_thumbnail(url=avatar_url)
        embed.add_field(name="💎 Robux", value=f"**{state['robux_amount']:,}**", inline=True)
        embed.add_field(name="💵 Valor", value=f"**R$ {state['final_price']:.2f}**", inline=True)
        embed.set_footer(text="⚠️ Certifique-se de que esta é a conta correta!")

        await interaction.followup.send(embed=embed, view=RobloxConfirmView())


class RobloxConfirmView(ui.View):
    """Passo 4: confirma a conta Roblox e inicia o pagamento."""

    def __init__(self):
        super().__init__(timeout=300)

    @ui.button(label="✅ Confirmar e Pagar", style=discord.ButtonStyle.green, custom_id="buy:roblox_confirm")
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        state = getattr(interaction.client, "purchase_state", {}).get(interaction.channel.id)
        if not state:
            await interaction.response.send_message(
                "❌ Sessão expirada. Clique em **💰 Iniciar Compra** novamente.", ephemeral=True
            )
            return

        await interaction.response.defer()

        ps = getattr(interaction.client, "purchase_state", {})
        ps.pop(interaction.channel.id, None)

        cog = interaction.client.get_cog("OrdersCog")
        if cog:
            mode = await DynamicConfig.operation_mode()
            if mode == "manual":
                await cog.process_manual_order(
                    interaction,
                    state["ticket_id"],
                    state["robux_amount"],
                    state["roblox_username"],
                    state["roblox_id"],
                    state.get("coupon"),
                )
            else:
                await cog.process_order(
                    interaction,
                    state["ticket_id"],
                    state["robux_amount"],
                    state["roblox_username"],
                    roblox_id=state["roblox_id"],
                    coupon=state.get("coupon"),
                )

    @ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger, custom_id="buy:roblox_cancel")
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        ps = getattr(interaction.client, "purchase_state", {})
        ps.pop(interaction.channel.id, None)
        embed = discord.Embed(
            title="❌ Compra Cancelada",
            description="Você pode clicar em **💰 Iniciar Compra** para tentar novamente.",
            color=discord.Color.red(),
        )
        await interaction.response.edit_message(embed=embed, view=None)

    @ui.button(label="✏️ Trocar Usuário", style=discord.ButtonStyle.gray, custom_id="buy:roblox_change")
    async def change(self, interaction: discord.Interaction, button: ui.Button):
        state = getattr(interaction.client, "purchase_state", {}).get(interaction.channel.id)
        if not state:
            await interaction.response.send_message(
                "❌ Sessão expirada.", ephemeral=True
            )
            return
        await interaction.response.send_modal(UsernameModal())


class CouponModal(ui.Modal, title="🎟️ Usar Cupom"):
    """Modal para usar cupom."""

    coupon_code = ui.TextInput(
        label="Código do Cupom",
        placeholder="Ex: DESCONTO10",
        min_length=3,
        max_length=30,
        required=True,
    )

    def __init__(self, ticket_id: str):
        super().__init__()
        self.ticket_id = ticket_id

    async def on_submit(self, interaction: discord.Interaction):
        from src.database import CouponRepository

        code = self.coupon_code.value.strip().upper()

        # Verifica cupom
        valid, message, discount = await CouponRepository.validate(code, 1000)

        if valid:
            embed = discord.Embed(
                title="✅ Cupom Válido!",
                description=(
                    f"**Código:** `{code}`\n"
                    f"**Desconto:** {discount * 100:.0f}%\n\n"
                    "O cupom será aplicado automaticamente na sua compra!"
                ),
                color=discord.Color.green(),
            )

            # Salva cupom no ticket (em memória, será usado na compra)
            interaction.client.ticket_coupons = getattr(
                interaction.client, "ticket_coupons", {}
            )
            interaction.client.ticket_coupons[self.ticket_id] = {
                "code": code,
                "discount": discount,
            }
        else:
            embed = discord.Embed(
                title="❌ Cupom Inválido",
                description=message,
                color=discord.Color.red(),
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)


class ConfirmCloseView(ui.View):
    """Confirmação para fechar ticket."""

    def __init__(self, ticket_id: str, user_id: int):
        super().__init__(timeout=60)
        self.ticket_id = ticket_id
        self.user_id = user_id

    @ui.button(label="✅ Sim, Fechar", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            return

        await interaction.response.defer()

        # Atualiza status
        await TicketRepository.update_status(
            self.ticket_id, TicketStatus.CLOSED, closed_by=interaction.user.id
        )

        # Log
        await LogRepository.log(
            action="ticket_closed",
            user_id=interaction.user.id,
            details={"ticket_id": self.ticket_id},
        )

        embed = discord.Embed(
            title="🔒 Ticket Fechado",
            description="Este ticket será deletado em 5 segundos...",
            color=discord.Color.red(),
        )
        await interaction.channel.send(embed=embed)

        # Deleta o canal após 5 segundos
        import asyncio as aio

        await aio.sleep(5)

        try:
            await interaction.channel.delete(reason="Ticket fechado")
        except Exception:
            pass

    @ui.button(label="❌ Cancelar", style=discord.ButtonStyle.gray)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            return

        await interaction.response.edit_message(
            content="✅ Operação cancelada.", view=None
        )


async def setup_ticket_panel(bot: commands.Bot) -> None:
    """Configura o painel de tickets (usa config dinâmica)."""
    settings = get_settings()

    vendas_id = await DynamicConfig.channel_vendas_id() or settings.channel_vendas_id
    channel = bot.get_channel(vendas_id)
    if not channel:
        logger.warning("⚠️ Canal de vendas não encontrado")
        return

    # Verifica se já existe mensagem do painel
    async for message in channel.history(limit=10):
        if message.author == bot.user and message.embeds:
            for embed in message.embeds:
                if embed.title and ("Loja" in embed.title or "loja" in embed.title):
                    view = TicketCreateButton()
                    await message.edit(view=view)
                    logger.info("✅ Painel de tickets atualizado")
                    return

    # Carrega configurações dinâmicas da embed
    shop_cfg = await DynamicConfig.shop_embed()
    price_cents = await DynamicConfig.price_per_1000()
    price_per_1k = price_cents / 100
    color = shop_cfg.get("color", 0x00D166)

    embeds_to_send = []

    # Banner (se configurado)
    banner_url = shop_cfg.get("banner_url", "")
    if banner_url:
        banner_embed = discord.Embed(color=color)
        banner_embed.set_image(url=banner_url)
        embeds_to_send.append(banner_embed)

    # Embed principal
    main_embed = discord.Embed(
        title=shop_cfg.get("title", "🏪 Loja Oficial de Robux"),
        description=shop_cfg.get(
            "description",
            "Compre Robux de forma **rápida**, **segura** e com\n**entrega automática** via Gamepass!\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ),
        color=color,
    )
    if shop_cfg.get("title_url"):
        main_embed.url = shop_cfg["title_url"]
    if shop_cfg.get("author_name"):
        main_embed.set_author(
            name=shop_cfg["author_name"],
            icon_url=shop_cfg.get("author_icon_url") or None,
            url=shop_cfg.get("author_url") or None,
        )
    if shop_cfg.get("thumbnail_url"):
        main_embed.set_thumbnail(url=shop_cfg["thumbnail_url"])

    main_embed.add_field(name="💰 Preço", value=f"**R$ {price_per_1k:.2f}** / 1.000 R$", inline=True)
    main_embed.add_field(name="⚡ Entrega", value="**Instantânea**", inline=True)
    main_embed.add_field(name="💳 Pagamento", value="**PIX**", inline=True)

    # Estoque visível
    if await DynamicConfig.robux_stock_display():
        try:
            from src.services import roblox_api
            balance = await roblox_api.get_my_robux_balance()
            if balance is not None:
                main_embed.add_field(
                    name="💎 Estoque",
                    value=f"**{balance:,} R$** disponíveis",
                    inline=True,
                )
        except Exception:
            pass

    embeds_to_send.append(main_embed)

    # Vantagens
    features_embed = discord.Embed(title="✨ Por que comprar conosco?", color=color)
    features_embed.add_field(name="🔒 100% Seguro", value="Método oficial via Gamepass\nNão pedimos senha", inline=True)
    features_embed.add_field(name="🤖 Automático", value="Sistema 100% automatizado\nSem esperar atendente", inline=True)
    features_embed.add_field(name="💎 Melhor Preço", value="Valores competitivos\nDescontos com cupom", inline=True)
    embeds_to_send.append(features_embed)

    # CTA
    # Custom fields configurados pelo admin
    for f in shop_cfg.get("fields", []):
        main_embed.add_field(
            name=f.get("name", ""),
            value=f.get("value", ""),
            inline=f.get("inline", True),
        )

    cta_embed = discord.Embed(
        description="```\n🛒 Clique no botão abaixo para iniciar sua compra!\n```",
        color=0xFEE75C,
    )
    footer_text = shop_cfg.get("footer", "🕐 Atendimento 24/7 • ⭐ +1000 clientes satisfeitos")
    footer_icon = shop_cfg.get("footer_icon_url") or None
    cta_embed.set_footer(text=footer_text, icon_url=footer_icon)
    embeds_to_send.append(cta_embed)

    view = TicketCreateButton()
    await channel.send(embeds=embeds_to_send, view=view)
    logger.success("✅ Painel de tickets criado")


class TicketsCog(commands.Cog):
    """Cog de gerenciamento de tickets."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    """Registra a cog de tickets."""
    await bot.add_cog(TicketsCog(bot))
