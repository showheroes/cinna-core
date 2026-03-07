import os
import warnings
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, types as sa_types
from sqlalchemy.exc import SAWarning
import enum

# Suppress circular FK warning — mutual FKs between agent/agent_environment,
# session/input_task, and input_task/email_message are intentional.
warnings.filterwarnings(
    "ignore",
    message=r"Cannot correctly sort tables.*unresolvable cycles",
    category=SAWarning,
)

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
# target_metadata = None

from app.models import SQLModel  # noqa
from app.core.config import settings # noqa

target_metadata = SQLModel.metadata


def compare_type(context, inspected_column, metadata_column, inspected_type, metadata_type):
    """Ignore VARCHAR vs str Enum comparisons — SQLModel stores str enums as VARCHAR."""
    if isinstance(inspected_type, sa_types.VARCHAR) and isinstance(metadata_type, sa_types.Enum):
        if issubclass(metadata_type.enum_class, str) and issubclass(metadata_type.enum_class, enum.Enum):
            return False
    return None


# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_url():
    # Prefer a URL explicitly set on the config (e.g. by tests) over the app default
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    return str(settings.SQLALCHEMY_DATABASE_URI)


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_url()
    context.configure(
        url=url, target_metadata=target_metadata, literal_binds=True, compare_type=compare_type
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, compare_type=compare_type
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
