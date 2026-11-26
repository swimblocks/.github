#!/usr/bin/env bash
# Download a secret scanner at its pinned release, and print the path to its binary.
#
# Usage:
#   scripts/fetch-scanner.sh gitleaks|trufflehog <dir>
#
# make-public.sh and the secret-scan workflow both fetch their scanners here, so they run the
# same versions. Each download is checked against the release's checksums file, whose own
# SHA-256 is pinned below. To move to a new release, change the version and the hash together:
#   gh release download v<version> -R <owner>/<repo> -p '*_checksums.txt' && sha256sum *_checksums.txt
set -euo pipefail

GITLEAKS_VERSION=8.30.1
GITLEAKS_SUMS_SHA256=061476c21adaf5441516f96f185c1a4706a83cd6329b9b38762271b3d4a52fae
TRUFFLEHOG_VERSION=3.100.1
TRUFFLEHOG_SUMS_SHA256=c277663d2164d6b954445412c1a0783435b1216fd102b48d1e4ce0a9a799e340

name=${1:-}
dir=${2:-}
if [ -z "$name" ] || [ -z "$dir" ]; then
  echo "usage: $0 gitleaks|trufflehog <dir>" >&2
  exit 2
fi

case "$(uname -s)" in
  Linux) os=linux ;;
  Darwin) os=darwin ;;
  MINGW*|MSYS*|CYGWIN*) os=windows ;;
  *) echo "FAIL: no $name release for $(uname -s)" >&2; exit 1 ;;
esac
case "$(uname -m)" in
  x86_64|amd64) arch=amd64 ;;
  aarch64|arm64) arch=arm64 ;;
  *) echo "FAIL: no $name release for $(uname -m)" >&2; exit 1 ;;
esac
ext=""; [ "$os" = windows ] && ext=.exe

case "$name" in
  gitleaks)
    source=gitleaks/gitleaks version=$GITLEAKS_VERSION sums_sha=$GITLEAKS_SUMS_SHA256
    gitleaks_arch=$arch; [ "$arch" = amd64 ] && gitleaks_arch=x64
    archive=tar.gz; [ "$os" = windows ] && archive=zip
    asset="gitleaks_${version}_${os}_${gitleaks_arch}.${archive}"
    ;;
  trufflehog)
    source=trufflesecurity/trufflehog version=$TRUFFLEHOG_VERSION sums_sha=$TRUFFLEHOG_SUMS_SHA256
    asset="trufflehog_${version}_${os}_${arch}.tar.gz"
    ;;
  *) echo "unknown scanner: $name" >&2; exit 2 ;;
esac
sums="${name}_${version}_checksums.txt"

sha256() {
  if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi | cut -d' ' -f1
}

mkdir -p "$dir"
for file in "$sums" "$asset"; do
  curl -fsSL -o "$dir/$file" "https://github.com/$source/releases/download/v$version/$file"
done
if [ "$(sha256 "$dir/$sums")" != "$sums_sha" ]; then
  echo "FAIL: $sums doesn't match the SHA-256 pinned in $0" >&2; exit 1
fi
if [ "$(sha256 "$dir/$asset")" != "$(awk -v a="$asset" '$2 == a { print $1 }' "$dir/$sums")" ]; then
  echo "FAIL: $asset doesn't match $sums" >&2; exit 1
fi
case "$asset" in
  *.zip) python -m zipfile -e "$dir/$asset" "$dir" ;;
  *) tar -xzf "$dir/$asset" -C "$dir" ;;
esac
echo "$dir/$name$ext"
