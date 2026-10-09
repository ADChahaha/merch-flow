from sqlalchemy import create_engine, text
from app import db


def test_upgrade_assigns_stable_uids_to_existing_products(monkeypatch):
    engine = create_engine('sqlite:///:memory:')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE agent_jobs (id INTEGER PRIMARY KEY)'))
        connection.execute(text('CREATE TABLE agent_products (id INTEGER PRIMARY KEY, name TEXT)'))
        connection.execute(text("INSERT INTO agent_products VALUES (1, 'A'), (2, 'B')"))
    monkeypatch.setattr(db, 'engine', engine)
    db._ensure_columns()
    with engine.connect() as connection:
        before = connection.execute(text('SELECT id, uid FROM agent_products ORDER BY id')).all()
    assert len({uid for _, uid in before}) == 2
    assert all(len(uid) == 32 for _, uid in before)
    db._ensure_columns()
    with engine.connect() as connection:
        assert connection.execute(text('SELECT id, uid FROM agent_products ORDER BY id')).all() == before


def test_startup_marks_interrupted_jobs_retryable(monkeypatch):
    from app.db import Base
    from app.models import AgentJob, AgentProduct
    from sqlalchemy.orm import Session
    from app.agent import jobs
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        row = AgentJob(url='https://example.com', status='running')
        row.products.append(AgentProduct(name='keep'))
        session.add(row)
        session.commit()
    monkeypatch.setattr(db, 'engine', engine)
    monkeypatch.setattr(jobs, 'backfill_job_usage', lambda: 0)
    db.init_db()
    with Session(engine) as session:
        row = session.get(AgentJob, 1)
        assert row.status == 'error' and '中断' in row.error
        assert len(row.products) == 1


def test_decimal_prices_work_with_legacy_sqlite_integer_column():
    from app.models import AgentJob, AgentProduct
    from sqlalchemy import MetaData, Integer
    from sqlalchemy.orm import Session
    engine = create_engine('sqlite:///:memory:')
    legacy = MetaData()
    AgentJob.__table__.to_metadata(legacy)
    products = AgentProduct.__table__.to_metadata(legacy)
    products.c.price.type = Integer()
    legacy.create_all(engine)
    with Session(engine) as session:
        row = AgentJob(url='https://example.com', status='done')
        row.products.append(AgentProduct(name='A', price=12.99))
        session.add(row)
        session.commit()
    with Session(engine) as session:
        assert session.get(AgentProduct, 1).price == 12.99
