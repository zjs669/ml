from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """全局声明式基类。所有表通过 Alembic 迁移创建，禁止启动时 create_all。"""

    pass
