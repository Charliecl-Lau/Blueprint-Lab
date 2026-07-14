from alembic import command
from sqlalchemy import create_engine, text

from backend.tests.integration.test_research_migration import LEGACY_DDL, alembic_config


def test_run_tracking_migration_preserves_legacy_usage_as_null(postgres_url):
    engine = create_engine(postgres_url)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
        connection.execute(text(LEGACY_DDL))
        connection.execute(
            text(
                "INSERT INTO experiments VALUES "
                "(1,'ENGR 101','Statics','Apply equilibrium','quiz','introductory',1,30,now())"
            )
        )
        connection.execute(
            text(
                "INSERT INTO conditions VALUES "
                "(1,1,'openai',false,false,false,false,'{}','baseline')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO generations VALUES "
                "(1,1,1,'completed','gemini','v1',100,NULL,now(),now())"
            )
        )

    config = alembic_config(postgres_url)
    command.upgrade(config, "20260712_01")
    command.upgrade(config, "20260714_01")

    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT input_tokens, output_tokens, total_tokens, model_call_count "
                "FROM runs WHERE id=1"
            )
        ).mappings().one()

    assert dict(row) == {
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "model_call_count": None,
    }
