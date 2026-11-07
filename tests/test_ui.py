from pathlib import Path

from streamlit.testing.v1 import AppTest

from agent_pentest.storage.database import Database
from worker import process_next


def test_ui_enqueue_rerun_view_and_download(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    monkeypatch.setenv("AGENT_PENTEST_RUNTIME", str(runtime))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=15).run()
    assert not app.exception
    start = next(button for button in app.button if button.label == "Start Campaign")
    start.click().run()
    assert not app.exception
    db = Database(runtime)
    assert len(db.list_campaigns()) == 1
    app.run()
    next(b for b in app.button if b.label == "Start Campaign").click().run()
    assert len(db.list_campaigns()) == 1
    campaign_id = process_next(db)
    app.run()
    assert not app.exception
    assert db.detail(campaign_id)["status"] == "COMPLETED"
    assert any("OBSERVED" in item.value for item in app.markdown)
    assert len(app.get("download_button")) == 2
    assert process_next(db) is None

