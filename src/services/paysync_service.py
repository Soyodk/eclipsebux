import aiohttp
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple
from loguru import logger
from src.config import get_settings


class PaySyncService:
    """Serviço de integração com PaySync para pagamentos PIX."""

    BASE_URL = "https://api.usepaysync.com"

    def __init__(self):
        settings = get_settings()
        self.api_key = settings.paysync_api_key
        self._session: Optional[aiohttp.ClientSession] = None
        self._expiration_minutes = settings.pix_expiration_minutes

    async def _get_session(self) -> aiohttp.ClientSession:
        """Retorna sessão HTTP reutilizável."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
            )
        return self._session

    async def close(self) -> None:
        """Fecha a sessão HTTP."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(
        self, method: str, endpoint: str, **kwargs
    ) -> Tuple[bool, Dict[str, Any]]:
        """Faz uma requisição à API PaySync."""
        try:
            session = await self._get_session()
            url = f"{self.BASE_URL}{endpoint}"

            async with session.request(method, url, **kwargs) as response:
                data = await response.json()

                if response.status in [200, 201]:
                    return True, data
                else:
                    logger.error(f"❌ PaySync API Error: {response.status} - {data}")
                    return False, data

        except Exception as e:
            logger.error(f"❌ Erro na requisição PaySync: {e}")
            return False, {"error": str(e)}

    async def create_pix_charge(
        self,
        amount_cents: int,
        order_id: str,
        description: str,
        customer_name: str = "Cliente",
        customer_email: str = "cliente@email.com",
        callback_url: Optional[str] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Cria uma cobrança PIX standalone.

        Args:
            amount_cents: Valor em centavos (ex: 4990 = R$ 49,90)
            order_id: ID do pedido
            description: Descrição do pagamento
            customer_name: Nome do cliente
            customer_email: Email do cliente
            callback_url: URL para webhook quando pago

        Returns:
            Tuple[bool, Dict]: (sucesso, dados do pagamento)
        """
        try:
            if amount_cents < 100:
                return False, {"error": "Valor mínimo é R$ 1.00"}

            payload = {
                "valueCents": amount_cents,
                "description": description,
                "customer": {
                    "name": customer_name,
                    "email": customer_email,
                    "externalId": order_id,
                },
            }

            if callback_url:
                payload["callbackUrl"] = callback_url

            success, response = await self._request(
                "POST", "/v1/charges", json=payload
            )

            if not success:
                logger.error(f"❌ Erro ao criar cobrança PIX: {response}")
                return False, response

            # Extrai dados do PIX
            pix_data = response.get("pix", {})

            result = {
                "payment_id": response.get("paymentId", ""),
                "status": response.get("status", "pending"),
                "pix_code": pix_data.get("brCode", ""),
                "pix_qrcode_url": pix_data.get("qrCodeImage", ""),
                "amount": response.get("amountCents", amount_cents),
                "expires_at": response.get("expiresAt", ""),
                "external_reference": order_id,
            }

            logger.success(
                f"💳 Pagamento PIX PaySync criado: {result['payment_id']} - R${amount_cents/100:.2f}"
            )
            return True, result

        except Exception as e:
            logger.error(f"❌ Exceção ao criar PIX PaySync: {e}")
            return False, {"error": str(e)}

    async def create_payment(
        self,
        amount_cents: int,
        order_id: str,
        description: str,
        customer_name: str = "Cliente",
        customer_email: str = "cliente@email.com",
        callback_url: Optional[str] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Cria um pagamento PIX usando a API de pagamentos (compatível com produtos).

        Args:
            amount_cents: Valor em centavos
            order_id: ID do pedido
            description: Descrição
            customer_name: Nome do cliente
            customer_email: Email do cliente
            callback_url: URL para webhook

        Returns:
            Tuple[bool, Dict]: (sucesso, dados do pagamento)
        """
        # Usa a mesma implementação de cobrança standalone
        return await self.create_pix_charge(
            amount_cents, order_id, description, customer_name, customer_email, callback_url
        )

    async def check_payment_status(
        self, payment_id: str
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Verifica status de um pagamento.

        Returns:
            Tuple[str, Dict]: (status, dados do pagamento)
                status pode ser: "pending", "paid", "expired", "refunded"
        """
        try:
            success, response = await self._request("GET", f"/v1/charges/{payment_id}")

            if success:
                status = response.get("status", "unknown")
                return status, response
            else:
                return "error", response

        except Exception as e:
            logger.error(f"❌ Erro ao verificar pagamento PaySync: {e}")
            return "error", {"error": str(e)}

    async def list_payments(
        self, limit: int = 50, offset: int = 0
    ) -> Tuple[bool, Dict[str, Any]]:
        """Lista pagamentos."""
        try:
            params = {"limit": min(limit, 100), "offset": offset}
            success, response = await self._request(
                "GET", "/v1/charges", params=params
            )
            return success, response

        except Exception as e:
            logger.error(f"❌ Erro ao listar pagamentos PaySync: {e}")
            return False, {"error": str(e)}

    async def validate_api_key(self) -> Tuple[bool, str]:
        """
        Valida se a chave API está funcionando.

        Returns:
            Tuple[bool, str]: (válida, mensagem)
        """
        try:
            success, response = await self._request("GET", "/v1/charges?limit=1")

            if success:
                return True, "✅ API PaySync válida"
            else:
                error = response.get("error", "Erro desconhecido")
                return False, f"❌ Erro na API PaySync: {error}"

        except Exception as e:
            return False, f"❌ Erro ao validar API PaySync: {e}"


# Instância global
paysync_service = PaySyncService()
