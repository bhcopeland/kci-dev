import json
from unittest.mock import Mock

import pytest
import requests

from kcidev import KciDevError, KernelCIClient
from kcidev.libs import maestro_common

CFG = {
    "test": {
        "api": "https://api.example.org/",
        "pipeline": "https://pipeline.example.org/",
        "token": "secret",
    }
}


def _client():
    return KernelCIClient(cfg=CFG, instance="test")


def test_client_uses_configured_default_instance(monkeypatch):
    cfg = {"default_instance": "test", **CFG}
    response = Mock(status_code=200)
    response.json.return_value = {"id": "n1"}
    get = Mock(return_value=response)
    monkeypatch.setattr(maestro_common.kcidev_session, "get", get)

    client = KernelCIClient(cfg=cfg)

    assert client.instance == "test"
    assert client.get_node("n1") == {"id": "n1"}
    assert get.call_args[0][0] == "https://api.example.org/latest/node/n1"


def test_get_node_uses_configured_api_url(monkeypatch):
    response = Mock(status_code=200)
    response.json.return_value = {"id": "n1", "state": "done"}
    get = Mock(return_value=response)
    monkeypatch.setattr(maestro_common.kcidev_session, "get", get)
    assert _client().get_node("n1") == {"id": "n1", "state": "done"}
    assert get.call_args[0][0] == "https://api.example.org/latest/node/n1"


def test_get_node_without_api_url_raises():
    with pytest.raises(KciDevError, match="api URL"):
        KernelCIClient().get_node("n1")


def test_get_node_http_error_raises_library_error(monkeypatch):
    response = Mock(status_code=404)
    response.json.return_value = {"detail": "Node not found"}
    response.raise_for_status.side_effect = requests.exceptions.HTTPError(
        response=response
    )
    monkeypatch.setattr(
        maestro_common.kcidev_session, "get", Mock(return_value=response)
    )
    with pytest.raises(KciDevError, match="Maestro node request failed"):
        _client().get_node("n1")


def test_get_node_plain_text_http_error_raises_library_error(monkeypatch):
    response = Mock(
        status_code=503,
        url="https://api.example.org/latest/node/n1",
        text="service unavailable",
    )
    response.json.side_effect = requests.exceptions.JSONDecodeError("bad", "", 0)
    response.raise_for_status.side_effect = requests.exceptions.HTTPError(
        response=response
    )
    monkeypatch.setattr(
        maestro_common.kcidev_session, "get", Mock(return_value=response)
    )

    with pytest.raises(KciDevError, match="Maestro node request failed"):
        _client().get_node("n1")


def test_get_nodes_passes_pagination_and_filters(monkeypatch):
    response = Mock(status_code=200)
    response.json.return_value = []
    get = Mock(return_value=response)
    monkeypatch.setattr(maestro_common.kcidev_session, "get", get)
    _client().get_nodes(limit=5, offset=10, filters=["name=checkout"])
    assert get.call_args[0][0] == "https://api.example.org/latest/nodes/fast"
    assert get.call_args.kwargs["params"] == [
        ("limit", 5),
        ("offset", 10),
        ("name", "checkout"),
    ]
    assert get.call_args.kwargs["timeout"] == 30


def test_retry_job_posts_with_token(monkeypatch):
    response = Mock(status_code=200)
    response.json.return_value = {"message": "OK"}
    post = Mock(return_value=response)
    monkeypatch.setattr(maestro_common.kcidev_session, "post", post)
    assert _client().retry_job("n1") == {"message": "OK"}
    assert post.call_args[0][0] == "https://pipeline.example.org/api/jobretry"
    assert post.call_args.kwargs["headers"]["Authorization"] == "secret"


def test_pipeline_url_does_not_require_trailing_slash(monkeypatch):
    cfg = {
        "test": {
            "pipeline": "https://pipeline.example.org",
            "token": "secret",
        }
    }
    response = Mock(status_code=200)
    response.json.return_value = {"message": "OK"}
    post = Mock(return_value=response)
    monkeypatch.setattr(maestro_common.kcidev_session, "post", post)

    KernelCIClient(cfg=cfg, instance="test").retry_job("n1")

    assert post.call_args[0][0] == "https://pipeline.example.org/api/jobretry"


def test_retry_job_failure_raises(monkeypatch):
    post = Mock(side_effect=requests.exceptions.ConnectionError("no route"))
    monkeypatch.setattr(maestro_common.kcidev_session, "post", post)
    with pytest.raises(KciDevError, match="retry failed"):
        _client().retry_job("n1")


def test_trigger_checkout_posts_payload(monkeypatch):
    response = Mock(status_code=200)
    response.json.return_value = {"treeid": "t1"}
    post = Mock(return_value=response)
    monkeypatch.setattr(maestro_common.kcidev_session, "post", post)
    result = _client().trigger_checkout(
        "https://git.example.org/linux.git", "master", "deadbeef", ["baseline-arm64"]
    )
    assert result == {"treeid": "t1"}
    body = json.loads(post.call_args.kwargs["data"])
    assert body == {
        "url": "https://git.example.org/linux.git",
        "branch": "master",
        "commit": "deadbeef",
        "jobfilter": ["baseline-arm64"],
    }


def test_trigger_checkout_includes_platform_filter(monkeypatch):
    response = Mock(status_code=200)
    response.json.return_value = {"treeid": "t1"}
    post = Mock(return_value=response)
    monkeypatch.setattr(maestro_common.kcidev_session, "post", post)
    _client().trigger_checkout(
        "https://git.example.org/linux.git",
        "master",
        "deadbeef",
        ["baseline-arm64"],
        platform_filter=["qemu-arm64"],
    )
    body = json.loads(post.call_args.kwargs["data"])
    assert body["platformfilter"] == ["qemu-arm64"]


def test_trigger_checkout_requires_token():
    cfg = {"test": {"pipeline": "https://pipeline.example.org/"}}
    with pytest.raises(KciDevError, match="token"):
        KernelCIClient(cfg=cfg, instance="test").trigger_checkout(
            "https://git.example.org/linux.git", "master", "deadbeef", ["baseline"]
        )


def test_trigger_patchset_posts_payload(monkeypatch):
    response = Mock(status_code=200)
    response.json.return_value = {"message": "OK", "node": {"treeid": "t1"}}
    post = Mock(return_value=response)
    monkeypatch.setattr(maestro_common.kcidev_session, "post", post)
    result = _client().trigger_patchset(
        "0" * 24, patches=["patch content"], job_filter=["baseline-arm64"]
    )
    assert result == {"message": "OK", "node": {"treeid": "t1"}}
    assert post.call_args[0][0] == "https://pipeline.example.org/api/patchset"
    body = json.loads(post.call_args.kwargs["data"])
    assert body == {
        "nodeid": "0" * 24,
        "patch": ["patch content"],
        "jobfilter": ["baseline-arm64"],
    }


def test_trigger_patchset_posts_patch_urls(monkeypatch):
    response = Mock(status_code=200)
    response.json.return_value = {"message": "OK", "node": {}}
    post = Mock(return_value=response)
    monkeypatch.setattr(maestro_common.kcidev_session, "post", post)
    _client().trigger_patchset(
        "0" * 24,
        patchurls=["https://patchwork.kernel.org/series/1/mbox/"],
        platform_filter=["qemu-arm64"],
    )
    body = json.loads(post.call_args.kwargs["data"])
    assert body["patchurl"] == ["https://patchwork.kernel.org/series/1/mbox/"]
    assert body["platformfilter"] == ["qemu-arm64"]


def test_trigger_patchset_rejects_both_patch_forms():
    with pytest.raises(KciDevError, match="xactly one"):
        _client().trigger_patchset(
            "0" * 24,
            patches=["patch content"],
            patchurls=["https://patchwork.kernel.org/series/1/mbox/"],
        )


def test_trigger_patchset_requires_a_patch_form():
    with pytest.raises(KciDevError, match="xactly one"):
        _client().trigger_patchset("0" * 24)


def test_trigger_patchset_failure_raises(monkeypatch):
    post = Mock(side_effect=requests.exceptions.ConnectionError("no route"))
    monkeypatch.setattr(maestro_common.kcidev_session, "post", post)
    with pytest.raises(KciDevError, match="patchset failed"):
        _client().trigger_patchset("0" * 24, patches=["patch content"])


def test_get_tree_report_uses_integer_age_defaults(monkeypatch):
    client = _client()
    request = Mock(return_value={})
    monkeypatch.setattr(client, "_dashboard_request", request)

    client.get_tree_report("maestro", "main", "https://example.com/linux.git")

    assert request.call_args.args[-2:] == (24, 0)


@pytest.mark.parametrize(
    ("method_name", "result_id"),
    [("get_build_issues", "build-id"), ("get_boot_issues", "test-id")],
)
def test_get_issues_forwards_error_verbosity(monkeypatch, method_name, result_id):
    client = _client()
    request = Mock(return_value=[])
    monkeypatch.setattr(client, "_dashboard_request", request)

    getattr(client, method_name)(result_id, error_verbose=False)

    assert request.call_args.args[-2:] == (True, False)


def test_compare_results_continues_without_tree_history(monkeypatch):
    client = _client()
    monkeypatch.setattr(client, "get_builds", Mock(return_value={"builds": []}))
    monkeypatch.setattr(client, "get_boots", Mock(return_value={"boots": []}))
    monkeypatch.setattr(client, "get_tests", Mock(return_value={"tests": []}))
    monkeypatch.setattr(
        client,
        "get_tree_report",
        Mock(side_effect=KciDevError("tree report unavailable")),
    )

    report = client.compare_results(
        "base", "head", "https://example.com/linux.git", "main"
    )

    assert report["incomplete"] is True
    assert report["items"] == []


def test_compare_results_only_fetches_issues_when_requested(monkeypatch):
    client = _client()
    passing = {
        "id": "base-test",
        "status": "PASS",
        "path": "suite.case",
        "environment_misc": {"platform": "qemu"},
    }
    failing = {**passing, "id": "head-test", "status": "FAIL"}
    monkeypatch.setattr(client, "get_builds", Mock(return_value={"builds": []}))
    monkeypatch.setattr(client, "get_boots", Mock(return_value={"boots": []}))
    get_tests = Mock(side_effect=[{"tests": [passing]}, {"tests": [failing]}] * 2)
    monkeypatch.setattr(client, "get_tests", get_tests)
    monkeypatch.setattr(client, "get_tree_report", Mock(return_value={}))
    get_issues = Mock(return_value=[{"id": "issue-1"}])
    monkeypatch.setattr(client, "get_boot_issues", get_issues)

    report = client.compare_results(
        "base", "head", "https://example.com/linux.git", "main"
    )

    assert report["items"][0]["known_issues"] == []
    get_issues.assert_not_called()

    report = client.compare_results(
        "base",
        "head",
        "https://example.com/linux.git",
        "main",
        include_issues=True,
    )

    assert report["items"][0]["known_issues"] == ["issue-1"]
    get_issues.assert_called_once_with("head-test", error_verbose=False)
