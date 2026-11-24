# Security policy

## Supported versions

The default branch is the supported version. Older snapshots may not receive security fixes.

## Reporting a vulnerability

Please do not report security vulnerabilities in a public issue. Use
[GitHub's private vulnerability reporting](https://github.com/N-Ved/ibgod/security/advisories/new) when
available. If it is unavailable, contact the repository owner privately through GitHub and include the
affected version, reproduction steps, impact, and any suggested mitigation.

Please allow reasonable time for investigation and coordinated disclosure. Do not include real student data,
credentials, private files, or other sensitive information in a report.

## Deployment notes

IB God is designed to run behind an authentication-aware reverse proxy. Do not expose the container directly
to an untrusted network, and never enable `IBGOD_DEV_USER` in a production deployment. Keep the mounted
library and FileBrowser data read-only, protect the writable data directory, and configure
`IBGOD_TRUSTED_PROXY_HOSTS` narrowly.
