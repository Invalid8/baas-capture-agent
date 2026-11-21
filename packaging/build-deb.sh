#!/bin/sh
set -eu
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/.." && pwd)
version=$(python3 -c "import sys; sys.path.insert(0, '$root'); import baas_capture_agent; print(baas_capture_agent.__version__)")
stage="$root/build/baas-capture-agent_${version}_all"
rm -rf "$stage"
install -d "$stage/DEBIAN" "$stage/usr/bin" "$stage/usr/lib/baas-capture-agent/baas_capture_agent" \
    "$stage/usr/lib/systemd/user" "$stage/usr/lib/udev/rules.d" "$stage/etc" "$stage/usr/share/doc/baas-capture-agent"
sed "s/@VERSION@/$version/" "$here/control" > "$stage/DEBIAN/control"
install -m 0755 "$here/postinst" "$here/prerm" "$stage/DEBIAN/"
echo /etc/baas-capture-agent.conf > "$stage/DEBIAN/conffiles"
install -m 0755 "$here/baas-capture-agent" "$stage/usr/bin/"
install -m 0644 "$root"/baas_capture_agent/*.py "$stage/usr/lib/baas-capture-agent/baas_capture_agent/"
install -m 0644 "$here/baas-capture-agent.service" "$stage/usr/lib/systemd/user/"
install -m 0644 "$here/baas-capture-agent.conf" "$stage/etc/"
install -m 0644 "$here/70-baas-capture-agent.rules" "$stage/usr/lib/udev/rules.d/"
install -m 0644 "$root/README.md" "$stage/usr/share/doc/baas-capture-agent/"
mkdir -p "$root/dist"
dpkg-deb --build --root-owner-group "$stage" "$root/dist/baas-capture-agent_${version}_all.deb"
