Community post; retrieved 2026-11-05T22:50:11.833805+08:00. Author: trinity. Last edited: 2026-07-11T16:36:06.106Z.

This post catalogs all the available operating systems available for the uConsole. The uConsole is compatible with a very wide variety of cores, also known as compute modules, which differ in capability, hardware design, and occasionally even architecture, and so these operating systems are grouped by system module, as none support them all. For a guide to hardware, see the [companion hardware directory](https://forum.clockworkpi.com/t/22222)

There are a lot of operating system images floating around the forum. You can help by contributing more if you find they aren’t in these lists. **ClockworkPi uConsoles currently only work with Linux** as their peripherals need [custom kernel patches](https://github.com/clockworkpi/uConsole/tree/master/Code/patch), so although these are all separate OSes, they do all share the kernel Linux, with the lone exception being EwokOS for the CM4 uConsole.

A given uConsole Linux distribution needs core support and a Linux kernel patch to support the screen, an LVDS panel connected through DSI. [Newer consoles have a slightly different panel and need an OS updated to support it](https://forum.clockworkpi.com/t/21666). It also needs a patch to support the battery controller.

## ClockworkPi cores

ClockworkPi’s first-party cores include the [A-04](https://www.clockworkpi.com/product-page/clockworkpi-core-a-0402) and [A-06](https://www.clockworkpi.com/product-page/clockworkpi-core-a-06), each 64-bit ARM, and the [R-01](https://www.clockworkpi.com/product-page/copy-of-clockworkpi-core-r-01), which is 64-bit RISC-V. They all use the Raspberry Pi Compute Module form factor, which is the DDR2 SO-DIMM form factor.

The uConsole was originally offered with one of three cores; the A-04 (cancelled prior to shipping), the A-06, or the Raspberry Pi CM4. There are no operating systems compatible with the A-04 on the uConsole.

| core | operating system | kernel version | format | URLs |
| --- | --- | --- | --- | --- |
| R-01 | Ubuntu 22.04 | unknown | unknown | [thread](https://forum.clockworkpi.com/t/13375/) |
| R-01 | ClockworkOS | 5.4.61 | .img | [GitHub](https://github.com/clockworkpi/uConsole#uconsole-os-images), [direct download](http://dl.clockworkpi.com/uConsole_R01_v1.3b.img.7z), [Google Drive](https://drive.google.com/file/d/1lDdO3-aj8zeO6JDJVBaCgNkehhffdNm1/view) |
| A-06 | Armbian 22.02 | 5.15.25 | source | [thread reply](https://forum.clockworkpi.com/t/uconsole-os-images/10432/15), [GitHub](https://github.com/LibreRetroToy/armbian-clockworkpi-a06/) |
| A-06 | ClockworkOS | 5.15.119 | .img | [GitHub](https://github.com/clockworkpi/uConsole#uconsole-os-images), [direct download](http://dl.clockworkpi.com/uConsole_A06_v1.1e.img.7z), [Google Drive](https://drive.google.com/file/d/1H5wdB_cCSW-qbf6Ijgcn-Uw4EQQkWrP1/view) |
| A-06 | Arch | 5.16.2 | source,.img | [GitHub](https://github.com/css459/arch-linux-arm-clockworkpi-a06) |
| A-06 | Arch | 6.2 | source,.img | [thread](https://forum.clockworkpi.com/t/12804), [GitHub](https://github.com/yatli/arch-linux-arm-clockworkpi) |
| A-06 | Arch | 6.2 | source,.img | [thread reply](https://forum.clockworkpi.com/t/21964/16), [GitHub](https://github.com/cuu/arch-linux-arm-clockworkpi/tree/uc), [Google Drive](https://drive.google.com/file/d/1czWml44COSSELKfZOSgNJB9s0pPAK4oN/view) |
| A-06 | Manjaro | 6.2.7 | .img | [thread reply](https://forum.clockworkpi.com/t/12322/2), [Dropbox](https://www.dropbox.com/scl/fi/q079jvt6icb0eeiy548v5/dt_a06_manjaro_2024_a.img.xz) |
| A-06 | Arch | 6.5.9-0 | source,.img,.pkg.xz | [GitHub](https://github.com/Autianic/clockworkpi-linux) |
| A-06 | NixOS | 6.6 | guide | [NixOS wiki](https://wiki.nixos.org/wiki/NixOS_on_ARM/Clockworkpi_A06_uConsole) |

## Raspberry Pi Compute Modules

Raspberry Pi invented the Compute Module (title cased, as it’s the name of the brand) form factor to be able to embed Raspberry Pi SoCs in places where a full SBC would be inappropriate. Theoretically [the Raspberry Pi Compute Module 1](https://www.raspberrypi.com/products/compute-module-1/) (32-bit ARM) may work in the uConsole but the earliest supported Compute Module in the uConsole is the Compute Module 3, as the CM3+ was sold with the earlier DevTerm (which uses the same ClockworkPi mainboard), and the only [Raspberry Pi Compute Module sold *with* the uConsole](https://www.clockworkpi.com/product-page/uconsole-kit-rpi-cm4-lite) is the Compute Module 4.

After the release of the uConsole, Raspberry Pi [came out](https://www.theregister.com/2024/11/27/raspberry_pi_compute_module_5/) with the Compute Module 5, which remains the latest and most performant Raspberry Pi module.

[@Rex](/u/rex) ’s assembled uConsole operating systems are widely recommended here as he has spent a lot of time making them work well with all the available uConsole hardware and mods. For his files, see [his website](https://images.ak-rex.com/), [MEGA](https://mega.nz/folder/LSInGD6J#0YezWX8xC4PkbyForgl1Hw), [Google Drive](https://drive.google.com/drive/folders/1tw2uPVPsFDhQ5Onx4mlllYexUDmDp0eK), or, updated less frequently, [Drime](https://app.drime.cloud/drive/s/O3faUnk9ihg2vlrgek0LiaHRiU3fGb). **Rex builds and provides these operating systems for free, but if they’re useful to you, consider [buying him a coffee](https://buymeacoffee.com/ak.rex)**.

| Compute Module(s) | operating system | kernel version | format | URLs |
| --- | --- | --- | --- | --- |
| CM4 | Kali | unknown | .img, guide | [thread reply](https://forum.clockworkpi.com/t/12947/4), [wiki page](https://github.com/clockworkpi/uConsole/wiki/Kali-linux-image-for-uConsole-cm4) |
| CM4, CM5 | NixOS | unknown | .img | [thread reply](https://forum.clockworkpi.com/t/12925/136), [GitHub](https://github.com/nixos-uconsole/nixos-uconsole) |
| CM4 | Raspberry Pi OS | unknown | .img | [thread](https://forum.clockworkpi.com/t/14699/), [Google Drive](https://drive.google.com/file/d/1zpYSingDclzp-Np4gC9tCTfzt3gX8RRS/view) |
| CM4 | ClockworkOS | 5.10.17 | .img | [GitHub](https://github.com/clockworkpi/uConsole#uconsole-os-images), [direct download](http://dl.clockworkpi.com/uConsole_CM4_v0.1b_xfce_64bit.img.7z), [Google Drive](https://drive.google.com/file/d/1gBpVK1rMM5zmq5z4-DlKlDmTFJQvwMFz/view) |
| CM4 | Debian 12 | 5.10.17 | .img | [thread](https://forum.clockworkpi.com/t/12738/), [GitHub](https://github.com/Snoozer-94/uConsole-CM4-OS) |
| CM4 | Raspberry Pi OS | 5.10.110 | guide | [Joseph’s Projects](https://jhewitt.net/uconsole) |
| CM3, CM4, CM4S | Debian 12 | 6.1.21 | .img | [thread](https://forum.clockworkpi.com/t/13041) |
| CM4 | Pop\_OS | 6.6.35 | proof of concept | [thread reply](https://forum.clockworkpi.com/t/uconsole-os-images/10432/48) |
| CM4 | Void | 6.6.51 | .img | [thread](https://forum.clockworkpi.com/t/14970), [GitHub](https://github.com/Ravenhammer-Research/void-uconsole) |
| CM3, CM4, CM5 | Debian 12 | 6.6.78 | .img | [thread](https://forum.clockworkpi.com/t/13235), formerly provided by Rex |
| CM3, CM4, CM5 | Manjaro | 6.12.27 | .img | [thread](https://forum.clockworkpi.com/t/14496/), provided by Rex, but only on Drime |
| CM4 | postmarketOS | 6.12.30 | installer | [thread](https://forum.clockworkpi.com/t/12458/), [wiki page](https://wiki.postmarketos.org/wiki/ClockworkPi_uConsole_\(clockworkpi-uconsole-rpi\)) |
| CM3, CM4, CM5 | ParrotOS | 6.12.45 | .img | [thread](https://forum.clockworkpi.com/t/21674), [Google Drive](https://drive.google.com/drive/folders/14rL-_rJfsHyxE3__7YV63bc6FGgdd4DK) |
| CM4, CM5 | Arch | 6.12.51 | source, guide | [thread](https://forum.clockworkpi.com/t/16382), [forgejo](https://gitea.angry.im/PeterCxy/alarm-clockworkpi-uconsole) |
| CM4 | ClockworkOS | 6.12.62-v8+ | .img | [GitHub](https://github.com/clockworkpi/uConsole#uconsole-os-images), [direct download](http://dl.clockworkpi.com/uConsole_CM4_v2.1_64bit.img.bz2), [Google Drive](https://drive.google.com/file/d/19opOCg8v4fdNUhuCaZWnBykgqyoU4-Bx/view) |
| CM4 | Fedora Kinoite 44 | 6.12.62-v8+ | .img | [thread](https://forum.clockworkpi.com/t/22812), [direct download](https://pub-728b0a04c49649fc9d4dd17c95a7bf21.r2.dev/kinoite-uconsole-cm4.img.gz) |
| CM4 | Fedora 44 | 6.12.62-v8+ | .img | [thread](https://forum.clockworkpi.com/t/22812), [direct download](https://pub-728b0a04c49649fc9d4dd17c95a7bf21.r2.dev/fedora-kde-uconsole-cm4.img.gz) |
| CM3, CM4, CM5 | Debian 12 | 6.12.64 | .img | [thread](https://forum.clockworkpi.com/t/14240), [GitHub](https://github.com/crossplatformdev/uConsole-Image-Builder) |
| CM3, CM4, CM5 | Debian 13 | 6.12.64 | .img | [thread](https://forum.clockworkpi.com/t/14240), [GitHub](https://github.com/crossplatformdev/uConsole-Image-Builder) |
| CM3, CM4, CM5 | Ubuntu 24.04 | 6.12.64 | .img | [thread](https://forum.clockworkpi.com/t/14240), [GitHub](https://github.com/crossplatformdev/uConsole-Image-Builder) |
| CM3, CM4, CM5 | Debian 12 | 6.12.67 | .img | [thread](https://forum.clockworkpi.com/t/15847), provided by Rex |
| CM3, CM4, CM5 | Debian 13 | 6.12.67 | .img | [thread](https://forum.clockworkpi.com/t/19457), provided by Rex |
| CM4, CM5 | DragonOS | 6.12.67 | .img | [thread](https://forum.clockworkpi.com/t/17289), [MEGA](https://mega.nz/folder/19BlTQ7b#x1UsRMcb4UtIDwU-CPGsPA), provided by Rex |
| CM4, CM5 | Kali | 6.12.67 | .img | [thread](https://forum.clockworkpi.com/t/14463), provided by Rex |
| CM3, CM4, CM5 | ParrotOS | 6.12.67 | .img | [thread](https://forum.clockworkpi.com/t/14076), provided by Rex |
| CM3, CM4, CM5 | RetroPie | 6.12.67 | .img | [thread](https://forum.clockworkpi.com/t/13572), provided by Rex |
| CM3, CM4, CM5 | TwisterOS | 6.12.67 | .img | [thread](https://forum.clockworkpi.com/t/16617), provided by Rex |
| CM3, CM4, CM5 | Ubuntu 24.04 | 6.12.67 | .img | [thread](https://forum.clockworkpi.com/t/17397), [MEGA](https://mega.nz/folder/19BlTQ7b#x1UsRMcb4UtIDwU-CPGsPA), provided by Rex |
| CM3, CM4, CM5 | Debian 13 | 6.12.78 | APT repository | [GitHub](https://github.com/ak-rex/ClockworkPi-apt) |
| CM3, CM4, CM4S | Arch | 6.16 | source | [thread](https://forum.clockworkpi.com/t/11351), [thread](https://forum.clockworkpi.com/t/13190), [GitHub](https://github.com/PotatoMania/uconsole-cm3) |
| CM4, CM5 | Arch kernel | 6.18.6 | .pkg.tar.xz | [thread](https://forum.clockworkpi.com/t/19340), [GitHub](https://github.com/OuinOuin74/linux-clockwork-arch/) |
| CM4 | Debian 13 kernel | 6.18.20 | .deb | [thread](https://forum.clockworkpi.com/t/22027), [Google Drive](https://drive.google.com/drive/folders/1h64yB-PaO2qsouifAQpFVQjq01LWbDbM) |
| CM4, CM5 | Arch kernel | 7.0.9 | .pkg.tar.xz | [thread](https://forum.clockworkpi.com/t/22738), [GitHub](https://github.com/KondratokGK/linux-clockwork-arch/) |
| CM4 | NixOS | unspecified | source | [thread](https://forum.clockworkpi.com/t/12925), [forgejo](https://git.vdx.hu/voidcontext/nixos-uconsole), [GitHub](https://github.com/voidcontext/nixos-uconsole) |

There are some CM4 ClockworkPi OS releases [in this Google Drive folder](https://drive.google.com/drive/folders/1LYiT_G9b08VG5oqKIpOHd9msAtL_X99u), including one newer (v3.0) than the latest known release (v2.1).

There is one single non-Linux OS for the uConsole, EwokOS, for which there is [a thread](https://forum.clockworkpi.com/t/11783) and [a GitHub repository](https://github.com/MisaZhu/ewokos). It’s implied that EwokOS targets the CM4.

## Orange Pi compute modules

Orange Pi offers compute modules in the same form factor with up to 32GB RAM. Recently some folks have managed to get this working in the ClockworkPi adapter, though it requires some hard modification to the mainboard.

| compute module(s) | operating system | kernel version | format | URLs |
| --- | --- | --- | --- | --- |
| Orange Pi CM5 | Gentoo | unspecified | patchset | [thread](https://forum.clockworkpi.com/t/19952), [gitflic](https://gitflic.ru/project/consensus/uconsole-opi-cm5), [GitHub](https://github.com/si6Och4j/uconsole-opi-cm5) |

## Radxa compute modules

Radxa is another company that releases Raspberry Pi form factor compute modules, and their CM5 is somewhat popular despite barely unsupported and unstable because it comes with up to 32GB RAM, twice what the Raspberry Pi CM5 supports, and has a faster processor, NPU, and optional GPU. Full use of a Radxa CM5 requires [HackerGadgets’ adapter board](https://hackergadgets.com/products/pre-order-adapter-board-for-uconsole-ugrade-kit?variant=47122570444974) in place of ClockworkPi’s.

| compute module(s) | operating system | kernel version | format | URLs |
| --- | --- | --- | --- | --- |
| Radxa CM5 | Debian 11 | unknown | guide | [thread](https://forum.clockworkpi.com/t/15375), [GitHub](https://github.com/dev-null2019/radxa-cm5-uconsole) |
| Radxa CM5 | Arch | 6.1.84 | guide | [thread](https://forum.clockworkpi.com/t/21569/), [GitHub](https://github.com/0xrushi/ClockworkRadxa-linux/) |
| Radxa CM5 | Debian 12 | 6.1.84 | .img | [thread](https://forum.clockworkpi.com/t/16315), [MEGA](https://mega.nz/folder/p150laIY#XBTyo_qOVEjPFiz4iQ4jjA), [Google Drive](https://drive.google.com/drive/folders/1V2AMxJ5XYQStWnaYVlBT3kxEvQaaTd8j) |
| Radxa CM5 | Debian 12 | 6.1.115 | proof of concept | [thread](https://forum.clockworkpi.com/t/21829) |
| Radxa CM5 | Debian kernel | 7.1 | proof of concept | [thread](https://forum.clockworkpi.com/t/22747) |

## tl;dr

Raspberry Pi modules tend to have the best software support. Using a module from neither Raspberry Pi or ClockworkPi is veering off the beaten path. Using a non-Debian OS requires much configuration and futzing. Rex’s operating system images are the best supported.