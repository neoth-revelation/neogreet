# Maintainer: neoth-revelation <arek.stankiewicz97@gmail.com>
pkgname=neogreet
pkgver=0.1.0
pkgrel=1
pkgdesc="Modern, sleek Catppuccin Mocha GTK4 greeter for greetd on Wayland"
arch=('any')
url="https://github.com/neoth-revelation/neogreet"
license=('MIT')
depends=('greetd' 'python' 'python-gobject' 'gtk4' 'papirus-icon-theme')
optdepends=(
    'hyprland: Recommended Wayland compositor for greetd'
    'swaybg: For wallpaper rendering in multi-monitor setups'
)
source=("bin/neogreet"
        "LICENSE")
sha256sums=('SKIP'
            'SKIP')

package() {
    install -Dm755 "${srcdir}/bin/neogreet" "${pkgdir}/usr/bin/neogreet"
    install -Dm644 "${srcdir}/LICENSE" "${pkgdir}/usr/share/licenses/${pkgname}/LICENSE"
}
