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

## api

```python
from texture_courier import list_texture_caches, TextureCache

caches = list_texture_caches()
# [PosixPath('/Users/meri/Library/Caches/Firestorm_x64/texturecache')]

cache = TextureCache("/Users/meri/Library/Caches/Firestorm_x64/texturecache")
# <TextureCache /Users/meri/Library/Caches/Firestorm_x64/texturecache, 26478 textures, 3 GB>

# the api implements an iterator and __getitem__, so you can interact with it like a list
texture = cache["93ff0fc0-731a-b04e-8a66-b6489c059e04"]

with open(f"{texture.uuid}.jp2", "wb") as f:
    f.write(texture.jpeg_2000())

first_ten = cache[:10]

for tex in first_ten:
    print(tex)

# <Texture 93ff0fc0-731a-b04e-8a66-b6489c059e04, 2026-08-21 22:39:00, 20 KB, whole=True>
# <Texture eb2667d6-dbc8-7188-ea0e-2bc8bc8da19b, 2026-08-21 22:39:00, 39 KB, whole=True>
# <Texture f75d9ea7-2c6f-3d11-5645-7c7c0a195721, 2026-08-21 22:38:58, 597 bytes, whole=True>
# ...
```

## hacking

i use `pip install --editable .` to install texture-courier as an editable
package, which allows the cli to be used like it was installed from pip.

[lltexturecache.h](https://github.com/secondlife/viewer/blob/develop/indra/newview/lltexturecache.h)
is the authoritative implementation of the texture cache, which much of this implementation was
engineered out of.

## prior art

- http://slcacheviewer.com
- https://github.com/jspataro791/PySLCacheDebugger
