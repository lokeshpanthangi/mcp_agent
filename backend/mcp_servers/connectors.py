"""Catalog of well-known remote MCP servers offered as one-click connectors.

Most use OAuth (with Dynamic Client Registration) — the user clicks Connect,
authorizes in their provider, and the tools appear. A connector may instead set
`"auth": "token"` when the provider doesn't support automatic OAuth registration
(e.g. GitHub); the user pastes a personal access token. This is content, not
config (like prompts.py); edit freely to add/remove connectors.
"""

CONNECTORS = [
    {
        "key": "github",
        "name": "GitHub",
        "url": "https://api.githubcopilot.com/mcp/",
        "transport": "streamable_http",
        "auth": "token",  # GitHub has no OAuth DCR — paste a personal access token
        "description": "Repositories, issues, pull requests, code search.",
    },
    {
        "key": "linear",
        "name": "Linear",
        "url": "https://mcp.linear.app/mcp",
        "transport": "streamable_http",
        "description": "Issues, projects, and cycles in Linear.",
    },
    {
        "key": "notion",
        "name": "Notion",
        "url": "https://mcp.notion.com/mcp",
        "transport": "streamable_http",
        "description": "Search, read, and update your Notion workspace.",
    },
    {
        "key": "sentry",
        "name": "Sentry",
        "url": "https://mcp.sentry.dev/mcp",
        "transport": "streamable_http",
        "description": "Errors, issues, and performance data from Sentry.",
    },
    {
        "key": "asana",
        "name": "Asana",
        "url": "https://mcp.asana.com/sse",
        "transport": "sse",
        "description": "Tasks, projects, and workspaces in Asana.",
    },
    {
        "key": "atlassian",
        "name": "Atlassian",
        "url": "https://mcp.atlassian.com/v1/sse",
        "transport": "sse",
        "description": "Jira issues and Confluence pages.",
    },
    {
        "key": "stripe",
        "name": "Stripe",
        "url": "https://mcp.stripe.com",
        "transport": "streamable_http",
        "description": "Payments, customers, and invoices in Stripe.",
    },
    {
        "key": "paypal",
        "name": "PayPal",
        "url": "https://mcp.paypal.com/mcp",
        "transport": "streamable_http",
        "description": "Invoices, orders, and transactions in PayPal.",
    },
]

CONNECTORS_BY_KEY = {c["key"]: c for c in CONNECTORS}
