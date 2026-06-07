# Flowise Import Steps

This package contains generated Flowise-compatible JSON created from the real PoC repository.

## Method A - UI Import

1. Start Flowise.
2. Open Flowise and go to `Chatflows`.
3. Click `Add New`.
4. Open settings or the canvas import menu and choose `Load Chatflow` / `Import`.
5. Select `flowise_project/generated/docfactor-all-in-one-flowise-chatflow.json`.
6. Reconnect credentials manually.
7. Save the chatflow.
8. Test chat from the Flowise canvas.

Credentials are intentionally excluded from generated JSON. Imported flows may require credentials to be reselected in Flowise UI.

## Method B - API Import

1. Copy `.env.flowise.example` to `.env.flowise`.
2. Set `FLOWISE_BASE_URL`.
3. Set `FLOWISE_API_KEY` if your Flowise instance requires API key auth.
4. Run the validator:

```bash
python3 flowise_project/validate-flowise-json.py
```

5. Run the import script:

```bash
python3 flowise_project/import-flowise-chatflow.py --all
```

For the one-file import:

```bash
python3 flowise_project/import-flowise-chatflow.py --file flowise_project/generated/docfactor-all-in-one-flowise-chatflow.json
```

or:

```bash
bash flowise_project/import-flowise-chatflow.sh --all
```

6. Open Flowise UI.
7. Attach credentials if needed.
8. Test the imported flow.

The API import uses Flowise `POST /api/v1/chatflows` and sends `flowData` as a JSON string.
