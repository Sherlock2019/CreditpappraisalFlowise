# Flowise Security Notes

- Never commit real API keys.
- Keep `.env.flowise` out of Git.
- Do not expose Flowise publicly without authentication, a reverse proxy, or VPN.
- Use HTTPS if Flowise is remote.
- Use API key auth for Flowise API imports.
- Rotate keys after testing.
- Keep local Ollama private.
- Protect enterprise document connector credentials.
- Use read-only credentials for S3, SharePoint, OpenText, Hyland, FileNet, ServiceNow, Salesforce, and cloud storage integrations.
- Avoid sending unnecessary sensitive personal data to any LLM provider.
- Keep generated JSON credential references as placeholders only.
