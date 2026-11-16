async def test_healthz_ok_without_key_and_token(client):
    response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-App-Version"] == "abc1234"
