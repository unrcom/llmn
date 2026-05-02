from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()
SCHEMA = "llmn"


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": SCHEMA}

    id            = Column(Integer, primary_key=True)
    username      = Column(String(100), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    role          = Column(String(20), nullable=False, default="user")
    created_at    = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    @property
    def is_admin(self):
        return self.role == "admin"


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = {"schema": SCHEMA}

    id         = Column(Integer, primary_key=True)
    users_id   = Column(Integer, ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), nullable=False)
    token      = Column(Text, nullable=False, unique=True)
    expires_at = Column(TIMESTAMP, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = {"schema": SCHEMA}

    id           = Column(Integer, primary_key=True)
    name         = Column(String(100), nullable=False, unique=True)
    display_name = Column(String(100), nullable=False)
    created_at   = Column(TIMESTAMP, server_default=func.now(), nullable=False)


class Model(Base):
    __tablename__ = "models"
    __table_args__ = {"schema": SCHEMA}

    id               = Column(Integer, primary_key=True)
    name             = Column(String(255), nullable=False)
    display_name     = Column(String(255), nullable=False)
    model_type       = Column(String(20), nullable=False, default="base")
    adapter_path     = Column(Text, nullable=True)
    parent_models_id = Column(Integer, ForeignKey(f"{SCHEMA}.models.id"), nullable=True)
    trained_at       = Column(TIMESTAMP, nullable=True)
    created_at       = Column(TIMESTAMP, server_default=func.now(), nullable=False)


class SystemPrompt(Base):
    __tablename__ = "system_prompts"
    __table_args__ = {"schema": SCHEMA}

    id         = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey(f"{SCHEMA}.projects.id", ondelete="CASCADE"), nullable=False)
    name       = Column(String(100), nullable=False)
    content    = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)


class QuestionSet(Base):
    __tablename__ = "question_sets"
    __table_args__ = {"schema": SCHEMA}

    id                = Column(Integer, primary_key=True)
    project_id        = Column(Integer, ForeignKey(f"{SCHEMA}.projects.id", ondelete="CASCADE"), nullable=False)
    system_prompts_id = Column(Integer, ForeignKey(f"{SCHEMA}.system_prompts.id"), nullable=True)
    name              = Column(String(100), nullable=False)
    status            = Column(String(20), nullable=False, default="draft")
    created_at        = Column(TIMESTAMP, server_default=func.now(), nullable=False)


class FtConversation(Base):
    __tablename__ = "ft_conversations"
    __table_args__ = {"schema": SCHEMA}

    id         = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey(f"{SCHEMA}.projects.id", ondelete="CASCADE"), nullable=False)
    is_base    = Column(Boolean, nullable=False, default=False)
    base_id    = Column(Integer, ForeignKey(f"{SCHEMA}.ft_conversations.id"), nullable=True)
    split      = Column(String(10), nullable=False, default="train")
    messages   = Column(JSONB, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
