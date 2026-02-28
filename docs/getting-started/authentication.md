# Authentication

LatePenalty requires a `credentials.json` file with API tokens for Canvas and GitHub.

## Create credentials.json

```json
{
    "Canvas Token": "your-canvas-api-token",
    "GitHub Token": "your-github-api-token"
}
```

## Obtaining a Canvas Token

1. Log in to your Canvas instance
2. Go to **Account** > **Profile** > **Settings**
3. Scroll to **Approved Integrations**
4. Click **+ New Access Token**
5. Copy the token into `credentials.json`

## Obtaining a GitHub Token

1. Go to [GitHub Settings > Developer Settings > Personal Access Tokens](https://github.com/settings/tokens)
2. Generate a new token with `repo` scope
3. Copy the token into `credentials.json`

!!! warning "Keep credentials secure"
    Never commit `credentials.json` to version control. Add it to `.gitignore`.
