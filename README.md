# texture-courier

simple program / api that rips texture cache from second life viewers

## goals

- output the entire texture cache in a commonly readable format
- support all platforms that support python
- be as fast as it is practical to be
- use few dependencies

## non goals

- no gui, no bells and whistles
- no option to transform outputs into other formats (this is what graphicsmagick
  or similar is for)

## install & use

install texture-courier with pip

```
pip install texture-courier
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

## prior art

- http://slcacheviewer.com
- https://github.com/jspataro791/PySLCacheDebugger
