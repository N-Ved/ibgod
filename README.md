# IB God

> **Open-source status:** IB God is released under the MIT License. This repository contains the application,
> subject catalogue, browser client, container definition, and test harness. It does not include study-drive
> content, FileBrowser data, authentication configuration, or any other private deployment data.

IB God is a self-hosted application. The included Compose file is a reference deployment: provide your own
library, data directory, reverse proxy, authentication, and optional companion services through `.env`. The
`n-ved.com` deployment details below are an example of one installation, not a requirement.

## Quick start

1. Copy `.env.example` to `.env` and set `IBGOD_LIBRARY_PATH` and `IBGOD_FILEBROWSER_DATA_PATH`.
2. Create the referenced directories, then start the service:

   ```bash
   mkdir -p library filebrowser-data data
   docker compose up -d --build
   ```

3. Put the service behind an authentication-aware reverse proxy. The app deliberately refuses direct requests
   unless `IBGOD_DEV_USER` is set for an isolated local test instance.

For local development, use `deploy/dev-up.sh`; it keeps the development port bound to loopback and uses a
fixed test identity. See [CONTRIBUTING.md](CONTRIBUTING.md) for the test workflow.

## Configuration

All deployment-specific values are environment variables. `.env.example` documents the important settings,
including the trusted proxy, public hosts used for same-origin checks, administrator identities, optional
document links, and the Compose network. `app/apps.json` is intentionally empty in the open-source distribution;
set `IBGOD_APPS_FILE` to a JSON catalogue if your deployment has companion services.

IB God is a study planner for IB Diploma students that sits on top of a material drive. Students pick their
subjects, levels, current and target grades, textbooks and available time; the app builds a study plan to exam
day, links every session to the right notes, textbook pages, question-bank sections, videos and past papers on
the drive, checks every change to the schedule for problems, and can be re-planned at any time.
It has no AI features (an earlier coach and feedback writer were removed). Everything runs in your self-hosted
instance.

## Reference deployment

```
Internet -> reverse proxy -> authentication (2FA) -> ibgod:8080
                                                       |-- library (read-only)
                                                       '-- FileBrowser data (read-only, optional)
```

- The Compose project does not publish a host port by default.
- Set `IBGOD_EXTERNAL_NETWORK=true` and `IBGOD_NETWORK_NAME` when the reverse proxy runs in another Compose project.
- The proxy passes the verified user in `Remote-User`; the app accepts that header **only when the connection comes
  from a configured trusted proxy**, so another container cannot impersonate a user.

| Container   | Image                              | Purpose                                              |
|-------------|------------------------------------|------------------------------------------------------|
| `ibgod`     | built from this folder             | web app, API, library index, planner                 |

## Everyday commands

```bash
cd /path/to/ibgod
docker compose up -d --build      # start, or apply an update to the code
docker compose ps                 # ibgod should be "healthy"
docker compose logs -f ibgod      # app log
docker compose down               # stop (data is kept)
```

## Going live behind Caddy and Authelia

`deploy/go-live.sh` is a deployment-specific example for the original installation. Adapt its paths, hostname,
network name, and authentication rules before using it elsewhere. The important invariant is that the app must
remain behind authentication and must only trust identity headers from the reverse proxy.

```bash
sudo sh deploy/go-live.sh            # adapt before applying
sudo sh deploy/go-live.sh rollback   # restore the saved configuration
```

If using a tunnel, add the application hostname and point it at the reverse proxy according to your provider's
documentation.

## Data

| What                          | Where                                   | Notes                                              |
|-------------------------------|-----------------------------------------|----------------------------------------------------|
| Student plans, grades, chats, drafts and the library index | `data/ibgod.db` (SQLite, ~3 GB) | owner-only permissions. Back this file up. |
| Study material                | `IBGOD_LIBRARY_PATH`                    | mounted read-only; the app cannot change it        |

The app writes a small daily snapshot of everything students created (not the index) to `data/backups/students-YYYYMMDD.sqlite`
and keeps the newest 14. They are on the same disk as the database, so copy that folder somewhere else now and then.
To restore: stop the stack, open `data/ibgod.db` with `sqlite3`, `ATTACH` the snapshot and copy the tables back.
The library index is derived data: if the database is lost, students' plans are lost but the index rebuilds itself
(about 45 minutes).

## The library index

- On start, and once a day, the app walks the drive, classifies every file (subject, level, paper, session, time zone,
  markscheme, syllabus version, language) and extracts searchable text page by page. Admins can trigger a rescan in
  Settings.
- Only study material is indexed (about 52,000 of 177,000 files; site assets and individual question pages are skipped).
- Never indexed or served: top-level folders listed in `IBGOD_EXCLUDE_TOP` (default `lost+found`).
- **FileBrowser's access rules apply here too**, read live from FileBrowser's own database (see "Who can see what").
- Offline HTML sites can be linked to an optional separately hosted viewer configured with `IBGOD_VIEW_BASE`; they are
  never rendered on the app's own address.
- Old-syllabus papers, books and notes are kept but labelled, and the planner prefers current-syllabus papers.

## Who can see what

Nothing about file access is configured in IB God. It reads FileBrowser's database and `config.yaml` (mounted read-only)
and re-reads them whenever they change (checked every 30 seconds), so a change made in FileBrowser's admin settings
applies to IB God within about half a minute, for every user, with no restart:

- a user's folder scope and `view` permission for the `docs` source;
- access rules on folders or files (Allow / Deny by user or FileBrowser group, "deny all"), inherited by everything
  below the folder, most specific rule winning;
- FileBrowser groups and `denyByDefault`;
- people who have never opened FileBrowser get FileBrowser's defaults from `config.yaml`, just as FileBrowser would.

This covers search, topic materials, past papers, the textbook picker, saved items and direct file links (a hidden file
returns "not found"). The planner only schedules papers the student can open. If FileBrowser's data cannot be read, IB
God shows nothing rather than everything. The admin panel in Settings shows how many FileBrowser users and rules it read.

## My works (Language A and B)

Each Language A / B subject page has a **My works** tab. Students add the texts they study (title, author, form, and
whether it is for Paper 2, the individual oral or the HL essay) and can upload their own copy (PDF, EPUB, Word or
plain text, up to 24 MB; 40 works and 400 MB per student). Each work:
- is matched to the LitCharts study guides on the drive by title;
- becomes an item in the subject's master checklist ("Your works"), so the planner schedules "Read and annotate",
  "Write about" (timed Paper 2 practice) and spaced reviews for it, following its checklist level;
- shows "Your copy" and its study guides in the matching plan tasks.

Files are checked by their content (a renamed program is refused), stored under `data/works/` with random names,
and only ever served to their owner: PDF and text inline under a sandboxing policy, EPUB/Word as downloads. Removing
a work deletes its file and its planned sessions; deleting the account deletes every upload. The daily snapshot covers
the works list but not the files themselves: back up `data/works/` along with `data/ibgod.db`.

## Apps page

`#/apps` shows a card for each configured companion service (`app/apps.json`). A card
is shown only if the person can actually open it: IB God asks Caddy for a small file on that site using the person's own
Authelia session, so the answer follows Authelia's live access_control rules (for example an administrator-only
service can be restricted by group). The Files card is also hidden without FileBrowser view permission. Results
are cached for 5 minutes.
To add a service, add an entry to `app/apps.json` and rebuild.

## The planner in brief

- Time is shared between subjects by level and grade gap; inside a subject it follows the grade band
  (a 3 spends most time on content, a 6 on timed papers).
- Each topic is learned, practised with exam questions the next day, and reviewed at growing gaps (spaced retrieval).
  Timed papers start once most content is covered; the newest papers are kept for the end; attempted papers are not
  scheduled again.
- **Master checklist** (subject page, Topics tab): each topic is marked Not started / Introduced / Familiar / Revised / Secure,
  one by one, per unit or for the whole subject. Re-planning then schedules only what is still needed: Learn + Practise +
  reviews for new topics, a half-length Consolidate for taught ones, Practise + reviews for familiar ones, reviews only for
  revised ones and a single maintenance review for secure ones. Finishing a Learn or Practise session raises a topic's level
  automatically (never lowers it).
- **Clear plan** (Plan page) deletes every session so a student can start again; subjects, grades, time settings, days off,
  paper scores and the checklist are kept unless the student also ticks "reset checklist".
- A fresh plan never exceeds the student's available time. When time is short the programme is thinned and the student
  is told plainly that the hours do not cover the target.
- Every edit (move, resize, add, day off) is checked. New problems are shown immediately and can be dismissed; a
  dismissal lasts until the situation changes. "Re-plan" redistributes everything unfinished from today and keeps
  completed work and anything the student placed by hand.
- The evidence behind these choices, with sources, is in the app under **Study methods** (`app/knowledge.py`).


## Settings (environment variables in `docker-compose.yml`)

| Variable | Default | Meaning |
|---|---|---|
| `IBGOD_EXCLUDE_TOP` | `lost+found` | top-level folders never indexed or served |
| `IBGOD_ADMIN_GROUPS` / `IBGOD_ADMIN_USERS` | empty / `admin` | who sees the server panel |
| `IBGOD_INDEX_WORKERS` | `2` | parallel text extraction (low priority) |
| `IBGOD_FB_SOURCE` | `/srv/docs` | FileBrowser's name for the folder mounted here as the library |
| `TZ` | `UTC` in Compose | what "today" means |

`IBGOD_DEV_USER` exists for the isolated test copy only (`deploy/dev-up.sh`). The app refuses to start with it set on
a network where Caddy is reachable.

## Security summary

- No published ports; reachable only through Caddy after Authelia. Identity headers are trusted only from Caddy.
- Requests that change anything need a custom header and same-origin checks, so sibling sites cannot act on a
  student's behalf.
- Strict Content-Security-Policy (no inline or third-party scripts; the one UI library is vendored:
  `web/vendor/preact-htm.js`, htm 3.1.1 + Preact, sha256 `72284e8e9079c87817145df1110f74e8a2aa040b2fc384922e18dfcb46fc1fd7`).
- Files are addressed by index id, never by path; HTML from the drive is never rendered on this origin.
- Container: non-root, read-only root filesystem, all capabilities dropped, memory/process limits, no internet.
- Each student sees only their own plan and progress, can export everything, and can delete it all.

## Tests

`deploy/dev-up.sh` starts an isolated copy on `127.0.0.1:18081` with a fake user (no Caddy, no Authelia, own network).

```bash
deploy/dev-up.sh                         # start test copy
python3 -I tests/t03_profiles.py         # eight very different students: plans must be consistent and fit their time
python3 -I tests/t04_edits.py            # edits, issue reporting/dismissal, re-planning
python3 -I tests/t05_library.py          # what topics, searches and paper lists return
python3 -I tests/t09_coverage.py         # master checklist and clear-plan
python3 -I tests/t10_access.py <dir>     # FileBrowser rules (needs dev-up.sh started with a scratch copy of FileBrowser's data)
python3 -I tests/t11_works.py            # My works (needs a second copy as another user on 127.0.0.1:18082, see the file)
deploy/dev-up.sh down
```

`tests/ui/ui_test.mjs` drives a real browser through setup and every screen (see the header of the file).

## Removing it

```bash
sudo sh deploy/go-live.sh rollback       # take it out of Caddy and Authelia
docker compose down                      # stop the containers
```
Then remove the public hostname from your proxy or tunnel and, if wanted, this folder.
