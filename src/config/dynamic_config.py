from typing import Any, Optional
from loguru import logger


class DynamicConfig:
    """
    Gerenciador de configurações dinâmicas.
    Lê do banco de dados primeiro, com fallback para as settings do .env.
    """

    _cache: dict = {}
    _loaded: bool = False

    @classmethod
    async def load(cls) -> None:
        """Carrega todas as configurações do banco."""
        try:
            from src.database import ConfigRepository
            cls._cache = await ConfigRepository.get_all()
            cls._loaded = True
            logger.info(f"⚙️ Config dinâmica carregada: {len(cls._cache)} chaves")
        except Exception as e:
            logger.warning(f"⚠️ Não foi possível carregar config dinâmica: {e}")
            cls._cache = {}

    @classmethod
    async def get(cls, key: str, default=None) -> Any:
        """Busca uma configuração. Banco > cache."""
        if key in cls._cache:
            return cls._cache[key]
        return default

    @classmethod
    async def set(cls, key: str, value: Any, updated_by: int = None) -> None:
        """Define uma configuração no banco e atualiza o cache."""
        from src.database import ConfigRepository
        await ConfigRepository.set(key, value, updated_by=updated_by)
        cls._cache[key] = value

    @classmethod
    async def delete(cls, key: str) -> None:
        """Remove uma configuração do banco e do cache."""
        from src.database import ConfigRepository
        await ConfigRepository.delete(key)
        cls._cache.pop(key, None)

    # ── Helpers tipados ─────────────────────────────────────────────────

    @classmethod
    async def get_int(cls, key: str, fallback_from_settings: str = None) -> Optional[int]:
        val = await cls.get(key)
        if val is not None:
            return int(val)
        if fallback_from_settings:
            from src.config.settings import get_settings
            return getattr(get_settings(), fallback_from_settings, None)
        return None

    @classmethod
    async def get_float(cls, key: str, fallback_from_settings: str = None) -> Optional[float]:
        val = await cls.get(key)
        if val is not None:
            return float(val)
        if fallback_from_settings:
            from src.config.settings import get_settings
            return getattr(get_settings(), fallback_from_settings, None)
        return None

    @classmethod
    async def get_str(cls, key: str, fallback_from_settings: str = None) -> Optional[str]:
        val = await cls.get(key)
        if val is not None:
            return str(val)
        if fallback_from_settings:
            from src.config.settings import get_settings
            return getattr(get_settings(), fallback_from_settings, None)
        return None

    # ── Atalhos de config específicos ───────────────────────────────────

    @classmethod
    async def operation_mode(cls) -> str:
        """Retorna o modo de operação: auto | semi_auto | manual"""
        return await cls.get("operation_mode", "auto")

    @classmethod
    async def price_per_1000(cls) -> int:
        """Preço por 1000 Robux em centavos."""
        return await cls.get_int("price_per_1000_robux", "price_per_1000_robux") or 1500

    @classmethod
    async def min_robux(cls) -> int:
        return await cls.get_int("min_robux_amount", "min_robux_amount") or 100

    @classmethod
    async def max_robux(cls) -> int:
        return await cls.get_int("max_robux_amount", "max_robux_amount") or 100000

    @classmethod
    async def daily_limit_robux(cls) -> Optional[int]:
        """Limite diário de Robux vendidos (None = sem limite)."""
        return await cls.get_int("daily_limit_robux")

    @classmethod
    async def daily_limit_brl(cls) -> Optional[float]:
        """Limite diário em R$ (None = sem limite)."""
        return await cls.get_float("daily_limit_brl")

    @classmethod
    async def channel_vendas_id(cls) -> Optional[int]:
        return await cls.get_int("channel_vendas_id", "channel_vendas_id")

    @classmethod
    async def channel_logs_id(cls) -> Optional[int]:
        return await cls.get_int("channel_logs_id", "channel_logs_id")

    @classmethod
    async def channel_pedidos_id(cls) -> Optional[int]:
        return await cls.get_int("channel_pedidos_id", "channel_pedidos_id")

    @classmethod
    async def category_tickets_id(cls) -> Optional[int]:
        return await cls.get_int("category_tickets_id", "category_tickets_id")

    @classmethod
    async def role_admin_id(cls) -> Optional[int]:
        return await cls.get_int("role_admin_id", "role_admin_id")

    @classmethod
    async def role_cliente_id(cls) -> Optional[int]:
        return await cls.get_int("role_cliente_id", "role_cliente_id")

    @classmethod
    async def role_vip_id(cls) -> Optional[int]:
        return await cls.get_int("role_vip_id", "role_vip_id")

    # ── Embed da loja (painel) ───────────────────────────────────────────

    @classmethod
    async def shop_embed(cls) -> dict:
        return await cls.get("shop_embed") or {
            "title": "🏪 Loja Oficial de Robux",
            "description": "Compre Robux de forma **rápida**, **segura** e com **entrega automática** via Gamepass!",
            "color": 0x00D166,
            "banner_url": "",
            "footer": "🕐 Atendimento 24/7 • ⭐ +1000 clientes satisfeitos",
            "thumbnail_url": "",
        }

    # ── Embed do ticket (boas-vindas) ────────────────────────────────────

    @classmethod
    async def ticket_embed(cls) -> dict:
        return await cls.get("ticket_embed") or {
            "title": "🛒 Bem-vindo à Loja de Robux!",
            "description": "Olá {mention}! 👋\n\nEstamos felizes em te atender! Aqui você pode comprar Robux de forma **rápida**, **segura** e **automática**.",
            "color": 0x5865F2,
            "banner_url": "",
            "footer": "Atendimento 24/7",
            "show_price_table": True,
            "show_steps": True,
        }

    @classmethod
    async def robux_stock_display(cls) -> bool:
        """Se deve mostrar o estoque atual de Robux no painel."""
        val = await cls.get("robux_stock_display")
        return bool(val) if val is not None else False


dynamic_config = DynamicConfig()
