import pytest
from tests.test_superset_api import *  # noqa: F401,F403
from tests.test_superset_api import live_app as _la  # noqa: F401


@pytest.mark.parametrize("n", range(60))
def test_repro(n, db, world, fake, live_app):
    pass
