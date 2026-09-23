#!/usr/bin/env sh

set -eu

cd "$(dirname "$0")/.."

bump="${1:-}"

case "$bump" in
	major | minor | patch) ;;
	*)
		echo "usage: $0 <major|minor|patch>" >&2
		exit 2
		;;
esac

if [ -n "$(git status --porcelain)" ]; then
	echo "error: git working tree is dirty. commit or stash changes first" >&2
	exit 1
fi

prev_version="$(uv version --short)"
version="$(uv version --bump "$bump" --dry-run --short)"
tag="v$version"

if git rev-parse --verify --quiet "refs/tags/$tag" >/dev/null; then
	echo "error: tag $tag already exists" >&2
	exit 1
fi

changelog="CHANGELOG.md"

./scripts/changelog-notes.sh unreleased >/dev/null

uv version --bump "$bump"

date="$(date -u +%Y-%m-%d)"
tmp="$(mktemp)"
awk -v heading="## $tag - $date" \
	'!done && /^## unreleased$/ { print heading; done = 1; next } { print }' \
	"$changelog" >"$tmp"
mv "$tmp" "$changelog"

git add pyproject.toml uv.lock "$changelog"
git commit -m "release $tag"
git tag "$tag"
commit="$(git rev-parse --short HEAD)"
branch="$(git rev-parse --abbrev-ref HEAD)"

echo ""
echo "made commit for $tag (from v$prev_version) on branch $branch"
echo ""
echo "to push the commit and tag, which triggers the release workflow, run:"
echo "  git push origin HEAD && git push origin $tag"
echo ""
echo "to undo the commit and remove the tag, run:"
echo "  git tag -d $tag && git reset $commit^"
