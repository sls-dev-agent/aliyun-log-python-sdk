# encoding: utf-8

from __future__ import absolute_import

import json
import re

import pytest
import responses

from aliyun.log import LogException, ResourcePolicyResourceType
from tests._helpers.fakes import make_client, mock_sls_response


PROJECT = "resource-policy-project"
LOGSTORE = "resource-policy-logstore"
POLICY = '{"Version":"1","Statement":[]}'


@responses.activate
def test_put_resource_policy_sends_project_and_logstore_bodies():
    client = make_client(endpoint="cn-mock.example.com", project=PROJECT)
    captured = []

    def callback(request):
        captured.append((json.loads(request.body.decode("utf-8")), request.headers))
        return 200, {"x-log-requestid": "mock-request-id"}, "{}"

    responses.add_callback(
        responses.PUT,
        re.compile(
            r"https?://resource-policy-project\.cn-mock\.example\.com.*?"
            r"/resource-policies$"
        ),
        callback=callback,
    )

    project_response = client.put_resource_policy(
        PROJECT, ResourcePolicyResourceType.PROJECT, POLICY
    )
    logstore_response = client.put_resource_policy(
        PROJECT,
        ResourcePolicyResourceType.LOGSTORE,
        POLICY,
        resource_name=LOGSTORE,
        dry_run=True,
    )

    assert captured[0][0] == {
        "resourceType": "project",
        "policyDocument": POLICY,
        "dryRun": False,
    }
    assert captured[1][0] == {
        "resourceType": "logstore",
        "resourceName": LOGSTORE,
        "policyDocument": POLICY,
        "dryRun": True,
    }
    for body, headers in captured:
        assert headers["Content-Type"] == "application/json"
        assert int(headers["x-log-bodyrawsize"]) == len(
            json.dumps(body).encode("utf-8")
        )
    assert project_response.get_request_id() == "mock-request-id"
    assert logstore_response.get_request_id() == "mock-request-id"


@responses.activate
def test_get_resource_policy_sends_query_and_parses_response():
    client = make_client(endpoint="cn-mock.example.com", project=PROJECT)
    mock_sls_response(
        responses,
        "GET",
        re.compile(
            r"https?://resource-policy-project\.cn-mock\.example\.com.*?"
            r"/resource-policies\?(?:resourceType=logstore"
            r"&resourceName=resource-policy-logstore|"
            r"resourceName=resource-policy-logstore&resourceType=logstore)$"
        ),
        body={
            "resourceType": "logstore",
            "resourceName": LOGSTORE,
            "policyDocument": POLICY,
            "revision": 3,
            "createTime": 10,
            "updateTime": 20,
        },
    )

    response = client.get_resource_policy(
        PROJECT, ResourcePolicyResourceType.LOGSTORE, LOGSTORE
    )

    assert response.get_resource_type() == ResourcePolicyResourceType.LOGSTORE
    assert response.get_resource_name() == LOGSTORE
    assert response.get_policy_document() == POLICY
    assert response.get_revision() == 3
    assert response.get_create_time() == 10
    assert response.get_update_time() == 20


@responses.activate
def test_get_project_resource_policy_omits_resource_name_and_uses_response_target():
    client = make_client(endpoint="cn-mock.example.com", project=PROJECT)
    mock_sls_response(
        responses,
        "GET",
        re.compile(
            r"https?://resource-policy-project\.cn-mock\.example\.com.*?"
            r"/resource-policies\?resourceType=project$"
        ),
        body={
            "resourceType": "logstore",
            "resourceName": "unexpected",
            "policyDocument": POLICY,
            "revision": 1,
            "createTime": 2,
            "updateTime": 3,
        },
    )

    response = client.get_resource_policy(
        PROJECT, ResourcePolicyResourceType.PROJECT
    )

    assert response.get_resource_type() == ResourcePolicyResourceType.LOGSTORE
    assert response.get_resource_name() == "unexpected"


@responses.activate
def test_delete_resource_policy_sends_target_query():
    client = make_client(endpoint="cn-mock.example.com", project=PROJECT)
    mock_sls_response(
        responses,
        "DELETE",
        re.compile(
            r"https?://resource-policy-project\.cn-mock\.example\.com.*?"
            r"/resource-policies\?resourceType=project$"
        ),
    )

    response = client.delete_resource_policy(
        PROJECT, ResourcePolicyResourceType.PROJECT
    )

    assert response.get_request_id() == "mock-request-id"


def test_put_resource_policy_rejects_empty_document():
    client = make_client(endpoint="cn-mock.example.com", project=PROJECT)

    with pytest.raises(LogException) as excinfo:
        client.put_resource_policy(
            PROJECT, ResourcePolicyResourceType.PROJECT, ""
        )

    assert excinfo.value.get_error_code() == "InvalidParameter"


@pytest.mark.parametrize(
    "project,resource_type",
    [
        ("", ResourcePolicyResourceType.PROJECT),
        (PROJECT, ""),
        (PROJECT, "dashboard"),
    ],
)
def test_resource_policy_rejects_missing_target(project, resource_type):
    client = make_client(endpoint="cn-mock.example.com", project=PROJECT)

    with pytest.raises(LogException) as excinfo:
        client.get_resource_policy(project, resource_type)

    assert excinfo.value.get_error_code() == "InvalidParameter"


def test_resource_policy_target_validation_is_delegated_to_server(monkeypatch):
    client = make_client(endpoint="cn-mock.example.com", project=PROJECT)
    calls = []

    def capture(method, project, body, resource, params, headers, **kwargs):
        calls.append((method, body, params))
        if method == "GET":
            return ({
                "resourceType": "logstore",
                "policyDocument": "{}",
                "revision": 1,
                "createTime": 2,
                "updateTime": 3,
            }, {})
        return ({}, {})

    monkeypatch.setattr(client, "_send", capture)

    client.put_resource_policy(
        PROJECT,
        ResourcePolicyResourceType.PROJECT,
        POLICY,
        resource_name=LOGSTORE,
    )
    client.get_resource_policy(
        PROJECT, ResourcePolicyResourceType.LOGSTORE, resource_name=""
    )
    client.delete_resource_policy(
        PROJECT, ResourcePolicyResourceType.PROJECT, resource_name=LOGSTORE
    )

    assert json.loads(calls[0][1].decode("utf-8"))["resourceName"] == LOGSTORE
    assert calls[1][2] == {"resourceType": "logstore"}
    assert calls[2][2] == {
        "resourceType": "project",
        "resourceName": LOGSTORE,
    }
