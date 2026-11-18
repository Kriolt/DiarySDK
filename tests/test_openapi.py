async def test_openapi_documents_endpoints_and_auth(client):
    response = await client.get("/openapi.json")

    assert response.status_code == 200
    spec = response.json()
    assert "/v1/me" in spec["paths"]
    assert "/healthz" not in spec["paths"]
    schemes = spec["components"]["securitySchemes"]
    assert {scheme["type"] for scheme in schemes.values()} == {"apiKey", "http"}
    me = spec["components"]["schemas"]["Me"]
    assert "class" in me["properties"]


def _spec(settings):
    from diarysdk.server.app import create_app

    return create_app(settings).openapi()


def test_openapi_describes_our_400_not_fastapi_422(settings):
    spec = _spec(settings)
    schemas = spec["components"]["schemas"]
    assert "HTTPValidationError" not in schemas
    assert "ValidationError" not in schemas
    marks = spec["paths"]["/v1/marks"]["get"]["responses"]
    # 422 остаётся только как наш multiple_children, не как ошибка проверки.
    assert "multiple_children" in marks["422"]["description"]
    assert "not_for_role" in marks["422"]["description"]
    assert "HTTPValidationError" not in str(marks)
    assert marks["400"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
    assert set(schemas["ErrorResponse"]["properties"]) == {"error", "message"}


def test_every_operation_documents_errors_in_our_format(settings):
    spec = _spec(settings)
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            responses = operation["responses"]
            assert {"403", "429"} <= set(responses), (method, path)
            for status, response in responses.items():
                if status.startswith(("4", "5")):
                    ref = response["content"]["application/json"]["schema"]["$ref"]
                    assert ref.rsplit("/", 1)[1].endswith("ErrorResponse"), (method, path, status)


def test_esia_code_documents_401_with_step(settings):
    spec = _spec(settings)
    schemas = spec["components"]["schemas"]
    unauthorized = spec["paths"]["/v1/auth/esia/{flow_id}/code"]["post"]["responses"]["401"]
    ref = unauthorized["content"]["application/json"]["schema"]["$ref"]
    assert ref == "#/components/schemas/LoginStepErrorResponse"
    assert "step" in schemas["LoginStepErrorResponse"]["properties"]
    assert "LoginStep" in schemas


def test_bad_gateway_documents_upstream_status(settings):
    spec = _spec(settings)
    bad_gateway = spec["paths"]["/v1/me"]["get"]["responses"]["502"]
    ref = bad_gateway["content"]["application/json"]["schema"]["$ref"]
    assert ref == "#/components/schemas/UpstreamErrorResponse"
    assert "upstream_status" in spec["components"]["schemas"]["UpstreamErrorResponse"]["properties"]


def test_settings_update_schema_has_no_null_defaults(settings):
    schemas = _spec(settings)["components"]["schemas"]
    for name in ("SettingsUpdate", "SettingsThemeUpdate"):
        for field, definition in schemas[name]["properties"].items():
            assert "default" not in definition, (name, field)
