from pathlib import Path

import pytest

from agent_pentest.control.catalogue import Catalogue
from agent_pentest.service import submit_campaign
from agent_pentest.storage.database import Database

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def catalogue():
    return Catalogue(ROOT)


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "runtime")
    database.initialize()
    return database


@pytest.fixture
def submit(db, catalogue):
    def enqueue(profile="vulnerable", request_key="test-request"):
        return submit_campaign(db, catalogue, "fake-hma", profile, "ASI02-HMA-001", request_key)[0]
    return enqueue

