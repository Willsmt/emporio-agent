import pytest

from emporio.data.etl import build_database
from emporio.tools.db import connect_readonly


@pytest.fixture(scope="session")
def db_path(tmp_path_factory):
    return build_database(db_path=tmp_path_factory.mktemp("store") / "store.db")


@pytest.fixture
def conn(db_path):
    connection = connect_readonly(db_path)
    yield connection
    connection.close()
