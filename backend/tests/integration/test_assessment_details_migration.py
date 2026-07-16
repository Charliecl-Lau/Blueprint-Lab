from alembic import command
from sqlalchemy import create_engine, text

from backend.tests.integration.test_research_migration import LEGACY_DDL, alembic_config


def test_assessment_details_migration_backfills_existing_experiments(postgres_url):
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

    config = alembic_config(postgres_url)
    command.upgrade(config, "20260716_01")

    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT cognitive_demand, additional_instruction "
                "FROM experiments WHERE id = 1"
            )
        ).mappings().one()

    assert dict(row) == {
        "cognitive_demand": "remember_understand",
        "additional_instruction": None,
    }
