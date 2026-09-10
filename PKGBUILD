# Maintainer: neoth-revelation <https://github.com/neoth-revelation>
pkgname=neogreet
pkgver=0.1.0
pkgrel=2
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
# Checkout-local build: file:// explicitly locates sources in subdirectories;
# makepkg stores the renamed files at the top of srcdir.
# A separately published AUR package should use a tagged source archive instead.
source=("neogreet::file://${startdir}/bin/neogreet"
        "LICENSE"
        "neogreet.conf::file://${startdir}/examples/neogreet.conf"
        "greetd-config.toml::file://${startdir}/examples/config.toml"
        "hyprland.conf::file://${startdir}/examples/hyprland.conf")
sha256sums=('0a64031c85fae26f8328af08383e4621999ef11db3cc11ffe4d15c3f67b10a53'
            '058fc0fb157ccd4b064b0bf443dc6826e3127a07777e2a92b92ac696a5a48196'
            'a987a00ffda591508a0794c1b737e3f23a459a78a1b536a158c11c478a29bf46'
            '3b6b6c6f6313ce111a67d981322acfd80742747443457d66bb74621c93f63805'
            '4660962838bdea53ce41262fce41c33108b6fbf7f65267c114d176a77d4f3947')

package() {
    install -Dm755 "${srcdir}/neogreet" "${pkgdir}/usr/bin/neogreet"
    install -Dm644 "${srcdir}/LICENSE" "${pkgdir}/usr/share/licenses/${pkgname}/LICENSE"
    install -Dm644 "${srcdir}/neogreet.conf" "${pkgdir}/usr/share/doc/${pkgname}/neogreet.conf"
    install -Dm644 "${srcdir}/greetd-config.toml" "${pkgdir}/usr/share/doc/${pkgname}/config.toml"
    install -Dm644 "${srcdir}/hyprland.conf" "${pkgdir}/usr/share/doc/${pkgname}/hyprland.conf"
}
