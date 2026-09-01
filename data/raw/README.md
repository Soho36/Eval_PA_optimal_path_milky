# Raw inputs

Place immutable upstream artifacts here. The directory contents are ignored by
Git because trade files can be large; every imported file must nevertheless be
listed in a run/import manifest with:

- original absolute path and upstream project;
- upstream Git revision;
- SHA-256 and byte size;
- extraction/copy date and command;
- schema/version and effective time range.

Never edit a raw input in place.
