import uuid
import pytest
from aiohttp import ClientTimeout

BASE = "http://localhost:9099/identitytoolkit.googleapis.com/v1"


@pytest.mark.parametrize(
    "email_prefix,password",
    [
        ("alice", "Passw0rd!"),
        ("bob", "S3cret#123"),
    ],
)
@pytest.mark.asyncio
async def test_auth_signup_and_signin(email_prefix, password, http_client):
    # given: unique email and password
    unique = uuid.uuid4().hex[:8]
    email = f"{email_prefix}.{unique}@example.com"

    # when: sign up (create user)
    signup_url = f"{BASE}/accounts:signUp?key=fake-key"
    async with http_client.post(
        signup_url,
        json={"email": email, "password": password, "returnSecureToken": True},
        timeout=ClientTimeout(total=5.0),
    ) as signup_res:
        # then: user is created and receives an id token
        assert signup_res.status == 200, await signup_res.text()
        data = await signup_res.json()
    assert data.get("localId")
    assert data.get("idToken")

    # when: sign in with the same credentials
    signin_url = f"{BASE}/accounts:signInWithPassword?key=fake-key"
    async with http_client.post(
        signin_url,
        json={"email": email, "password": password, "returnSecureToken": True},
        timeout=ClientTimeout(total=5.0),
    ) as signin_res:
        # then: sign-in succeeds and returns a token
        assert signin_res.status == 200, await signin_res.text()
        signin_data = await signin_res.json()
    assert signin_data.get("localId") == data.get("localId")
    assert signin_data.get("idToken")
