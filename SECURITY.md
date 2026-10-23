# Security Policy

## Supported versions

ZhiXing is currently an alpha project. Security fixes are applied to the latest
commit on the default branch; older snapshots are not maintained as supported
release lines unless a release note states otherwise.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting feature for
`apbocldueo/unimobile` when it is available. If private reporting is not enabled,
contact the repository owner privately through their GitHub profile before
publishing details.

Do not open a public issue containing:

- API keys, access tokens, passwords, cookies, or model credentials;
- Android/Harmony device serials or private profile configuration;
- private host paths, database contents, trajectories, screenshots, or model
  responses;
- exploit instructions before a fix and disclosure plan exist.

Include the affected commit, component, reproduction conditions, impact, and a
minimal redacted proof. You should receive an acknowledgement through the same
private channel; no fixed response-time guarantee is currently offered.

## Scope boundaries

ZhiXing does not claim that arbitrary third-party plugins execute in a security
sandbox. Treat plugins and device adapters as trusted code, use least-privilege
credentials, and run device experiments in an isolated test environment.
