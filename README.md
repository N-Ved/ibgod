# IB God

A personal study planner for IB Diploma students that sits on top of the material drive (`/mnt/files/docs`).
Students pick their subjects, levels, current and target grades, textbooks and available time; the app builds a
study plan to exam day, links every session to the right notes, textbook pages, question-bank sections, videos and
past papers on the drive, checks every change to the schedule for problems, and can be re-planned at any time.
It has no AI features (an earlier coach and feedback writer were removed). Everything runs on this server.

## How it fits into the server

```
Internet -> Cloudflare tunnel -> Caddy -> Authelia (2FA) -> ibgod:8080
                                                              |-- /mnt/files/docs (read-only)
                                                              '-- /opt/fileserver/filebrowser-data (read-only: FileBrowser's access rules)
```

- Separate compose project in this folder. It never rebuilds or restarts the `fileserver` stack.
- `ibgod` joins the existing `fileserver_apps` network so Caddy can reach it. No host port is published.
- Sign-in is Authelia's. Caddy passes the verified user in `Remote-User`; the app accepts that header **only when the
  connection comes from Caddy's address**, so no other container can impersonate a user. A new Authelia user who
  opens the site is taken straight to the setup page. Members of `lldap_admin` (and the user `admin`) see a server
  panel in Settings.

| Container   | Image                              | Purpose                                              |
|-------------|------------------------------------|------------------------------------------------------|
| `ibgod`     | built from this folder             | web app, API, library index, planner                 |

## Everyday commands

```bash
cd /home/student/projects/ibgod
docker compose up -d --build      # start, or apply an update to the code
docker compose ps                 # both should be "healthy"
docker compose logs -f ibgod      # app log
docker compose down               # stop (data is kept)
```

## Going live (already-running fileserver stack)

`deploy/go-live.sh` adds one site block to the Caddyfile (graceful reload, no downtime) and adds `ibgod.n-ved.com`
to Authelia's two-factor rule (Authelia restarts, so everyone signs in again once). It backs both files up to
`/opt/backups/ibgod-golive-<time>/`, validates each new file before using it, and checks afterwards that the existing
sites answer exactly as before and that a forged identity header is still stopped.

```bash
sudo sh deploy/go-live.sh            # apply
sudo sh deploy/go-live.sh rollback   # undo
```

One step is done in the Cloudflare dashboard, because the tunnel is managed there:
**Zero Trust -> Networks -> Tunnels -> (your tunnel) -> Public Hostname -> Add a public hostname**:
subdomain `ibgod`, domain `n-ved.com`, service `HTTP`, URL `caddy:80`.

## Data

| What                          | Where                                   | Notes                                              |
|-------------------------------|-----------------------------------------|----------------------------------------------------|
| Student plans, grades, chats, drafts and the library index | `data/ibgod.db` (SQLite, ~3 GB) | owner-only permissions. Back this file up. |
| Study material                | `/mnt/files/docs`                       | mounted read-only; the app cannot change it        |

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
- Never indexed or served: top-level folders listed in `IBGOD_EXCLUDE_TOP` (default `lost+found,Shaffy`). Under `home/`
  only `SaveMyExams - Notes` is indexed.
- **FileBrowser's access rules apply here too**, read live from FileBrowser's own database (see "Who can see what").
- Offline HTML sites (question banks, InThinking, StudyIB) are never rendered on the app's own address; links go to
  `view.n-ved.com`, which already serves them.
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

## Apps page

`#/apps` shows a card for each service on the server (`app/apps.json`; view.n-ved.com is deliberately left out). A card
is shown only if the person can actually open it: IB God asks Caddy for a small file on that site using the person's own
Authelia session, so the answer follows Authelia's live access_control rules (for example User admin only appears for
`lldap_admin`). The Files card is also hidden without FileBrowser view permission. Results are cached for 5 minutes.
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
| `IBGOD_EXCLUDE_TOP` | `lost+found,Shaffy` | top-level folders never indexed or served |
| `IBGOD_ADMIN_GROUPS` / `IBGOD_ADMIN_USERS` | `lldap_admin` / `admin` | who sees the server panel |
| `IBGOD_INDEX_WORKERS` | `2` | parallel text extraction (low priority) |
| `IBGOD_FB_SOURCE` | `/srv/docs` | FileBrowser's name for the folder mounted here as the library |
| `TZ` | `Europe/Stockholm` | what "today" means |

`IBGOD_DEV_USER` exists for the isolated test copy only (`deploy/dev-up.sh`). The app refuses to start with it set on
a network where Caddy is reachable.

## Security summary

- No published ports; reachable only through Caddy after Authelia. Identity headers are trusted only from Caddy.
- Requests that change anything need a custom header and same-origin checks (plus Caddy's `same_origin_only`), so pages
  on sibling sites such as `view.n-ved.com` cannot act on a student's behalf.
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
deploy/dev-up.sh down
```

`tests/ui/ui_test.mjs` drives a real browser through setup and every screen (see the header of the file).

## Removing it

```bash
sudo sh deploy/go-live.sh rollback       # take it out of Caddy and Authelia
docker compose down                      # stop the containers
```
Then delete the Cloudflare public hostname and, if wanted, this folder.

Note for the fileserver stack: `ibgod` is attached to its `fileserver_apps` network. `docker compose down` in `/opt/fileserver`
will therefore report that this one network is still in use; that is harmless (stop IB God first if you want it removed).
