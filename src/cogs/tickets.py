import discord
from discord import ui
from discord.ext import commands
from loguru import logger
from src.config import get_settings
from src.database import (
    TicketRepository,
    TicketStatus,
    TicketCreate,
    LogRepository,
)
from src.services import roblox_api


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

            # Envia mensagem de boas-vindas profissional
            settings = get_settings()
            price_per_1k = settings.price_per_1000_robux / 100

            # Banner/Header
            header_embed = discord.Embed(
                color=0x00D166,  # Verde vibrante
            )
            header_embed.set_image(url="https://i.imgur.com/8QXmZPR.png")  # Banner

            # Embed principal de boas-vindas
            welcome_embed = discord.Embed(
                title="<:robux:1234567890> Bem-vindo à Loja de Robux!",
                description=(
                    f"Olá {interaction.user.mention}! 👋\n\n"
                    "Estamos felizes em te atender! Aqui você pode comprar Robux "
                    "de forma **rápida**, **segura** e **automática**."
                ),
                color=0x5865F2,  # Blurple do Discord
            )
            welcome_embed.set_thumbnail(url=interaction.user.display_avatar.url)

            # Embed de preços
            price_embed = discord.Embed(
                title="💰 Tabela de Preços",
                color=0xFEE75C,  # Amarelo
            )

            # Calcula exemplos de preços
            examples = [100, 500, 1000, 2000, 5000, 10000]
            price_table = ""
            for robux in examples:
                price = settings.calculate_price(robux)
                price_table += f"**{robux:,}** R$ → `R$ {price:.2f}`\n"

            price_embed.add_field(
                name="📊 Exemplos",
                value=price_table,
                inline=True,
            )
            price_embed.add_field(
                name="ℹ️ Informações",
                value=(
                    f"💵 **R$ {price_per_1k:.2f}** / 1.000 R$\n"
                    f"📉 Mínimo: **{settings.min_robux_amount:,}** R$\n"
                    f"📈 Máximo: **{settings.max_robux_amount:,}** R$\n"
                    "⚡ Entrega: **Instantânea**"
                ),
                inline=True,
            )

            # Embed de como funciona
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
                color=0x5865F2,
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
            steps_embed.set_footer(
                text=f"🎫 Ticket #{ticket_id} • Atendimento 24/7",
                icon_url=interaction.guild.icon.url if interaction.guild.icon else None,
            )

            view = TicketActionsView()
            await channel.send(
                embeds=[welcome_embed, price_embed, steps_embed], view=view
            )
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
        """Abre modal para iniciar compra com novo fluxo."""
        # Busca ticket pelo canal
        ticket = await TicketRepository.get_by_channel(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message(
                "❌ Ticket não encontrado!", ephemeral=True
            )
            return

        modal = UsernameInputModal(ticket["ticket_id"])
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


class UsernameInputModal(ui.Modal, title="👤 Qual seu usuário Roblox?"):
    """Modal para pedir username do Roblox."""

    username = ui.TextInput(
        label="Usuário do Roblox",
        placeholder="Ex: PlayerName123",
        min_length=3,
        max_length=50,
        required=True,
    )

    def __init__(self, ticket_id: str):
        super().__init__()
        self.ticket_id = ticket_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        username = self.username.value.strip()

        # Valida o usuário
        valid, roblox_id, message = await roblox_api.validate_username(username)

        if not valid:
            embed = discord.Embed(
                title="❌ Usuário não encontrado",
                description=f"O usuário **{username}** não foi encontrado no Roblox.\n\n{message}",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Busca a thumbnail
        avatar_url = await roblox_api.get_user_avatar(roblox_id)

        # Mostra confirmação com thumbnail
        embed = discord.Embed(
            title="👤 Confirmar Jogador",
            description=f"**Usuário:** {username}\n**ID:** {roblox_id}",
            color=discord.Color.blue(),
        )

        if avatar_url:
            embed.set_thumbnail(url=avatar_url)

        view = PlayerConfirmView(self.ticket_id, username, roblox_id, avatar_url)
        await interaction.followup.send(embed=embed, view=view)


class PlayerConfirmView(ui.View):
    """View para confirmar o jogador selecionado."""

    def __init__(self, ticket_id: str, username: str, roblox_id: int, avatar_url: str = None):
        super().__init__(timeout=300)
        self.ticket_id = ticket_id
        self.username = username
        self.roblox_id = roblox_id
        self.avatar_url = avatar_url

    @ui.button(label="✅ Confirmar Jogador", style=discord.ButtonStyle.green)
    async def confirm_player(self, interaction: discord.Interaction, button: ui.Button):
        """Confirma o jogador e prossegue para quantidade de robux."""
        # Armazena o jogador selecionado
        interaction.client.ticket_players = getattr(interaction.client, "ticket_players", {})
        interaction.client.ticket_players[self.ticket_id] = {
            "username": self.username,
            "roblox_id": self.roblox_id,
            "avatar_url": self.avatar_url,
        }

        # Abre modal para quantidade
        modal = RobuxAmountModal(self.ticket_id, self.username, self.avatar_url)
        await interaction.response.send_modal(modal)

    @ui.button(label="❌ Cancelar", style=discord.ButtonStyle.red)
    async def cancel_player(self, interaction: discord.Interaction, button: ui.Button):
        """Cancela e volta."""
        await interaction.response.defer()
        await interaction.delete_original_response()


class RobuxAmountModal(ui.Modal, title="💎 Quantidade de Robux"):
    """Modal para pedir a quantidade de robux."""

    robux_amount = ui.TextInput(
        label="Quantidade de Robux",
        placeholder="Ex: 1000",
        min_length=1,
        max_length=10,
        required=True,
    )

    def __init__(self, ticket_id: str, username: str, avatar_url: str = None):
        super().__init__()
        self.ticket_id = ticket_id
        self.username = username
        self.avatar_url = avatar_url

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        # Valida quantidade
        try:
            amount = int(self.robux_amount.value.replace(".", "").replace(",", ""))
        except ValueError:
            embed = discord.Embed(
                title="❌ Quantidade inválida",
                description="Digite apenas números.",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        settings = get_settings()

        # Valida limites
        if amount < settings.min_robux_amount:
            embed = discord.Embed(
                title="❌ Quantidade mínima",
                description=f"O mínimo é **{settings.min_robux_amount:,}** Robux.",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if amount > settings.max_robux_amount:
            embed = discord.Embed(
                title="❌ Quantidade máxima",
                description=f"O máximo é **{settings.max_robux_amount:,}** Robux.",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Calcula preço
        final_price = settings.calculate_price(amount)

        # Mostra resumo com confirmação
        embed = discord.Embed(
            title="📋 Resumo da Compra",
            color=0x5865F2,
        )

        embed.add_field(
            name="👤 Jogador",
            value=f"```{self.username}```",
            inline=True,
        )
        embed.add_field(
            name="💎 Robux",
            value=f"```{amount:,}```",
            inline=True,
        )
        embed.add_field(
            name="\u200b",
            value="\u200b",
            inline=False,
        )
        embed.add_field(
            name="💵 Preço Total",
            value=f"**R$ {final_price:.2f}**",
            inline=True,
        )

        # Mostra preço unitário
        price_per_1k = settings.price_per_1000_robux / 100
        embed.add_field(
            name="📊 Taxa",
            value=f"R$ {price_per_1k:.2f} / 1.000 R$",
            inline=True,
        )

        if self.avatar_url:
            embed.set_thumbnail(url=self.avatar_url)

        # Armazena dados para processamento
        interaction.client.ticket_orders = getattr(interaction.client, "ticket_orders", {})
        interaction.client.ticket_orders[self.ticket_id] = {
            "username": self.username,
            "roblox_id": interaction.client.ticket_players[self.ticket_id]["roblox_id"],
            "amount": amount,
            "price": final_price,
            "avatar_url": self.avatar_url,
        }

        view = OrderConfirmView(self.ticket_id, amount, final_price)
        await interaction.followup.send(embed=embed, view=view)


class OrderConfirmView(ui.View):
    """View para confirmar a compra final."""

    def __init__(self, ticket_id: str, amount: int, price: float):
        super().__init__(timeout=300)
        self.ticket_id = ticket_id
        self.amount = amount
        self.price = price

    @ui.button(label="✅ Confirmar Compra", style=discord.ButtonStyle.green)
    async def confirm_order(self, interaction: discord.Interaction, button: ui.Button):
        """Mostra opções de gateway de pagamento."""
        settings = get_settings()

        # Se apenas um gateway está disponível, usa direto
        has_mercadopago = bool(settings.mercadopago_access_token)
        has_paysync = bool(settings.paysync_api_key)

        if has_mercadopago and not has_paysync:
            # Usa Mercado Pago direto
            await self._process_with_gateway(interaction, "mercadopago")
        elif has_paysync and not has_mercadopago:
            # Usa PaySync direto
            await self._process_with_gateway(interaction, "paysync")
        elif has_mercadopago and has_paysync:
            # Mostra opções
            await interaction.response.defer()
            embed = discord.Embed(
                title="💳 Escolha o Gateway de Pagamento",
                description="Selecione qual método de pagamento você prefere:",
                color=0x5865F2,
            )
            embed.add_field(
                name="💰 Mercado Pago",
                value="PIX instantâneo com o Mercado Pago",
                inline=False,
            )
            embed.add_field(
                name="🔐 PaySync",
                value="PIX instantâneo com PaySync",
                inline=False,
            )

            view = PaymentGatewayView(self.ticket_id)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            embed = discord.Embed(
                title="❌ Erro",
                description="Nenhum gateway de pagamento configurado.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _process_with_gateway(
        self, interaction: discord.Interaction, gateway: str
    ) -> None:
        """Processa a compra com o gateway especificado."""
        await interaction.response.defer()

        ticket_orders = getattr(interaction.client, "ticket_orders", {})
        if self.ticket_id not in ticket_orders:
            embed = discord.Embed(
                title="❌ Erro",
                description="Dados da compra não encontrados. Tente novamente.",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        order_data = ticket_orders[self.ticket_id]

        # Armazena gateway escolhido
        interaction.client.ticket_gateways = getattr(
            interaction.client, "ticket_gateways", {}
        )
        interaction.client.ticket_gateways[self.ticket_id] = gateway

        # Processa a compra via OrdersCog
        cog = interaction.client.get_cog("OrdersCog")
        if cog:
            await cog.process_order(
                interaction,
                self.ticket_id,
                order_data["amount"],
                order_data["username"],
            )

    @ui.button(label="❌ Cancelar", style=discord.ButtonStyle.red)
    async def cancel_order(self, interaction: discord.Interaction, button: ui.Button):
        """Cancela a compra."""
        await interaction.response.defer()
        embed = discord.Embed(
            title="❌ Compra cancelada",
            description="Você cancelou a compra. Clique em 'Iniciar Compra' novamente se desejar continuar.",
            color=discord.Color.red(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


class PaymentGatewayView(ui.View):
    """View para escolher gateway de pagamento."""

    def __init__(self, ticket_id: str):
        super().__init__(timeout=300)
        self.ticket_id = ticket_id

    @ui.button(
        label="💰 Mercado Pago",
        style=discord.ButtonStyle.blurple,
    )
    async def choose_mercadopago(
        self, interaction: discord.Interaction, button: ui.Button
    ):
        """Escolhe Mercado Pago como gateway."""
        await interaction.response.defer()

        ticket_orders = getattr(interaction.client, "ticket_orders", {})
        if self.ticket_id not in ticket_orders:
            embed = discord.Embed(
                title="❌ Erro",
                description="Dados da compra não encontrados.",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        order_data = ticket_orders[self.ticket_id]

        # Armazena gateway escolhido
        interaction.client.ticket_gateways = getattr(
            interaction.client, "ticket_gateways", {}
        )
        interaction.client.ticket_gateways[self.ticket_id] = "mercadopago"

        # Processa a compra
        cog = interaction.client.get_cog("OrdersCog")
        if cog:
            await cog.process_order(
                interaction,
                self.ticket_id,
                order_data["amount"],
                order_data["username"],
            )

    @ui.button(
        label="🔐 PaySync",
        style=discord.ButtonStyle.green,
    )
    async def choose_paysync(self, interaction: discord.Interaction, button: ui.Button):
        """Escolhe PaySync como gateway."""
        await interaction.response.defer()

        ticket_orders = getattr(interaction.client, "ticket_orders", {})
        if self.ticket_id not in ticket_orders:
            embed = discord.Embed(
                title="❌ Erro",
                description="Dados da compra não encontrados.",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        order_data = ticket_orders[self.ticket_id]

        # Armazena gateway escolhido
        interaction.client.ticket_gateways = getattr(
            interaction.client, "ticket_gateways", {}
        )
        interaction.client.ticket_gateways[self.ticket_id] = "paysync"

        # Processa a compra
        cog = interaction.client.get_cog("OrdersCog")
        if cog:
            await cog.process_order(
                interaction,
                self.ticket_id,
                order_data["amount"],
                order_data["username"],
            )


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
    """Configura o painel de tickets profissional."""
    settings = get_settings()

    channel = bot.get_channel(settings.channel_vendas_id)
    if not channel:
        logger.warning("⚠️ Canal de vendas não encontrado")
        return

    # Verifica se já existe mensagem do painel
    async for message in channel.history(limit=10):
        if message.author == bot.user and message.embeds:
            for embed in message.embeds:
                if embed.title and "Loja" in embed.title:
                    # Adiciona view persistente
                    view = TicketCreateButton()
                    await message.edit(view=view)
                    logger.info("✅ Painel de tickets atualizado")
                    return

    # Calcula preço para exibição
    price_per_1k = settings.price_per_1000_robux / 100

    # ═══════════════════════════════════════════════════════════
    # EMBED 1: Header/Banner
    # ═══════════════════════════════════════════════════════════
    banner_embed = discord.Embed(color=0x5865F2)
    banner_embed.set_image(url="https://i.imgur.com/KRK5Fz0.png")  # Banner da loja

    # ═══════════════════════════════════════════════════════════
    # EMBED 2: Informações Principais
    # ═══════════════════════════════════════════════════════════
    main_embed = discord.Embed(
        title="<:robux:1234567890> Loja Oficial de Robux",
        description=(
            "Compre Robux de forma **rápida**, **segura** e com\n"
            "**entrega automática** via Gamepass!\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=0x00D166,
    )

    main_embed.add_field(
        name="💰 Preço",
        value=f"**R$ {price_per_1k:.2f}** / 1.000 R$",
        inline=True,
    )
    main_embed.add_field(
        name="⚡ Entrega",
        value="**Instantânea**",
        inline=True,
    )
    main_embed.add_field(
        name="💳 Pagamento",
        value="**PIX**",
        inline=True,
    )

    # ═══════════════════════════════════════════════════════════
    # EMBED 3: Vantagens
    # ═══════════════════════════════════════════════════════════
    features_embed = discord.Embed(
        title="✨ Por que comprar conosco?",
        color=0x5865F2,
    )
    features_embed.add_field(
        name="🔒 100% Seguro",
        value="Método oficial via Gamepass\nNão pedimos senha",
        inline=True,
    )
    features_embed.add_field(
        name="🤖 Automático",
        value="Sistema 100% automatizado\nSem esperar atendente",
        inline=True,
    )
    features_embed.add_field(
        name="💎 Melhor Preço",
        value="Valores competitivos\nDescontos com cupom",
        inline=True,
    )

    # ═══════════════════════════════════════════════════════════
    # EMBED 4: Call to Action
    # ═══════════════════════════════════════════════════════════
    cta_embed = discord.Embed(
        description=(
            "```\n" "🛒 Clique no botão abaixo para iniciar sua compra!\n" "```"
        ),
        color=0xFEE75C,
    )
    cta_embed.set_footer(
        text="🕐 Atendimento 24/7 • ⭐ +1000 clientes satisfeitos",
    )

    view = TicketCreateButton()
    await channel.send(
        embeds=[banner_embed, main_embed, features_embed, cta_embed], view=view
    )
    logger.success("✅ Painel de tickets criado")


class TicketsCog(commands.Cog):
    """Cog de gerenciamento de tickets."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    """Registra a cog de tickets."""
    await bot.add_cog(TicketsCog(bot))
