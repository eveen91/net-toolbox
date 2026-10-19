# Documentation

The Documentation module creates tenant-local network/DC documents, switch cards,
firewall cards and operational runbooks. The existing eleven DC chapters remain
available under the Network / DC template. Other templates have their own tabs.
Existing saved forms and version downloads remain compatible.

## Create, edit and review

1. Choose **New document** and a **Document type**. The type is fixed after the first save.
2. Enter the title and documented subject. Runbooks may omit the subject.
3. Optionally choose **Document scope** and the DC, rack, device or IPAM network
   it describes. **Manual document** does not collect inventory. DC/rack scopes
   include every installed device within the limit, not only one device.
4. Inspect **Included data preview**. Published DHCP Generator versions can be
   attached explicitly; their immutable version IDs are pinned.
5. Complete the narrative and **Save all chapters**. Switching chapters or views
   retains entered values. Failed saves retain the form. Saved documents have an
   explicit **Edit** action and search/status/type filters. The saved-document list starts expanded, then collapses when opening/saving a document to leave room for the editor; expand **Saved documentation** to choose another record.
6. **Submit for review** checks purpose, responsible team and identity. Runbooks
   also require procedure steps, verification and rollback. Incomplete drafts can
   be saved. Optional sections and missing source facts are advisory; no firewall
   rulebase transcription or historical per-rule justification is required.
7. While **In review**, the content and infrastructure snapshot are read-only.
   A publisher can enter a review note and **Publish reviewed version**. This
   creates an immutable local published version and records the actor/time.
8. **Start new draft** enables later changes. Published versions remain unchanged.
   There is no enforced separation between submitter and publisher identities.

## Existing module data

Source adapters read the active tenant database in one consistent SQLite transaction:

| Module | Included facts |
| --- | --- |
| DC Inventory | DC/rack identity, U capacity, placement and explicit physical connections |
| Device Visualization | Devices, models, vendors, ports, transceivers, IPs, VLANs, management ports, storage bays and expansion-port counts |
| IPAM | Scoped/related IPv4 networks, relevant address records and DHCP pools |
| Routing Map | Exactly matching saved host routes/interfaces, using the existing shared merge/read model |
| DHCP Generator | Explicitly attached published configuration versions, server/subnet settings, pools and reservations |

Device and rack reads reuse the existing repositories; physical endpoint naming uses
DC Inventory's existing connection endpoint reader. Routing uses
`db.get_host_in_connection()` shared with Routing Map. There is no second routing
parser, device driver or inventory store. Static export reuses DC Inventory’s
`rackRows`, `unitRange`, `connectionLayout`, `connectionBundles` and `panelSockets`
geometry through a local Node.js adapter.

A routing host must exactly match a device name (case-insensitive) or one of its
recorded interface IPs. Partial hostnames are not guessed. Connected-route fallbacks
can represent network addresses; they are not presented as discovered gateway IPs.
Optional module data is omitted, with an advisory, when its permission is unavailable.
A source manifest records the permissions actually needed for retained facts.

Generated tables are read-only and live in their corresponding chapters. Narrative
remains editable. Connected peers outside the selected scope are marked explicitly;
collection does not recursively include their neighbors. **Source provenance** lists
module, stable ID, version where available, original update time and collection time.
Unknown fields say **Not recorded**. Saved facts are not evidence of live link state.

**Preview infrastructure changes** compares the saved snapshot with current records.
Inspect its tables, then **Apply infrastructure refresh**. Applying preserves all
narrative, checks the draft revision and verifies that the previewed source digest
still matches. Changed sources require a new preview. DHCP references remain pinned
to the explicitly attached published versions.

Limits: 150 scoped devices, 2,000 rows per table, 12,000 combined generated rows and
10 attached DHCP versions. Oversized scopes fail without silently truncating or
partially saving records. Tables page 50 rows in the browser; persisted lists use
server-side pagination. IPAM remains IPv4-only. No device commands are executed.

## Preview, versions and exports

**Preview document** shows every chapter, including unsaved narrative edits. A changed
scope must be saved before its infrastructure snapshot becomes part of the document.
Narrative is displayed as escaped readable text; exported Markdown retains formatting.

**Versions & export** lists both saved draft baselines and published versions, labelled
by kind. **Create version** preserves an optional baseline of a saved draft; it does
not approve or publish the document. Publication goes through the review controls.
Draft revision numbers and explicitly created version numbers are independent.

Each version freezes form content, chapter definitions, template/renderer versions,
source snapshot, source-access manifest, and generated Markdown/ZIP bytes. Historical
preview/download does not collect live infrastructure. **Compare saved versions**
shows named fields before/after, changed source tables and an optional detailed diff.
**Restore version N as draft** requires a draft, confirmation and source access, and
creates a new draft revision without changing any saved version.

Markdown downloads are self-contained UTF-8 text with every generated table row.
ZIP packages contain `README.md`, `documents/dc-<id>.md`, `manifest.json` and, when
applicable, a diagram index, source-reference index, paginated tables/CSV and local
PNG/SVG assets. The ZIP document links to images and other pages using relative
paths; retain the directory structure when unpacking. No app connection, CDN,
Mermaid extension or Confluence plugin is needed to read it offline. The legacy
API and main filename retain the `dc` prefix for compatibility across templates.

Tables exceeding 100 rows show their first 100 rows in the ZIP document and link to
complete pages, each with repeated headers, navigation and a CSV alternative. No
rows are dropped. Spreadsheet-formula-like CSV text is prefixed with an apostrophe;
Markdown preserves the exact recorded value. Typed source references link to stable
anchors rather than guessing identity from names. Missing identities and external
peers have explicit entries in the source index.

The manifest records scope, source timestamp, revision/template/renderer metadata,
permissions, diagram descriptions and SHA-256/size for every other package file.
`standaloneMarkdownSha256` hashes the separate text-only download; the packaged
Markdown has its own hash because it adds images/links and paginated tables.
Version creation, review transitions, restoration, refresh, export and diagram
retrieval are audited. **Review and change history** displays paginated metadata.

## Frozen diagrams

Creating or publishing a version generates PNG and SVG locally from its saved
infrastructure snapshot:

- Rack front elevations, split into 24U pages, with names and recorded U ranges.
- Rack-bundle overview and one orthogonal port-to-port diagram per saved cable.
- Device panels and port details, 16 ports per page, preserving management/controller
  grouping from the existing panel geometry. Free-text destinations are unverified notes.
- IPAM network membership from recorded interface IP/CIDR, 12 memberships per page.
  No routing, zone, VLAN adjacency or live reachability is inferred from membership.

External peers provide cable endpoint context only; their unrelated ports, notes
and neighbors are not collected. Rack diagrams show scoped equipment, so a blank
unit in a device/network document does not assert that the real rack unit is free.
Labels are fitted with an ellipsis when necessary; complete values remain in tables
and SVG titles. PNG is the universal fallback; SVG font substitution does not affect
PNG readability. A bundled DejaVu Sans font, including its distribution license,
preserves Polish labels without an operating-system font dependency.

In **Versions & export**, select **Preview version N**, then **Show diagrams**.
The browser fetches six images per page through authenticated, tenant-aware requests;
open an image to inspect it at full size. Historical PNG/SVG retrieval rechecks
source access and reads stored bytes, exactly like the ZIP download. It never
re-renders against current inventory or loads live device data.

Limits are 512 diagram pages and 64 MiB of diagram assets per revision, in addition
to source limits. Rendering failure or exceeding a limit rolls back the entire
version/publication and audit write; choose a smaller scope before retrying.
Existing versions retain their original bytes. To add diagrams to a pre-Phase-2
snapshot, refresh infrastructure in a draft, inspect/apply the refresh, then save
or publish a new version. Old versions are not upgraded in place.

## Permissions and tenant boundaries

- `documentation.read`: list/read, preview, compare, history and authorized downloads.
- `documentation.write` plus Read: create/edit, refresh, submit/return to draft,
  save a draft baseline and restore a version.
- `documentation.publish` plus Read: publish a reviewed document.
- `documentation.admin` plus Read: manage Confluence connection profiles and credentials.
- Legacy `documentation` preserves full module access. `*` and existing open mode
  retain their behavior. The role editor labels the legacy permission explicitly.
- Existing roles are not automatically rewritten or broadened. Granular permissions
  can be granted to the existing tenant roles/groups through role administration.
- Retained source permissions are checked again on reads, list metadata, comparisons,
  restoration and downloads, including old versions. Revoking source access does not
  leave a historical-export bypass. A document permission alone grants no source access.

## Storage, migration and deployment

The tenant application database owns `documentation_dc_forms`,
`documentation_dc_form_audit` and `documentation_dc_versions`. Additive initialization
adds status, snapshot, retained-permission and publication metadata. Existing forms
become drafts; existing immutable versions remain saved baselines and retain their
original bytes. No records, old module tables or versions are deleted or regenerated.
New immutable artifacts are stored as bounded BLOBs in the tenant DB and participate
in normal database backups.

Static diagram creation requires **Node.js** (already in the Docker image and
frontend development environment) and **Pillow**, pinned in `server/requirements.txt`.
Install/update the backend requirements in the backend's actual virtual environment:

```sh
server/venv/bin/pip install -r server/requirements.txt
```

Pillow is installed in this workspace's `server/venv`. The font and local geometry
adapter ship with the source; keep `src/tools/dc-inventory/{connectionLayout,rackLogic}.js`
when packaging the backend because the adapter imports those existing pure helpers.
No browser engine, screenshot service or external diagram service is required.

Restart the backend to initialize the schema and load the new API, then refresh the
rebuilt frontend. Existing form fields and the `/api/documentation/dc` API prefix
remain stable; `dcName` is the compatible subject-name field for every template.

## Phase 0 / Confluence dependency

The source contracts, permission model, schema, scope limits, migration ownership and
revision rules have been audited and implemented for Phase 1. The on-premises
Confluence URL/context path, product/version, supported authentication, internal CA,
service identity, test space/parent and audience are still installation-dependent.
They must be supplied/verified before connector compatibility can be claimed.
The Phase 3 connector and read-only preview are implemented below. No real customer
Confluence connection has been tested, and production publication is never performed by development tests.
The retained full plan is `.plans/Documentation_Module_Implementation_Plan.md`.

## Confluence connections and publication preview (Phase 3)

This increment implements the local connector and a read-only publication plan.
Phase 3 established read-only checks and previews. Explicit remote publication
and recovery are now implemented in Phase 4 below. The installed customer Confluence version
has not been tested because its URL, token and test space are not yet available.
The application provides the check to perform once those details are supplied.

### Configure and check

1. With Documentation Read and **Documentation Manage Confluence**
   (`documentation.admin`), expand **Confluence connections** and choose
   **Add Confluence connection**.
2. Enter a name, exact HTTPS base URL (including a context such as `/confluence`),
   space key, optional parent page ID, personal access token and request timeout.
   A public internal CA PEM bundle can be supplied for private PKI. Certificate and
   hostname verification are always enabled. The connector does not follow redirects
   or use environment HTTP proxies; configure the canonical destination directly.
3. **Save Confluence connection** stores the PAT encrypted and clears the password
   input. Saved tokens are never returned to the browser. Leave the token blank
   when editing to retain it; changing the base URL requires entering it again.
   Profiles are versioned, can be disabled and are scoped to the active tenant.
4. **Test connection** makes GET requests only. It detects the version via the
   server-information endpoint or older AppLinks JSON manifest, confirms an
   authenticated identity, reads the chosen space/parent, storage representation
   and attachments. The result records its time and profile revision. No page or
   attachment is created as a test.

PAT support starts at Confluence 7.9; older versions and Cloud URLs are rejected.
The test verifies observed read capabilities, not write permissions, upload limits,
reader audience or the final appearance after Confluence processes storage. These
must be checked on the actual approved installation before Phase 4 publication.

### Review an immutable version

1. Publish the reviewed document locally. In **Versions & export**, choose
   **Preview version N** for a published version.
2. In **Confluence publication preview**, choose a destination and
   **Prepare Confluence preview**. This requires Documentation Read/Publish and
   all source permissions retained by the selected version and any earlier
   publication baseline used in the comparison.
3. Inspect the root page, chapter pages, child pages for large tables and PNG
   attachments. Headings, paragraphs, lists, fenced code and tables are rendered
   from the canonical version to native Confluence storage; no Markdown upload or
   Mermaid extension is required. Frozen PNG checksums are verified against the
   stored ZIP; live inventory and diagram renderers are not consulted.
4. Select a **Planned page** to review its browser preview, target, action, issues,
   attachment operations, storage diff and complete planned storage. The browser
   preview uses a scriptless sandbox with automatic network access blocked. It is
   an approximation, not Confluence's own rendered output. Full frozen diagrams
   remain available under **Saved diagrams** and in the ZIP.
5. Use **Saved Confluence previews** to reopen captured results. A profile-change
   warning marks plans made with older settings. Regenerate the plan when remote
   pages or configuration change; reopening does not silently re-fetch remote data.

Stable tenant-local destination UUIDs identify each document/page key. Remote IDs,
observed versions/hashes, last published local revisions and owned attachment
baselines are used by the Phase 4 executor described below. A title match without a mapping
is a conflict, never an instruction to adopt or overwrite the page. Previously
mapped pages that disappear, move or change remotely are flagged; parent conflicts
block descendants. Attachment identity/version changes and unowned filename
collisions are also conflicts. Obsolete mappings are retained, without delete plans.

A saved preview carries the union of source permissions needed for both planned
and comparison content. Revocation blocks historical preview access and removes
that preview from the paginated list, even if the current document scope no longer
includes those older sources. Profile management is separate from Publish:
publishers can select/test approved profiles, but cannot read editable profile
settings or change credentials without `documentation.admin`. Legacy
`documentation` retains full module access, including connection management; existing
roles are not automatically rewritten. The role editor exposes the new permission.

Limits: 50 profiles per tenant, 200 pages per hierarchy, 100 rows per table child
page, 1,000 remote attachments per page, 250 remote GET requests / 90 seconds per
operation, 8 MiB per REST response and 32 MiB per saved preview. Oversized or stale
plans fail before committing local destination reservations/preview/audit records.
Authentication, TLS, format, permission, timeout and rate-limit errors are sanitized;
remote error bodies and submitted credentials are not echoed into responses/audit.

### Credential key and deployment

The backend directly depends on `cryptography` and `markdown-it-py`, both listed in
`server/requirements.txt` (already present in this workspace's backend environment).
Install the requirements in any other backend environment before restarting it.
The frontend must be rebuilt for the profile and preview screens.

By default, the first token save creates a private, owner-only (`0600`) Fernet key
at `$TENANT_DATA_ROOT/.documentation-confluence.key`, or under
`server/tenants/` when the environment setting is absent. Docker's existing tenant
data volume persists this file. Encrypted token payloads are bound to the tenant,
profile ID and base URL. Tokens/ciphertext never enter document versions, Markdown,
ZIP packages, preview records or audit metadata.

**Back up this key separately and securely together with the tenant database backup.**
Restoring encrypted profiles without their original key cannot recover the tokens.
The application does not replace a missing key while decrypting an existing profile.
An operator can instead provide a valid Fernet key through `DOCUMENTATION_SECRET_KEY`;
keep that environment value stable. Changing it is not automatic key rotation and
will not decrypt profiles written with a different key. To rotate a PAT, edit the
profile and enter a replacement token; its revision increments and prior checks
and previews become stale. Moving a profile with real remote mappings to another
URL/space/parent is blocked; use a separate profile and reviewed migration workflow.

### Protocol references

The implementation follows Atlassian's
[Server/DC REST API examples](https://developer.atlassian.com/server/confluence/confluence-rest-api-examples/),
[server-information endpoint](https://developer.atlassian.com/server/confluence/rest/v9220/api-group-server-information/),
[AppLinks manifest documentation](https://confluence.atlassian.com/spaces/APPLINKS040/pages/776822328/AppLinks%2BDiagnostics%2B-%2BManifest%2BApplication%2BURL%2BHTTP%2BConnectivity),
[personal access token documentation](https://confluence.atlassian.com/enterprise/using-personal-access-tokens-1026032365.html)
and [storage format](https://confluence.atlassian.com/doc/confluence-storage-format-790796544.html).
Mock tests exercise the supported protocol; they are not certification of an unknown
installation. No production Confluence space is used by the automated test suite.

## Confluence publication and recovery (Phase 4)

Phase 4 adds explicit execution to the Phase 3 preview. Development tests use an
isolated Confluence simulator; the customer's real space, supported API behavior,
reader audience and upload settings still require installation testing. No real
Confluence pages are published during automated tests.

### Publish a reviewed plan

1. Open an immutable locally published version and prepare a **new Confluence
   preview**. Old previews without audience metadata cannot be executed.
2. Inspect the target space/parent, page diffs and PNG attachments. Expand
   **Destination audience and inherited read restrictions**. The application records
   reported space permissions and direct read restrictions on mapped pages and
   external ancestors; it does not equate tenant groups with Confluence groups.
   If the API does not expose space permissions, inspect them in Confluence.
3. Resolve mapped-page conflicts explicitly: **Keep remote content and attachments**
   preserves that page, while **Replace the reviewed remote content** authorizes the
   displayed replacement against the captured remote version/hash. Unowned titles,
   moved/missing pages and attachment collisions cannot be adopted or overwritten.
   A fresh conflict after review stops the job again. Saved Keep decisions remain
   in force on later previews until explicitly replaced after another review.
4. Confirm that the intended audience may read the document, then choose
   **Publish reviewed plan to Confluence**. This is the action that permits remote
   writes. Creating a preview or reopening a job does not start publication.
5. Inspect per-operation results. Publication creates parent pages before children,
   then uploads frozen PNGs, verifies page/attachment references and performs a final
   audience check. Unchanged canonical pages and owned assets are verified and
   skipped. Remote versions are checked again before each page write; PUT uses the
   next exact version number. Manual edits are never silently merged or replaced.

The published storage includes hidden native anchor macros for stable ownership
and operation identity. They allow a lost response to be reconciled without taking
ownership by title alone. The canonical document, source snapshot and historical
Markdown/ZIP bytes are unchanged. Remote-normalized storage hashes are recorded
separately from canonical content hashes to avoid repeated needless updates.

PNG filenames include their content hash. New images are uploaded as new
attachments with `allowDuplicated=false`, never as unversioned overwrites of an
existing binary. Unchanged files are checked by ID/version and SHA-256 of a bounded
same-origin download. Older attachments and obsolete pages remain in Confluence;
publication does not automatically delete, move or replace unrelated objects.

### Partial results, pause and resume

`documentation_confluence_jobs` and `documentation_confluence_steps` persist the
approved plan, decisions, source permissions, operation IDs, attempts, durable send
markers and confirmed remote IDs/versions/hashes. Journal, mapping and audit writes
are committed together. Each advance processes one bounded step without holding a
SQLite transaction open during HTTP. An optimistic revision plus a 180-second claim
prevents duplicate processors; only one active job may reserve a document/profile.
Repeated start requests for the same preview return the existing job.

**Pause after current operation** stops at the next boundary. Leaving the view or
closing the browser stops sending further steps; an already authorized in-flight
operation may finish. The backend does not continue in a background worker or start
unattended publication on restart. Open **Publication history**, select the job and
choose **Continue publication** to resume. Completed steps are not replayed.

The UI distinguishes success, partial progress, failure, conflict and uncertainty.
Confirmed remote changes remain after a later error; a Confluence hierarchy is not
one remote transaction. No automatic rollback deletes pages. **Abandon publication**
releases a known-result job while preserving remote objects and mappings; use a new
preview for later work. A job with an unresolved ambiguous write cannot be abandoned
until its result is identified or explicitly resolved.

Authentication/network rejections before a write can be retried. HTTP 429 respects
its bounded Retry-After delay. A changed destination audience, remote hierarchy,
page version/hash or attachment identity stops further writes. Source-access checks
apply on every request, including old baseline permissions retained after a scope
change. Revoked permissions block job details, lists and mutation endpoints.

### Uncertain writes and interrupted processes

A durable send marker is stored before an HTTP mutation. Timeout, interrupted or
unreadable successful response, redirect or server error can mean that Confluence
already applied it. **Reconcile publication** reads the remote state first:

- A created page is accepted only when its ownership and operation anchors match,
  its identity is unique, and its expected version, title, space and parent match.
- An interrupted PUT can be accepted via its marker, or repeated only if the exact
  original version/hash remains unchanged. Its version check prevents two successful
  updates, including delayed competing requests.
- An uploaded attachment requires its operation comment, expected version and exact
  frozen SHA-256. It is not re-uploaded just because a response was lost.

After a backend interruption, wait for an in-flight claim to expire and refresh the
job before reconciling. If a created page was renamed, **Identify marked page** can
supply its ID; both anchors must match, and external changes still become conflicts.
If no created page/file is visible, reconciliation remains uncertain rather than
blindly resending. Only an operator who checked Confluence server logs and confirmed
that the original create/upload was not applied should use **Confirm write was not
applied**. This audited manual exception resets that step for a guarded new attempt.

PAT rotation can be performed without discarding confirmed work. After updating the
profile, **Revalidate connection** explicitly checks the new profile revision,
unchanged URL/space/parent and the captured audience before resuming the job. A
reserved destination cannot be moved to another URL/space/parent while work is
active. Rotating credentials does not authorize a changed reader audience or bypass
remote content conflicts.

### Deployment and acceptance

No new packages or services are required beyond Phase 3 dependencies. Restart the
backend to add the job/step tables and `preserve_remote` mapping column; migrations
retain existing documents, profiles, previews, mappings and immutable export bytes.
Use the rebuilt frontend. Existing Read/Publish and retained source permissions
control publication; Manage Confluence remains a separate profile-management grant.
Back up the tenant DB and original credential key as described above.

Before publishing production documentation, run connection checks and a reviewed
publication in an approved test space on the real installation. Confirm intended
readers, native links/PNG attachments, repeated publication and recovery behavior.
The automated simulator covers these protocol paths but cannot certify an unknown
Confluence installation or its local permission policy.
