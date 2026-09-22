import asyncio

import yaml

import app


def test_new_template_job_is_merged_with_saved_schedule(tmp_path, monkeypatch):
    template = tmp_path / "template.yaml"
    saved = tmp_path / "jobs.yaml"
    template.write_text(
        yaml.safe_dump({"jobs": {
            "paper_daily": {"cron": "0 8 * * *", "body": {"no_llm": False}},
            "paper_fulltext": {"cron": "0 10 * * *", "body": {"limit": 3}},
        }}),
        encoding="utf-8",
    )
    saved.write_text(
        yaml.safe_dump({"jobs": {"paper_daily": {"cron": "30 7 * * *", "body": {"no_llm": True}}}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("JOBS_CONFIG", str(saved))
    monkeypatch.setenv("JOBS_TEMPLATE", str(template))

    jobs = app.load_config()["jobs"]
    assert jobs["paper_daily"] == {"cron": "30 7 * * *", "body": {"no_llm": True}}
    assert jobs["paper_fulltext"] == {"cron": "0 10 * * *", "body": {"limit": 3}}


def test_partial_result_is_visible_in_scheduler_status(monkeypatch):
    class Response:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"partial": True, "summarized": {"failed": 1}}

    class Client:
        def __init__(self, timeout):
            assert timeout == 1800

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def request(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(app.httpx, "AsyncClient", Client)
    app.job_state.clear()
    result = asyncio.run(app.invoke("paper_fulltext", {"url": "http://paper-agent/run", "timeout_seconds": 1800}))
    assert result["partial"] is True
    assert app.job_state["paper_fulltext"]["last_status"] == "partial"
