#!/usr/bin/env sh

set -eu

cd "$(dirname "$0")/.."

section="${1:-}"

if [ -z "$section" ]; then
	echo "usage: $0 <section>" >&2
	exit 2
fi

changelog="CHANGELOG.md"

if ! awk -v section="$section" \
	'$1 == "##" && $2 == section { found = 1; exit } END { exit !found }' \
	"$changelog"; then
	echo "err: no '## $section' section in $changelog" >&2
	exit 1
fi

notes="$(
	awk -v section="$section" \
		'$1 == "##" && $2 == section { f = 1; next } f && /^## / { exit } f { print }' \
		"$changelog" |
		awk 'NF { for (i = 0; i < held; i++) print ""; held = 0; print; seen = 1; next }
		     seen { held++ }'
)"

if [ -z "$notes" ]; then
	echo "err: the $section section in $changelog is empty" >&2
	exit 1
fi

printf '%s\n' "$notes"
