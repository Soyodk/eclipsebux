from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    """Configurações centralizadas do bot usando Pydantic."""

    # Discord
    discord_token: str = Field(..., description="Token do bot Discord")
    discord_guild_id: int = Field(..., description="ID do servidor Discord")

    # Canais
    channel_vendas_id: int = Field(..., description="Canal de vendas")
    channel_logs_id: int = Field(..., description="Canal de logs")
    channel_pedidos_id: int = Field(..., description="Canal de pedidos")

    # Cargos
    role_admin_id: int = Field(..., description="Cargo de admin")
    role_cliente_id: int = Field(..., description="Cargo de cliente")
    role_vip_id: int = Field(..., description="Cargo VIP")

    # Tickets
    category_tickets_id: int = Field(..., description="Categoria dos tickets")

    # PostgreSQL
    database_url: str = Field(
        default="sqlite+aiosqlite:///robux_bot.db",
        description="URL de conexão do banco de dados (default: SQLite)",
    )

    # Mercado Pago
    mercadopago_access_token: Optional[str] = Field(
        default=None, description="Access token do Mercado Pago (opcional)"
    )
    mercadopago_webhook_secret: Optional[str] = Field(default=None)

    # PaySync
    paysync_api_key: Optional[str] = Field(
        default=None, description="API key do PaySync (ps_live_ ou ps_test_)"
    )

    # Gateway padrão: "mercadopago" ou "paysync"
    payment_gateway: str = Field(
        default="mercadopago", description="Gateway de pagamento padrão"
    )

    # Roblox
    roblox_cookie: str = Field(..., description="Cookie .ROBLOSECURITY")
    roblox_user_id: int = Field(..., description="ID do usuário Roblox")
    roblox_universe_id: int = Field(..., description="Universe ID do jogo")

    # Preços (em centavos)
    price_per_1000_robux: int = Field(
        default=1500, description="Preço por 1000 Robux em centavos"
    )
    roblox_tax_rate: float = Field(default=0.30, description="Taxa do Roblox")
    min_robux_amount: int = Field(default=100, description="Mínimo de Robux por compra")
    max_robux_amount: int = Field(
        default=100000, description="Máximo de Robux por compra"
    )

    # Configurações gerais
    pix_expiration_minutes: int = Field(default=30)
    ticket_expiration_hours: int = Field(default=24)
    debug: bool = Field(default=False)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # Ignora campos não definidos no .env

    @field_validator("roblox_cookie")
    @classmethod
    def validate_cookie(cls, v: str) -> str:
        """Valida formato do cookie do Roblox."""
        if not v or len(v) < 100:
            raise ValueError("Cookie do Roblox inválido ou muito curto")
        if "_|WARNING:-DO-NOT-SHARE" not in v:
            raise ValueError("Cookie do Roblox não parece ser válido")
        return v

    @field_validator("discord_token")
    @classmethod
    def validate_token(cls, v: str) -> str:
        """Valida formato do token do Discord."""
        if not v or len(v) < 50:
            raise ValueError("Token do Discord inválido")
        return v

    @field_validator("payment_gateway")
    @classmethod
    def validate_payment_gateway(cls, v: str, info) -> str:
        """Valida se pelo menos um gateway de pagamento está configurado."""
        mercadopago = info.data.get("mercadopago_access_token")
        paysync = info.data.get("paysync_api_key")

        if not mercadopago and not paysync:
            raise ValueError(
                "❌ Nenhum gateway de pagamento configurado! "
                "Configure MERCADOPAGO_ACCESS_TOKEN ou PAYSYNC_API_KEY no .env"
            )

        return v

    @property
    def price_per_robux_reais(self) -> float:
        """Retorna o preço por Robux em reais."""
        return (self.price_per_1000_robux / 100) / 1000

    def calculate_price(self, robux_amount: int) -> float:
        """Calcula o preço para uma quantidade de Robux."""
        return robux_amount * self.price_per_robux_reais

    def calculate_gamepass_price(self, robux_amount: int) -> int:
        """
        Calcula o preço do gamepass considerando a taxa do Roblox.
        Se você quer entregar X Robux, o gamepass precisa custar X / (1 - taxa).
        """
        return int(robux_amount / (1 - self.roblox_tax_rate))


@lru_cache()
def get_settings() -> Settings:
    """Retorna instância cacheada das configurações."""
    return Settings()
