"""Standards-based OAuth 2.1 flow for remote MCP servers.

Implements the MCP authorization flow: metadata discovery (RFC 9728 / RFC 8414),
Dynamic Client Registration (RFC 7591), Authorization Code + PKCE, token
exchange and refresh. Pure outbound HTTP — no DB, no FastAPI. The mcp_servers
layer stores the flow state and the resulting tokens.
"""

from urllib.parse import urlencode, urljoin, urlsplit

import httpx
from mcp.client.auth import PKCEParameters

CLIENT_NAME = "MCP Agent"


def new_pkce() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for a fresh PKCE pair (S256)."""
    p = PKCEParameters.generate()
    return p.code_verifier, p.code_challenge


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _wellknown_urls(url: str, name: str) -> list[str]:
    """Candidate metadata URLs for a resource/auth-server per RFC 8414 / 9728.

    The well-known segment goes *between* host and path (path-suffixed), e.g.
    https://host/.well-known/<name>/some/path — with the plain-origin form as a
    fallback for servers that publish it at the root.
    """
    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    path = parts.path.rstrip("/")
    urls = [f"{origin}/.well-known/{name}{path}"] if path else []
    urls.append(f"{origin}/.well-known/{name}")
    return urls


async def discover(server_url: str) -> dict:
    """Discover the OAuth endpoints for an MCP server.

    Returns {authorization_endpoint, token_endpoint, registration_endpoint,
    scopes_supported, resource}. Falls back to sensible defaults when a server
    doesn't publish full metadata.
    """
    origin = _origin(server_url)
    resource = server_url
    scopes: list[str] = []
    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as http:
        # 1) Protected Resource Metadata -> which authorization server to use.
        auth_server = origin
        for prm_url in _wellknown_urls(server_url, "oauth-protected-resource"):
            try:
                r = await http.get(prm_url)
                if r.status_code == 200:
                    prm = r.json()
                    resource = prm.get("resource") or resource
                    scopes = prm.get("scopes_supported") or []
                    servers = prm.get("authorization_servers") or []
                    if servers:
                        auth_server = servers[0].rstrip("/")
                        break
            except Exception:
                continue

        # 2) Authorization Server Metadata -> the actual endpoints.
        for asm_url in (
            *_wellknown_urls(auth_server, "oauth-authorization-server"),
            *_wellknown_urls(auth_server, "openid-configuration"),
        ):
            try:
                r = await http.get(asm_url)
                if r.status_code == 200:
                    m = r.json()
                    return {
                        "authorization_endpoint": m["authorization_endpoint"],
                        "token_endpoint": m["token_endpoint"],
                        "registration_endpoint": m.get("registration_endpoint"),
                        "scopes_supported": m.get("scopes_supported") or scopes,
                        "resource": resource,
                    }
            except Exception:
                continue

    # 3) Fallback to conventional endpoint paths. registration_endpoint stays None:
    # we only claim Dynamic Client Registration when real metadata advertises it,
    # so we never POST to a fabricated /register (which 404s) or offer a login the
    # server can't honor.
    return {
        "authorization_endpoint": urljoin(auth_server + "/", "authorize"),
        "token_endpoint": urljoin(auth_server + "/", "token"),
        "registration_endpoint": None,
        "scopes_supported": scopes,
        "resource": resource,
    }


async def register_client(registration_endpoint: str, redirect_uri: str, scope: str | None) -> dict:
    """Dynamic Client Registration. Returns {client_id, client_secret?}."""
    payload = {
        "client_name": CLIENT_NAME,
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    if scope:
        payload["scope"] = scope
    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as http:
        r = await http.post(registration_endpoint, json=payload)
        r.raise_for_status()
        data = r.json()
    return {"client_id": data["client_id"], "client_secret": data.get("client_secret")}


def build_authorization_url(
    authorization_endpoint: str,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    state: str,
    scope: str | None,
    resource: str,
) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
        "resource": resource,
    }
    if scope:
        params["scope"] = scope
    sep = "&" if "?" in authorization_endpoint else "?"
    return f"{authorization_endpoint}{sep}{urlencode(params)}"


async def exchange_code(
    token_endpoint: str,
    code: str,
    redirect_uri: str,
    client_id: str,
    code_verifier: str,
    resource: str,
    client_secret: str | None = None,
) -> dict:
    """Exchange an authorization code for tokens.

    Returns {access_token, refresh_token?, expires_in?, token_type?}.
    """
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": code_verifier,
        "resource": resource,
    }
    if client_secret:
        data["client_secret"] = client_secret
    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as http:
        r = await http.post(token_endpoint, data=data)
        r.raise_for_status()
        return r.json()


async def refresh_access_token(
    token_endpoint: str,
    refresh_token: str,
    client_id: str,
    client_secret: str | None = None,
) -> dict:
    """Use a refresh token to obtain a new access token."""
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }
    if client_secret:
        data["client_secret"] = client_secret
    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as http:
        r = await http.post(token_endpoint, data=data)
        r.raise_for_status()
        return r.json()
