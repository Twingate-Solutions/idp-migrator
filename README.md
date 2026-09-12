# twingate-idp-migrator

A desktop GUI tool for Twingate administrators to migrate group-to-resource access mappings when switching identity providers (e.g. Okta → Microsoft Entra ID).

---

## Disclaimer

> **Use at your own risk.**
>
> This tool was developed with the assistance of large language model (LLM) AI tooling and has been tested against sample data and real Twingate API environments. However, it is provided **"as is"** under the Apache 2.0 License, with no warranty of any kind — express or implied.
>
> Before running any pre-built binary, you are strongly encouraged to **review the source code** in this repository and satisfy yourself that it behaves as expected in your environment. You should **test with the built-in demo mode** (see below) before connecting to a production Twingate account.
>
> **This is not an official Twingate product.** Twingate support does not provide assistance for this tool. If you encounter a bug or unexpected behavior, please [open an issue](issues) in this repository. Community contributions via pull requests are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## What It Does

When you migrate your organization to a new identity provider, Twingate syncs the new IdP's groups alongside your existing ones. This leaves your old groups' resource access assignments intact, but the new groups start with no resource access. Re-assigning every resource, security policy, and access mode by hand is tedious and error-prone.

This tool automates that process:

1. Connects to your Twingate tenant via the admin API and fetches all groups and resources.
2. Lets you designate which groups belong to the **old IdP** and which belong to the **new IdP**.
3. Uses fuzzy name matching to suggest old→new group pairings, with manual override support.
4. Generates a full preview (dry run) of every access grant that will be added.
5. Executes the migration — adding the new groups to the same resources with identical security policies and access modes as the old groups.
6. Writes a complete JSON changelog of every change made, enabling full rollback at any time.

**The tool is additive only.** It never removes the old groups' access. You retain full control over when to decommission the old groups in Twingate.

---

## Features

- **Fuzzy group matching** — auto-suggests pairings with confidence scores (0–100%); any mapping can be overridden manually via dropdown
- **Mandatory dry run** — every planned access grant is shown before any API write is made; there is no way to skip this step
- **Additive only** — existing access is never removed; old group cleanup is left to the administrator
- **Full changelog** — every executed mutation is logged to a local JSON file with resource IDs, group IDs, policy details, and timestamps
- **One-click rollback** — load a changelog file and undo the entire migration, or selectively roll back one group at a time
- **Demo / TEST mode** — fully walkable offline demo using pre-built sample data; no Twingate account required
- **Light / dark theme** — follows system appearance or can be set manually via File → Appearance
- **Cross-platform** — pre-built single-file binaries for Windows, macOS (Apple Silicon + Intel), and Linux

---

## Download

Download the latest pre-built binary from [GitHub Releases](releases/latest):

| Platform | File |
|---|---|
| Windows (x64) | `twingate-idp-migrator-windows-x64.exe` |
| macOS (Apple Silicon) | `twingate-idp-migrator-macos-arm64` |
| Linux (x64) | `twingate-idp-migrator-linux-x64` |

No Python installation required. Each binary is self-contained.

**Windows:** The binary is self-signed rather than signed by a commercial certificate authority, so Windows Defender SmartScreen may show a "Windows protected your PC" warning the first time you run it. This is expected for community-distributed tooling. To proceed:

1. Click **More info**
2. Click **Run anyway**

If you are on a managed device where **Run anyway** is not shown, your IT administrator has restricted unsigned executable launches via Group Policy. In that case, the simplest alternative is to [run the tool from source](#running-from-source) instead — Python and pip are all that is required.

> If you want to verify the binary before running it, the SHA-256 checksum for each release asset is listed in the release notes on the [Releases page](releases/latest).

**macOS:** After downloading, remove the quarantine flag before running:

```bash
xattr -d com.apple.quarantine twingate-idp-migrator-macos-*
chmod +x twingate-idp-migrator-macos-*
./twingate-idp-migrator-macos-*
```

**Linux:** Make the binary executable before running:

```bash
chmod +x twingate-idp-migrator-linux-x64
./twingate-idp-migrator-linux-x64
```

---

## Prerequisites (Live Migration)

- A Twingate account with administrator access
- A Twingate API token with **Read** and **Write** scope
  - In the Twingate admin console: **Settings → API → Generate Token**
- Your Twingate tenant name — the part of your Admin Console URL before `.twingate.com`.
  Copy it from the URL rather than assuming a single label:
  - `acme.twingate.com` (legacy) → enter `acme`
  - `acme.us1.twingate.com` (shard-based, where `us1` is the shard) → enter `acme.us1`
- Your new IdP's groups must already be synced into Twingate before running the migration

---

## How to Use

### Step 1 — Connect

Enter your **Tenant Name** and **API Key**, then click **Connect**. The tool will verify the credentials and fetch all groups and resources from your Twingate account. This is read-only — no changes are made at this step.

> The API key is held in memory only for the duration of the session. It is never written to disk, the registry, or any log file.

Once connected, a count of loaded groups and resources is shown. Click **Next**.

---

### Step 2 — Select Groups

Assign your groups into two buckets:

- **Old IdP (From)** — the groups currently synced from your previous identity provider
- **New IdP (To)** — the groups synced from your new identity provider

Select groups in the **Available Groups** list and use the arrow buttons to move them into the appropriate bucket. Use the **Remove** buttons to move a group back to Available if you change your mind.

> This step does not create any pairings. You are simply categorising groups — the actual mapping happens in Step 3.

Click **Next** when both buckets are populated.

---

### Step 3 — Review Mappings

The tool uses fuzzy name matching to suggest a **To** group for each **From** group. Each row shows:

| Column | Description |
|---|---|
| From Group | The old IdP group |
| To Group | The suggested new IdP group (dropdown — click to change) |
| Confidence | Match quality: ≥80% high (green), 50–79% medium (yellow), <50% low (red) |
| Confirmed | Check this box to include the mapping in the migration |

**Reviewing mappings:**

- High-confidence matches (≥80%) are auto-confirmed. Review them and uncheck any that look wrong.
- Low-confidence or unmatched rows are left unconfirmed. Use the dropdown to assign a To group manually, then check Confirmed.
- Any From group left unconfirmed is excluded from the migration — its resources will not be updated.

Click **Next** when you are satisfied with the confirmed mappings.

---

### Step 4 — Preview Changes (Dry Run)

Before any writes are made, the tool fetches detailed resource access data and builds a complete plan. The tree view shows:

```
Mapping: Okta-Engineering → Entra-Engineering
  └── prod-database.corp (10.0.1.10)
        ADD access for Entra-Engineering  [Security Policy: MFA Required]
  └── gitlab.corp (10.0.1.30)
        ADD access for Entra-Engineering  [Security Policy: MFA Required]
```

Each entry shows the resource name, address, the group being granted access, and the security policy that will be applied (copied from the old group's access edge).

> If a mapping shows "No changes needed", the new group already has access to all the same resources as the old group — nothing will be added.

Review the entire plan carefully. When you are ready, click **Run Migration →**.

---

### Step 5 — Execute Migration

The tool executes all planned access grants in sequence, showing per-resource progress. For each action:

- **Success** — the new group was granted access to the resource
- **Skipped / already exists** — the new group already had access (idempotent; not an error)
- **Failed** — the API call failed; the error is logged and the migration continues with the remaining actions

A summary of successes and failures is shown when the run completes. A **changelog file** is saved to your home directory:

```
~/twingate-migration-<timestamp>.json
```

Keep this file — it is required for rollback.

---

### Rollback

Rollback is available at any time via **File → Rollback from Changelog…**, or as the final step after execution.

1. Click **Load Changelog** and select the `.json` changelog file saved during the migration.
2. The tool shows all changes that were made, grouped by From→To group mapping.
3. Choose the rollback scope:
   - **Roll Back All** — removes the new group's access from every resource that was added during the migration
   - **Roll Back One Group** — select a specific mapping to undo
4. Click **Execute Rollback**.

Rollback uses `resourceAccessRemove` mutations — it only removes access that was explicitly granted by this tool's changelog. It does not touch any other access.

---

## TEST / Demo Mode

You can walk through the entire tool without a Twingate account using the built-in demo mode.

**To activate:** On the Connect page, enter `TEST` in both the **Tenant Name** and **API Key** fields, then click **Connect**.

The tool loads a pre-built Okta → Entra ID scenario:

**Old IdP groups (Okta):**

- Okta-Engineering, Okta-Finance, Okta-DevOps, Okta-Sales, Okta-HR

**New IdP groups (Entra ID):**

- Entra-Engineering, Entra-Finance, Entra-DevOps, Entra-Sales-Team, Entra-Executive

**Sample resources (8 internal services):**

- prod-database.corp, internal-wiki.corp, gitlab.corp, jira.corp, salesforce.corp, hr-portal.corp, monitoring.corp, ci-runner.corp

**Pre-built mappings:**

| From | To | Confidence | Notes |
| --- | --- | --- | --- |
| Okta-Engineering | Entra-Engineering | 92% | High confidence, auto-confirmed |
| Okta-Finance | Entra-Finance | 88% | High confidence, auto-confirmed |
| Okta-DevOps | Entra-DevOps | 90% | High confidence, auto-confirmed |
| Okta-Sales | Entra-Sales-Team | 65% | Medium — name differs slightly |
| Okta-HR | *(none)* | 0% | No close match — unconfirmed |

This gives you roughly 20 planned access changes in the dry run, covering various security policies (MFA Required, Standard Access) and access modes.

**In demo mode:**

- Step 2 (group selection) is pre-populated — you can click through it or modify it
- Step 3 shows the pre-built mappings — you can adjust and confirm as with a real account
- Step 4 shows the full dry-run tree based on the sample resources
- Step 5 simulates execution with a short delay per action — no real API calls are made
- Rollback similarly simulates the reverse operations

A banner on Steps 4 and 5 reminds you that you are in demo mode.

---

## Running from Source

Requires Python 3.12+.

```bash
git clone https://github.com/Twingate-Solutions/idp-migrator.git
cd twingate-idp-migrator

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt

python -m src.main
```

---

## Building a Binary

```bash
pip install -r requirements-dev.txt
pyinstaller migrator.spec --clean
# Output: dist/twingate-idp-migrator.exe  (Windows)
#         dist/twingate-idp-migrator       (macOS / Linux)
```

---

## Architecture

```
PySide6 GUI (QMainWindow + QStackedWidget wizard)
    ↕ Qt signals/slots
QThread workers  →  asyncio.run()  →  TwingateClient (httpx.AsyncClient)
    ↕                                      ↕ HTTPS GraphQL
Changelog (JSON)              Twingate Admin API
```

The GUI runs on the main thread. All Twingate API calls run in a background `QThread` using `asyncio.run()`. Qt signals bridge results back to the main UI thread. The core logic (`src/api/`, `src/core/`) has no Qt dependency and is fully unit-testable in isolation.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

Issues and pull requests are welcome. This tool is community-supported — please do not contact Twingate support with questions about it.

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
