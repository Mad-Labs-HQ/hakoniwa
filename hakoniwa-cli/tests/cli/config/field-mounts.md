# CfgMount

## CfgMount#destination `NULL`

An omitted destination keeps the source path. With `rw` omitted, the bind must
remain read-only, even when the host mount is writable.

```console
$ hakoniwa run --config ./tests/fixtures/config/field-mounts.toml -- findmnt /sys
TARGET [..] OPTIONS
/sys [..] ro,[..]

```

## CfgMount#rw `false`

```console
$ hakoniwa run --config ./tests/fixtures/config/field-mounts.toml -- findmnt /rodir
TARGET [..] OPTIONS
/rodir [..] ro,[..]

```

## CfgMount#rw `true`

```console
$ hakoniwa run --config ./tests/fixtures/config/field-mounts.toml -- findmnt /rwdir
TARGET [..] OPTIONS
/rwdir [..] rw,[..]

```

## CfgMount#type `devfs`

```console
$ hakoniwa run --config ./tests/fixtures/config/field-mounts.toml -- dd if=/mydev/random of=/mytmp/output.txt count=1 bs=4
1+0 records in
1+0 records out
4 bytes copied, [..]

```

## CfgMount#type `tmpfs`

```console
$ hakoniwa run --config ./tests/fixtures/config/field-mounts.toml -- findmnt /mytmp
TARGET [..] OPTIONS
/mytmp [..] rw,nosuid,nodev,[..]

```
