# Changelog

## 2.0.0

### Breaking changes

- Docker images no longer support `linux/arm/v7`. The last version with an
  ARMv7 image is `v1.0.2`; pin that version if ARMv7 support is required.
- PostgreSQL and PostGIS backup and restore require server major versions
  14 through 18, with a matching client installed in the image. The last
  version with the previous client compatibility is `v1.0.2`, which contains
  PostgreSQL 15 client tools and can dump older servers. Users of servers
  older than 14 should remain on `v1.0.2` until they upgrade and verify their
  backup and restore procedures.

### Added

- Support for MongoDB, Redis and GraphDB Free.
- Configurable backup extensions and gzip compression.
- PostGIS pre-restore scripts for installed extensions such as pgvector.
- PostgreSQL client selection based on the server major version.

### Changed

- The restore CLI returns a non-zero exit code when a restore fails or no
  matching backup is found. It also extracts database names from generated
  backup filenames without including their timestamps.
- Compressed restores use isolated temporary directories.
- Automatic restore and retention only select scheduler-generated backup
  filenames, excluding auxiliary and recovery files and matching database names
  exactly. Nonstandard backup filenames can still be restored by explicit path.
- GraphDB Free exports explicit RDF statements in N-Quads, including blank
  nodes and named graphs. Restore saves a recovery snapshot before replacing
  data. It is not atomic; stop other writes during the operation.

### Upgrade notes

- GraphDB RDF backups do not include repository configuration, namespaces,
  accounts or other instance-level data. The destination repository must exist
  with a compatible configuration.
- Restoring gzip files requires enough space on the temporary filesystem.
  GraphDB restore also requires writable persistent space beside the backup
  for a recovery snapshot.
- The `latest` tag includes the 2.0.0 breaking changes. Pin an explicit image
  version when automatic major-version changes are undesirable.
