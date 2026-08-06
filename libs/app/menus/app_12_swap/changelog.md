# Swap Manager changelog

## v2.5.1

- FIX seznam aktivních swapů používá úplný výstup `swapon --show`, takže zobrazuje swap soubory, swap partition i zram.
- SAFE editační submenu je dostupné pouze pro `TYPE=file`; zram a swap partition se zobrazují pouze informativně.
- UX obecné popisky již neoznačují všechny aktivní swapy jako image.
