# texture-courier

program that rips texture cache from second life viewers

## goals

- output the entire texture cache in a commonly readable format
- support all platforms that support python
- be as fast as it is practical to be
- use few dependencies

## non goals

- no gui, and no bells and whistles
- no option to transform outputs into other formats (this is what graphicsmagick 
or similar is for)

## install & use

install texture-courier via pip

```
pip install texture-courier
```

locate your texture cache, and provide it like so

```
texture-courier /Users/meri/Library/Caches/Firestorm_x64/texturecache
```

this dumps the contents of the cache to a directory (by default, to  
`./texturecache`).

see `texture-courier --help` for other options.

## hacking

i use `pip install --editable .` to install texture-courier as an editable
package, which allows it to be used like it was installed from pip.

## prior art

- http://slcacheviewer.com
- https://github.com/jspataro791/PySLCacheDebugger
