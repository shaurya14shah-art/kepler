"""Every test gets its own Kepler home, so nothing touches your real ~/.kepler (bot lessons, cached models, library)."""
import os
import tempfile

os.environ.setdefault("KEPLER_DB", os.path.join(tempfile.mkdtemp(prefix="kepler-test-"), "kepler.db"))  # never ~/.kepler
# no demo data unless a test seeds it itself: starting the app on a demo workspace seeds 21 days in a background thread
# that outlives the test, and a later test that switches databases would find it writing into its own
os.environ.setdefault("KEPLER_DEMO", "0")
# ...and no automatic retraining in a background thread either (tests call api.retrain_due directly)
os.environ.setdefault("KEPLER_AUTO_TRAIN", "off")

import pytest  # noqa: E402

from kepler import device
from kepler.bot import model


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path_factory, monkeypatch):
    home = tmp_path_factory.mktemp("kepler-home")
    monkeypatch.setattr(device, "HOME", home)
    monkeypatch.setenv("KEPLER_WEB", "off")              # tests never reach the internet
    monkeypatch.delenv("KEPLER_LIBRARY", raising=False)  # … nor your real library
    monkeypatch.setattr(model, "_cache", None)
    return home
