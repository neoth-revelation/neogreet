# Maintainer: neoth-revelation <https://github.com/neoth-revelation>
pkgname=neogreet
pkgver=0.1.0
pkgrel=3
pkgdesc="Modern, sleek Catppuccin Mocha GTK4 greeter for greetd on Wayland"
arch=('any')
url="https://github.com/neoth-revelation/neogreet"
license=('MIT')
depends=('greetd' 'python' 'python-gobject' 'gtk4>=4.8')
optdepends=(
    'hyprland: Recommended Wayland compositor for greetd'
    'swaybg: For wallpaper rendering in multi-monitor setups'
    'papirus-icon-theme: Optional symbolic icon theme'
    'ttf-jetbrains-mono-nerd: Optional theme font'
)
# Checkout-local build. Include the actual content hash in downloaded filenames
# so makepkg never reuses stale file:// copies after editing or pulling updates.
# Expected checksums below remain independent and must still be maintained.
# A separately published AUR package should use a tagged source archive instead.
_files=('bin/neogreet' 'LICENSE' 'examples/neogreet.conf'
        'examples/config.toml' 'examples/hyprland.conf')
source=()
for _file in "${_files[@]}"; do
    _hash=$(sha256sum -- "${startdir}/${_file}")
    _path="${startdir}/${_file}"
    _path=${_path//%/%25}
    _path=${_path// /%20}
    _path=${_path//#/%23}
    _path=${_path//\?/%3F}
    _path=${_path//\[/%5B}
    _path=${_path//\]/%5D}
    source+=("${_hash%% *}-${_file##*/}::file://${_path}")
done
sha256sums=('3e8f69b0f4157c9adbdba1f0c839cac78fdda04f37a6c9ce58a1e75064c51138'
            '058fc0fb157ccd4b064b0bf443dc6826e3127a07777e2a92b92ac696a5a48196'
            'a987a00ffda591508a0794c1b737e3f23a459a78a1b536a158c11c478a29bf46'
            '3b6b6c6f6313ce111a67d981322acfd80742747443457d66bb74621c93f63805'
            '4660962838bdea53ce41262fce41c33108b6fbf7f65267c114d176a77d4f3947')

package() {
    install -Dm755 "${srcdir}/${source[0]%%::*}" "${pkgdir}/usr/bin/neogreet"
    install -Dm644 "${srcdir}/${source[1]%%::*}" "${pkgdir}/usr/share/licenses/${pkgname}/LICENSE"
    install -Dm644 "${srcdir}/${source[2]%%::*}" "${pkgdir}/usr/share/doc/${pkgname}/neogreet.conf"
    install -Dm644 "${srcdir}/${source[3]%%::*}" "${pkgdir}/usr/share/doc/${pkgname}/config.toml"
    install -Dm644 "${srcdir}/${source[4]%%::*}" "${pkgdir}/usr/share/doc/${pkgname}/hyprland.conf"
}
