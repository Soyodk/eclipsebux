from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from typing import Optional
from contextlib import asynccontextmanager
from loguru import logger
import ssl
import os


class Base(DeclarativeBase):
    """Classe base para todos os modelos SQLAlchemy."""

    pass


class Database:
    """Gerenciador de conexão PostgreSQL assíncrono."""

    _instance: Optional["Database"] = None
    _engine = None
    _session_factory: Optional[async_sessionmaker[AsyncSession]] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def connect(self, database_url: str) -> None:
        """Conecta ao PostgreSQL."""
        try:
            # Garante que usa o driver asyncpg
            if database_url.startswith("postgres://"):
                database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
            elif database_url.startswith("postgresql://") and "+asyncpg" not in database_url:
                database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

            # Remove parâmetros de query incompatíveis com asyncpg (ex: sslmode, sslrootcert)
            from urllib.parse import urlparse, urlencode, parse_qs, urlunparse
            parsed = urlparse(database_url)
            query_params = parse_qs(parsed.query, keep_blank_values=True)
            # asyncpg lida com SSL via connect_args, não via query string
            incompatible = {"sslmode", "sslrootcert", "sslcert", "sslkey"}
            ssl_mode = query_params.pop("sslmode", ["disable"])[0]
            for key in incompatible:
                query_params.pop(key, None)
            clean_query = urlencode({k: v[0] for k, v in query_params.items()})
            database_url = urlunparse(parsed._replace(query=clean_query))

            # Configura SSL se certificados existirem
            ssl_context = None
            cert_path = os.path.join(os.getcwd(), "certs")
            ca_cert = os.path.join(cert_path, "ca-certificate.crt")
            client_cert = os.path.join(cert_path, "certificate.pem")
            client_key = os.path.join(cert_path, "private-key.key")

            if all(os.path.exists(f) for f in [ca_cert, client_cert, client_key]):
                ssl_context = ssl.create_default_context(cafile=ca_cert)
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_REQUIRED
                ssl_context.load_cert_chain(certfile=client_cert, keyfile=client_key)
                logger.info("🔒 Usando certificados SSL para PostgreSQL")

            # Cria engine assíncrono
            connect_args = {}
            if ssl_context:
                connect_args["ssl"] = ssl_context

            self._engine = create_async_engine(
                database_url,
                echo=False,  # True para debug SQL
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                connect_args=connect_args,
            )

            # Cria factory de sessões
            self._session_factory = async_sessionmaker(
                bind=self._engine, class_=AsyncSession, expire_on_commit=False
            )

            # Testa a conexão
            async with self._engine.begin() as conn:
                await conn.run_sync(lambda c: None)

            logger.success("✅ Conectado ao PostgreSQL")

            # Cria tabelas
            await self._create_tables()

        except Exception as e:
            logger.error(f"❌ Erro ao conectar ao PostgreSQL: {e}")
            raise

    async def _create_tables(self) -> None:
        """Cria todas as tabelas no banco de dados."""
        from src.database.models import Base as ModelsBase

        async with self._engine.begin() as conn:
            await conn.run_sync(ModelsBase.metadata.create_all)

        logger.info("📊 Tabelas do PostgreSQL criadas/verificadas")

    async def disconnect(self) -> None:
        """Desconecta do PostgreSQL."""
        if self._engine:
            await self._engine.dispose()
            logger.info("🔌 Desconectado do PostgreSQL")

    def get_session(self) -> AsyncSession:
        """Retorna uma nova sessão do banco."""
        if self._session_factory is None:
            raise RuntimeError("Database não conectado. Chame connect() primeiro.")
        return self._session_factory()

    @asynccontextmanager
    async def session(self):
        """Context manager para sessões com auto-commit/rollback."""
        session = self.get_session()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    @property
    def engine(self):
        """Retorna o engine do SQLAlchemy."""
        return self._engine


# Instância global
db = Database()
