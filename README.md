# texture-courier

program that rips texture cache from second life viewers

## goals

- work on all platforms (that support pip)
- be as fast as possible
- no dependencies

## non goals

texture-courier should not transform or present the cache in any way. we output
things as they are. that means no gui, and no bells and whistles.

## install & use

install texture-courier from pip

```
pip install texture-courier
```

locate your texture cache, and provide it like this

```
texture-courier /Users/meri/Library/Caches/Firestorm_x64/texturecache
```

this dumps the contents of the cache folder to the provided folder (default
`./texturecache`).

these files will be in j2c, a jpeg2000 derivative. many programs and operating
systems do not read this natively, and may need conversion. you may want to use
a utility to convert these. [graphicsmagick](http://www.graphicsmagick.org) is a
good place to start.

if you want to convert everything in a directory, this command should do the job:

```
for i in [ *.j2c ]; gm convert "$i" (basename "$i" ".j2c").png; end
```

use `texture-courier -h` for other options.

## prior art

- http://slcacheviewer.com
- https://github.com/jspataro791/PySLCacheDebugger
