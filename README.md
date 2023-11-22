# texture-courier

program that rips texture cache from second life viewers

## goals

- work on all platforms (that support python)
- output the cache exactly as it is
- be as fast as it is practical
- no dependencies

## non goals

texture-courier should not transform the cache in any way. we output things as
they are. that means no gui, and no bells and whistles.

## install & use

install texture-courier via pip

```
pip install texture-courier
```

locate your texture cache, and provide it like so

```
texture-courier /Users/meri/Library/Caches/Firestorm_x64/texturecache
```

this dumps the contents of the cache folder to a folder (default
`./texturecache`).

use `texture-courier -h` for other options.

## prior art

- http://slcacheviewer.com
- https://github.com/jspataro791/PySLCacheDebugger
