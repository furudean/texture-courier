# Changelog

## unreleased

- cli: read and decode textures on multiple threads for faster cache dumps
- cli: more precise elapsed-time output, plus a total bytes-written summary on completion
- cli: replaced the output-mode flags with `--debug` / `--quiet`, simplifying output
- removed CLI `--watch` and `TextureCache.watch()`

## v0.0.16 - 2026-09-01

- less strict sanity check for `texture.entries`

## v0.0.15 - 2026-09-01

- fixes an import error

## v0.0.14 - 2026-09-01

### breaking

- `Texture.thumbnail_png()` replaced by `Texture.thumbnail`, returning `Thumbnail | None`. encode with `texture.thumbnail.png()`
- `TextureCache.fast_cache_file`, which handed out the open `BytesIO`, is replaced by the boolean `TextureCache.has_fastcache`. the file handle is private
- `Thumbnail.size` is renamed to `Thumbnail.dimensions`
- `encode` is no longer exported from the package root

### added

- `Thumbnail` is exported from the package root
- `Thumbnail.source_dimensions`, the dimensions of the texture the thumbnail was reduced from, and `Texture.dimensions()` as a shortcut to it

### fixed

- FastCache slots with a discard level outside `0..16` are rejected. unwritten slots carry junk in that field that were being read as valid thumbnails

## v0.0.13 - 2026-08-24

### breaking

- `texture.loads()` is now `texture.codestream()`
- `loads_jp2()` is now `jpeg_2000()`
- `loads_thumbnail()` is now `thumbnail_png()`
- `is_downloaded()` is now `whole()`
- `cache.watch()` hands back a custom `Watch` class instead of a watchdog observer
- `texture_entries_file` and `texture_cache_file` are now private
- deps moved to extras — `texture-courier[cli]` for the command line, `[watcher]` for live updates, base package has none

### added

- implemented `__getitem__` for cache, so `cache[i]`, `cache[1:2]`, and `cache["uuid"]` works
- `entry in cache` works, entries are hashable and orderable, equality accounts for image size
- `codestream()` and `jpeg_2000()` verify head/body sizes and the jp2 start and end markers, `verify=False` opts out
- `Watch` is a context manager with `stop()`, `join()`, `is_alive()`, plus `on_error` and `debounce`
- `__all__` and `py.typed`. proper types in package

### fixed

- refresh no longer loses textures when a slot's occupant moves rows
- textures rebind instead of mutating in place, so a held reference stays consistent
- evicted textures drop out on refresh instead of lingering after a cache clear
- torn reads of a cache the viewer is mid-write on go to `on_error` instead of killing the watch
- a handler that raises no longer takes the watch down with it
- watch listens on every event kind, catching rename-swaps on linux and delete/create on a clear

### changed

- refresh diffs `texture.entries` are more cpu efficient
- `FastCache.cache` is only read when something asks for a thumbnail
- watch debounces at 200ms with a 2s ceiling, one shared observer across all watches
- incomplete-texture errors carry a reason
- `--watch` exits 74 when the watch dies on its own

## v0.0.12 - 2026-08-14

- is now 40x faster encoding jp2 because of custom container encoding
- drops pillow as a dep, was previously used for this
- adds a thumbnail api for FastCache. cli can dump with `--thumb`
- handle incomplete textures properly, based on ref impl.

## v0.0.11 - 2024-03-19

- handle incomplete files better
- nicer output
- deps are more lenient

## v0.0.10 - 2024-02-22

- correct appdata folder on windows
- add integrity checks
- improve logging with `--watch`

## v0.0.9 - 2024-02-19

bugfix

## v0.0.8 - 2023-12-09

- arguably more sensible output for `-O files`

## v0.0.7 - 2023-12-09

- adds a `--watch` option
- refactor

## v0.0.6 - 2023-12-03

- added linting and type checking to CI
- adopted Dependabot
- fixed a texture-encoding bug

## v0.0.5 - 2023-12-01

- automatically find the viewer's cache directory
- fault-tolerant cache scanning
- added output modes
- initial integrity checking

## v0.0.4 - 2023-11-22

- moved dependencies into `pyproject.toml`
- updated the PyPI publishing action

## v0.0.3 - 2023-11-22

- early fixes following the initial release

## v0.0.2 - 2023-11-22

- initial release of the `texture-courier` CLI
