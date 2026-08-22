![Courier from Hello Girl](https://github.com/furudean/texture-courier/blob/main/courier.png?raw=true)

# texture-courier

simple CLI program and high-level python API to interact with the second life texture cache

## goals

- output the entire texture cache in a commonly readable format
- support all platforms that support python
- be as fast as it is practical to be
- use few dependencies

## non goals

- no gui, no bells and whistles
- no option to transform outputs into other formats, as i believe this is better covered by other programs

## use CLI

install texture-courier from PyPI. conventionally this is done with pip. but [uv tool install](https://docs.astral.sh/uv/guides/tools/#installing-tools) gives you proper dependency isolation without having to worry about environments.

```bash
# with uv (preferred)
uv tool install texture-courier[cli]

# with pip
pip install texture-courier[cli]
```

then, run it on the command line like

```
texture-courier
```

texture-courier will attempt to find any texture caches on the system
automatically. if this does not work, find your texture cache and provide it
like so

```
texture-courier /Users/meri/Library/Caches/Firestorm_x64/texturecache
```

this dumps the contents of the cache to a directory (by default, to  
`./texturecache`).

see `texture-courier --help` for other options.

## hacking

i use `pip install --editable .` to install texture-courier as an editable
package, which allows the cli to be used like it was installed from pip.

[lltexturecache.h](https://github.com/secondlife/viewer/blob/develop/indra/newview/lltexturecache.h)
is the authoritative implementation of the texture cache, which much of this implementation was
engineered out of.

## prior art

- http://slcacheviewer.com
- https://github.com/jspataro791/PySLCacheDebugger
